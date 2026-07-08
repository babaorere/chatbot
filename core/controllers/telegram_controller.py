"""
telegram_controller — Webhook handler para Telegram.

Recibe actualizaciones de Telegram, resuelve el FSM (menús vs texto libre),
y delega la inferencia y reglas de negocio a ProcessMessageUseCase.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from sqlalchemy import func

from app.container import ProcessMessageUCDep, get_redis_client
from application.use_cases.commands import ProcessMessageCommand
from config.database import SessionLocal
from models.order import Order, OrderItem
from models.product import Product
from models.category import Category
from services.business_config_service import BusinessConfigService
from services.job_dispatcher import JobDispatcher
from services.cart_service import CartService
from services.product_service import ProductService
from services.user_service import UserService
from infrastructure.channels.telegram_fsm import (
    TelegramConversationFSM,
    FSMStateStore,
    FSMState,
    ExpectedInput,
    RedisFSMStateStore,
)
from infrastructure.channels.telegram_menu_flow import (
    CATEGORIES_MENU_SCOPE,
    CATEGORY_SCOPE_PREFIX,
    MAIN_MENU_SCOPE,
    PEDIDOS_MENU_SCOPE,
    TelegramMenuFlow,
    TelegramMenuPlan,
)
from infrastructure.channels.telegram_purchase_flow import (
    TelegramPurchaseFlow,
    TelegramPurchasePlan,
)
from infrastructure.channels.telegram_router import (
    TelegramInputKind,
    TelegramInputRouter,
)
from config.settings import settings
from services.order_service import OrderService
from services.telegram_service import (
    answer_telegram_callback_query,
    send_telegram_message,
    inject_version_to_reply_markup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_memory_fsm_store = FSMStateStore()

# Cerradura local en memoria para concurrencia si Redis no está activo
_local_locks: set[str] = set()
_FEATURED_MAX_ITEMS = 10
_REPLY_MARKUP_CLEANUP_CONCURRENCY = 2
_CATALOG_REMOTE_VERSION_CHECK_INTERVAL_SECONDS = 2.0
_CATALOG_REMOTE_VERSION_KEY_SUFFIX = "catalog:snapshot_version"
_reply_markup_cleanup_semaphore = asyncio.Semaphore(_REPLY_MARKUP_CLEANUP_CONCURRENCY)

# Caché en memoria para tablas pequeñas (Catálogo)
_categories_cache: list[dict[str, Any]] = []
_products_by_category_cache: dict[str, list[dict[str, Any]]] = {}


@dataclass(frozen=True)
class CatalogSnapshot:
    categories: tuple[dict[str, Any], ...] = ()
    products_by_category: dict[str, tuple[dict[str, Any], ...]] = field(
        default_factory=dict
    )
    products_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    loaded_at: float = 0.0
    version: int = 0


@dataclass(frozen=True)
class BusinessConfigSnapshot:
    name: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    business_hours: dict[str, Any] = field(default_factory=dict)
    promotions_config: dict[str, Any] = field(default_factory=dict)
    best_sellers_config: dict[str, Any] = field(default_factory=dict)
    favorites_config: dict[str, Any] = field(default_factory=dict)
    estimated_attention_minutes: int | None = None
    human_agent_available: bool = True
    loaded_at: float = 0.0
    version: int = 0


@dataclass(frozen=True)
class StaticMenuPrerenderSnapshot:
    catalog_version: int = 0
    plans_by_scope: dict[str, TelegramMenuPlan] = field(default_factory=dict)


_catalog_snapshot = CatalogSnapshot()
_business_config_snapshot = BusinessConfigSnapshot()
_static_menu_prerender_snapshot = StaticMenuPrerenderSnapshot()
_catalog_distributed_version_seen = 0
_catalog_remote_version_checked_at = 0.0


def _catalog_remote_version_key() -> str:
    return f"{settings.redis_namespace}:{_CATALOG_REMOTE_VERSION_KEY_SUFFIX}"


def prime_catalog_cache() -> None:
    """Pre-carga en memoria las categorías y productos disponibles para evitar accesos secuenciales a DB."""
    global _catalog_snapshot, _categories_cache, _products_by_category_cache
    started_at = time.perf_counter()
    db = SessionLocal()
    try:
        # Obtener todas las categorías ordenadas por nombre
        categories = db.query(Category).order_by(Category.name.asc()).all()
        categories_cache = [
            {"name": c.name, "slug": c.slug, "is_system": c.is_system}
            for c in categories
        ]

        # Obtener todos los productos disponibles y agruparlos por categoría
        products = db.query(Product).filter(Product.is_available.is_(True)).all()
        grouped: dict[str, list[dict[str, Any]]] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for p in products:
            p_dict = {
                "id": str(p.id),
                "name": p.name,
                "price": float(p.price) if p.price is not None else 0.0,
                "stock": int(p.stock) if p.stock is not None else 0,
                "category": p.category,
                "is_available": p.is_available,
                "unit_of_measure": p.unit_of_measure,
            }
            if p.category not in grouped:
                grouped[p.category] = []
            grouped[p.category].append(p_dict)
            by_id[p_dict["id"]] = p_dict

        next_snapshot = CatalogSnapshot(
            categories=tuple(categories_cache),
            products_by_category={
                category: tuple(category_products)
                for category, category_products in grouped.items()
            },
            products_by_id=by_id,
            loaded_at=time.time(),
            version=_catalog_snapshot.version + 1,
        )
        _catalog_snapshot = next_snapshot
        _categories_cache = list(next_snapshot.categories)
        _products_by_category_cache = {
            category: list(category_products)
            for category, category_products in next_snapshot.products_by_category.items()
        }
        logger.info(
            "Catalog cache primed successfully: %d categories, %d products cached, version=%d",
            len(next_snapshot.categories),
            len(products),
            next_snapshot.version,
        )
        _log_timing(
            trace_id="catalog-cache-prime",
            stage="catalog_cache_primed",
            started_at=started_at,
            extra=(
                f"categories={len(next_snapshot.categories)} products={len(products)} "
                f"version={next_snapshot.version}"
            ),
        )
    except Exception:
        logger.exception("Failed to prime catalog cache")
        raise
    finally:
        db.close()


def refresh_catalog_cache_after_commit(reason: str) -> None:
    """Refresca el snapshot de catálogo luego de una mutación confirmada."""
    global _catalog_distributed_version_seen
    started_at = time.perf_counter()
    try:
        prime_catalog_cache()
        remote_version = _bump_distributed_catalog_version(reason)
        if remote_version is not None:
            _catalog_distributed_version_seen = remote_version
        _log_timing(
            trace_id="catalog-cache-refresh",
            stage="catalog_cache_refreshed_after_commit",
            started_at=started_at,
            extra=(
                f"reason={reason} version={_catalog_snapshot.version} "
                f"remote_version={remote_version or '-'}"
            ),
        )
    except Exception as exc:
        logger.exception(
            "Catalog cache refresh failed after committed mutation [reason=%s]",
            reason,
        )
        raise RuntimeError(
            f"Failed to refresh catalog cache after committed mutation: {reason}"
        ) from exc


def _bump_distributed_catalog_version(reason: str) -> int | None:
    """Publica una nueva versión de catálogo para otros workers, si Redis está activo."""
    if get_redis_client() is None:
        return None

    try:
        from redis import Redis

        client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
        )
        try:
            version = int(client.incr(_catalog_remote_version_key()))
        finally:
            client.close()
    except Exception as exc:
        logger.exception(
            "Distributed catalog version bump failed [reason=%s]",
            reason,
        )
        raise RuntimeError(
            f"Failed to publish distributed catalog cache version: {reason}"
        ) from exc

    logger.info(
        "[telegram_cache] distributed_version_bumped key=%s version=%d reason=%s",
        _catalog_remote_version_key(),
        version,
        reason,
    )
    return version


async def _refresh_catalog_cache_if_remote_version_changed(
    *,
    trace_id: str,
    user_id: str | None = None,
) -> None:
    """Refresca el snapshot local si otro worker publicó una versión más nueva."""
    global _catalog_distributed_version_seen, _catalog_remote_version_checked_at

    redis_client = get_redis_client()
    if redis_client is None:
        return

    now = time.time()
    if (
        now - _catalog_remote_version_checked_at
        < _CATALOG_REMOTE_VERSION_CHECK_INTERVAL_SECONDS
    ):
        return
    _catalog_remote_version_checked_at = now

    started_at = time.perf_counter()
    raw_version = await redis_client.get(_catalog_remote_version_key())
    remote_version = int(raw_version) if raw_version is not None else 0
    if remote_version > _catalog_distributed_version_seen:
        await asyncio.to_thread(prime_catalog_cache)
        _catalog_distributed_version_seen = remote_version
        stage = "catalog_cache_remote_refreshed"
    else:
        stage = "catalog_cache_remote_checked"

    _log_timing(
        trace_id=trace_id,
        stage=stage,
        started_at=started_at,
        user_id=user_id,
        extra=(
            f"remote_version={remote_version} "
            f"seen_version={_catalog_distributed_version_seen}"
        ),
    )


def prime_business_config_cache(config: Any | None = None) -> BusinessConfigSnapshot:
    """Carga configuración estable del negocio para evitar DB en menús no transaccionales."""
    global _business_config_snapshot, _human_agent_cache
    started_at = time.perf_counter()
    db = None
    try:
        if config is None:
            db = SessionLocal()
            config = BusinessConfigService(db).get_config()

        next_snapshot = BusinessConfigSnapshot(
            name=str(getattr(config, "name", "") or ""),
            phone=str(getattr(config, "phone", "") or ""),
            address=str(getattr(config, "address", "") or ""),
            city=str(getattr(config, "city", "") or ""),
            business_hours=dict(getattr(config, "business_hours", {}) or {}),
            promotions_config=dict(getattr(config, "promotions_config", {}) or {}),
            best_sellers_config=dict(getattr(config, "best_sellers_config", {}) or {}),
            favorites_config=dict(getattr(config, "favorites_config", {}) or {}),
            estimated_attention_minutes=getattr(
                config,
                "estimated_attention_minutes",
                None,
            ),
            human_agent_available=bool(getattr(config, "human_agent_available", True)),
            loaded_at=time.time(),
            version=_business_config_snapshot.version + 1,
        )
        _business_config_snapshot = next_snapshot
        _human_agent_cache = {
            "value": next_snapshot.human_agent_available,
            "expires_at": time.time() + 300,
        }
        _log_timing(
            trace_id="business-config-cache-prime",
            stage="business_config_cache_primed",
            started_at=started_at,
            extra=f"version={next_snapshot.version}",
        )
        return next_snapshot
    except Exception as exc:
        logger.exception("Failed to prime business config cache")
        raise RuntimeError("Failed to prime business config cache") from exc
    finally:
        if db is not None:
            db.close()


def _get_business_config_snapshot() -> BusinessConfigSnapshot:
    if _business_config_snapshot.version > 0:
        logger.info(
            "[telegram_cache] key=business_config hit version=%d age_seconds=%.2f",
            _business_config_snapshot.version,
            time.time() - _business_config_snapshot.loaded_at,
        )
        return _business_config_snapshot

    logger.info("[telegram_cache] key=business_config miss")
    return prime_business_config_cache()


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _log_timing(
    *,
    trace_id: str,
    stage: str,
    started_at: float,
    user_id: str | None = None,
    extra: str = "",
) -> None:
    suffix = f" {extra}" if extra else ""
    logger.info(
        "[telegram_timing] trace=%s stage=%s elapsed_ms=%.2f user=%s%s",
        trace_id,
        stage,
        _elapsed_ms(started_at),
        user_id or "-",
        suffix,
    )


def _log_cache_snapshot(*, trace_id: str, user_id: str | None) -> None:
    snapshot = _catalog_snapshot
    product_count = len(snapshot.products_by_id)
    logger.info(
        "[telegram_cache] trace=%s categories=%d category_buckets=%d products=%d version=%d age_seconds=%.2f user=%s",
        trace_id,
        len(snapshot.categories),
        len(snapshot.products_by_category),
        product_count,
        snapshot.version,
        time.time() - snapshot.loaded_at if snapshot.loaded_at else -1,
        user_id or "-",
    )


def _active_categories_cache() -> list[dict[str, Any]]:
    snapshot_categories = list(_catalog_snapshot.categories)
    if snapshot_categories != _categories_cache:
        return _categories_cache
    return snapshot_categories


def _active_products_by_category_cache() -> dict[str, list[dict[str, Any]]]:
    snapshot_products = {
        category: list(products)
        for category, products in _catalog_snapshot.products_by_category.items()
    }
    if snapshot_products != _products_by_category_cache:
        return _products_by_category_cache
    return snapshot_products


def _copy_menu_plan(
    plan: TelegramMenuPlan,
    *,
    menu_stack: list[str] | None = None,
) -> TelegramMenuPlan:
    return TelegramMenuPlan(
        text=plan.text,
        reply_markup=deepcopy(plan.reply_markup),
        state=plan.state,
        menu_scope=plan.menu_scope,
        menu_stack=list(menu_stack if menu_stack is not None else plan.menu_stack),
        expected_input=plan.expected_input,
        allow_numeric_input=plan.allow_numeric_input,
        context_updates=deepcopy(plan.context_updates),
    )


def _get_static_menu_prerenders() -> StaticMenuPrerenderSnapshot:
    global _static_menu_prerender_snapshot
    catalog_version = _catalog_snapshot.version
    if (
        _static_menu_prerender_snapshot.catalog_version == catalog_version
        and _static_menu_prerender_snapshot.plans_by_scope
    ):
        return _static_menu_prerender_snapshot

    flow = _create_menu_flow()
    plans: dict[str, TelegramMenuPlan] = {}
    main_plan = flow.render_main_menu()
    plans[MAIN_MENU_SCOPE] = main_plan
    categories_plan = flow.render_categories_menu(current_stack=[MAIN_MENU_SCOPE])
    plans[CATEGORIES_MENU_SCOPE] = categories_plan
    for category in _active_categories_cache():
        slug = category.get("slug")
        if isinstance(slug, str) and slug:
            scope = f"{CATEGORY_SCOPE_PREFIX}{slug}"
            plans[scope] = flow.render_category_detail(
                category_slug=slug,
                current_stack=[MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE],
            )

    _static_menu_prerender_snapshot = StaticMenuPrerenderSnapshot(
        catalog_version=catalog_version,
        plans_by_scope=plans,
    )
    logger.info(
        "[telegram_cache] key=static_menu_prerender refreshed catalog_version=%d plans=%d",
        catalog_version,
        len(plans),
    )
    return _static_menu_prerender_snapshot


def _render_static_menu_plan(
    scope: str,
    *,
    current_stack: list[str] | None = None,
) -> TelegramMenuPlan | None:
    snapshot = _get_static_menu_prerenders()
    plan = snapshot.plans_by_scope.get(scope)
    if plan is None:
        return None
    if scope == MAIN_MENU_SCOPE:
        return _copy_menu_plan(plan, menu_stack=[MAIN_MENU_SCOPE])
    if scope == CATEGORIES_MENU_SCOPE:
        base_stack = current_stack or [MAIN_MENU_SCOPE]
        return _copy_menu_plan(
            plan,
            menu_stack=TelegramMenuFlow._push_scope(base_stack, CATEGORIES_MENU_SCOPE),
        )
    if scope.startswith(CATEGORY_SCOPE_PREFIX):
        base_stack = current_stack or [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE]
        return _copy_menu_plan(
            plan,
            menu_stack=TelegramMenuFlow._push_scope(base_stack, scope),
        )
    return None


def _render_main_menu_plan() -> TelegramMenuPlan:
    plan = _render_static_menu_plan(MAIN_MENU_SCOPE)
    if plan is not None:
        return plan
    return _create_menu_flow().render_main_menu()


def _render_menu_scope_plan(
    *,
    menu_flow: TelegramMenuFlow,
    scope: str,
    user_id: str,
    current_stack: list[str] | None = None,
) -> TelegramMenuPlan:
    static_plan = _render_static_menu_plan(scope, current_stack=current_stack)
    if static_plan is not None:
        return static_plan
    return menu_flow.render_scope(
        scope=scope,
        user_id=user_id,
        current_stack=current_stack,
    )


def _create_logged_task(
    coro: Any,
    *,
    trace_id: str,
    stage: str,
    user_id: str | None = None,
) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro)

    def _log_task_result(done_task: asyncio.Task[Any]) -> None:
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.info(
                "[telegram_task] trace=%s stage=%s cancelled user=%s",
                trace_id,
                stage,
                user_id or "-",
            )
        except Exception:
            logger.exception(
                "[telegram_task] trace=%s stage=%s failed user=%s",
                trace_id,
                stage,
                user_id or "-",
            )

    task.add_done_callback(_log_task_result)
    return task


async def _prewarm_idle_client_cache(
    *,
    trace_id: str,
    user_id: str | None = None,
    reason: str,
) -> None:
    """Precalienta datos no transaccionales mientras el cliente lee el menú."""
    started_at = time.perf_counter()
    try:
        if _catalog_snapshot.version == 0:
            await asyncio.to_thread(prime_catalog_cache)

        _get_static_menu_prerenders()
        _log_timing(
            trace_id=trace_id,
            stage="idle_prewarm_done",
            started_at=started_at,
            user_id=user_id,
            extra=f"reason={reason} catalog_version={_catalog_snapshot.version}",
        )
    except Exception:
        logger.exception(
            "[telegram_task] trace=%s stage=idle_prewarm failed user=%s reason=%s",
            trace_id,
            user_id or "-",
            reason,
        )


def _schedule_idle_prewarm(
    *,
    trace_id: str,
    user_id: str | None,
    reason: str,
) -> None:
    _create_logged_task(
        _prewarm_idle_client_cache(
            trace_id=trace_id,
            user_id=user_id,
            reason=reason,
        ),
        trace_id=trace_id,
        stage="idle_prewarm",
        user_id=user_id,
    )


def get_fsm_store() -> FSMStateStore:
    """Returns the Redis-backed FSM state store if configured, otherwise falls back to in-memory."""
    if settings.use_redis_sessions:
        redis_client = get_redis_client()
        if redis_client is not None:
            return RedisFSMStateStore(
                redis_client=redis_client,
                namespace=settings.redis_namespace,
                ttl_seconds=settings.redis_session_ttl_seconds,
            )
    return _memory_fsm_store


async def send_menu_message(
    bot_token: str,
    chat_id: int | str,
    text: str,
    reply_markup: dict | None,
    fsm: TelegramConversationFSM,
    trace_id: str | None = None,
    user_id: str | None = None,
    menu_scope: str | None = None,
    menu_stack: list[str] | None = None,
    expected_input: ExpectedInput = ExpectedInput.FREE_TEXT,
    allow_numeric_input: bool = False,
    next_state: FSMState | None = None,
    context_updates: dict[str, Any] | None = None,
) -> int | None:
    """Wrapper para enviar mensajes. Si contiene reply_markup, inyecta la versión del FSM

    e incrementa el contador, guardando el message_id resultante como el menú activo.
    También persiste las opciones en el FSM context para soporte híbrido numérico.
    """
    started_at = time.perf_counter()
    menu_version: int | None = None
    menu_options: list[str] = []
    if reply_markup and "inline_keyboard" in reply_markup:
        fsm_read_started_at = time.perf_counter()
        _, context = await fsm.get_state_and_context()
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="menu_fsm_context_loaded",
                started_at=fsm_read_started_at,
                user_id=user_id,
            )
        menu_version = context.get("_fsm_version", 1) + 1
        reply_markup = inject_version_to_reply_markup(reply_markup, menu_version)

        # Extraer y guardar callback_data para entrada numérica híbrida
        for row in reply_markup["inline_keyboard"]:
            for btn in row:
                if "callback_data" in btn:
                    cb = btn["callback_data"]
                    base = cb.split("#")[0]
                    menu_options.append(base)
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="menu_prepare",
                started_at=started_at,
                user_id=user_id,
                extra=f"version={menu_version} options={len(menu_options)}",
            )

    telegram_send_started_at = time.perf_counter()
    msg_id = await send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        trace_id=trace_id,
    )
    if trace_id:
        _log_timing(
            trace_id=trace_id,
            stage="telegram_send_message_done",
            started_at=telegram_send_started_at,
            user_id=user_id,
            extra=f"message_id={msg_id} has_markup={bool(reply_markup)}",
        )

    if (
        msg_id
        and reply_markup
        and "inline_keyboard" in reply_markup
        and menu_version is not None
    ):
        if context_updates:
            fsm_update_started_at = time.perf_counter()
            await fsm.update_state(
                lambda current_state, context: (
                    next_state or current_state,
                    {**context, **context_updates},
                )
            )
            if trace_id:
                _log_timing(
                    trace_id=trace_id,
                    stage="menu_context_updates_persisted",
                    started_at=fsm_update_started_at,
                    user_id=user_id,
                    extra=f"keys={','.join(sorted(context_updates.keys()))}",
                )
        metadata_started_at = time.perf_counter()
        await fsm.persist_menu_metadata(
            version=menu_version,
            options=menu_options,
            active_menu_id=msg_id,
            state=next_state,
            menu_scope=menu_scope,
            menu_stack=menu_stack,
            expected_input=expected_input,
            allow_numeric_input=allow_numeric_input,
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="menu_metadata_persisted",
                started_at=metadata_started_at,
                user_id=user_id,
                extra=f"message_id={msg_id}",
            )
    elif trace_id:
        _log_timing(
            trace_id=trace_id,
            stage="menu_send_completed",
            started_at=started_at,
            user_id=user_id,
            extra=f"message_id={msg_id}",
        )
    elif next_state is not None or context_updates:
        fsm_update_started_at = time.perf_counter()
        await fsm.update_state(
            lambda current_state, context: (
                next_state or current_state,
                {**context, **(context_updates or {})},
            )
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="message_state_persisted",
                started_at=fsm_update_started_at,
                user_id=user_id,
                extra=f"has_context_updates={bool(context_updates)}",
            )

    return msg_id


_human_agent_cache: dict[str, Any] = {"value": True, "expires_at": 0}


def prime_human_agent_cache(value: bool, ttl_seconds: int = 300) -> None:
    """Carga en memoria el estado de atención humana para evitar un lookup inicial en DB."""
    global _human_agent_cache
    _human_agent_cache = {
        "value": value,
        "expires_at": time.time() + ttl_seconds,
    }
    # Cargar también la caché del catálogo al arrancar o refrescar
    prime_catalog_cache()


def _get_human_agent_available() -> bool:
    """Retrieves whether a human agent is currently available from business configuration with caching."""
    global _human_agent_cache
    now = time.time()
    if now < _human_agent_cache["expires_at"]:
        logger.info(
            "[telegram_cache] key=human_agent_available hit ttl_remaining=%.2f value=%s",
            _human_agent_cache["expires_at"] - now,
            _human_agent_cache["value"],
        )
        return _human_agent_cache["value"]

    logger.info("[telegram_cache] key=human_agent_available miss")
    db = SessionLocal()
    try:
        cfg = BusinessConfigService(db).get_config()
        snapshot = prime_business_config_cache(cfg)
        return snapshot.human_agent_available
    except Exception as exc:
        logger.exception("Failed to resolve human agent availability")
        raise RuntimeError("Failed to resolve human agent availability") from exc
    finally:
        db.close()


def _format_money(value: float) -> str:
    return f"${value:,.0f}"


def _parse_featured_section(config: dict[str, Any] | None) -> dict[str, Any]:
    data = config or {}
    return {
        "enabled": bool(data.get("enabled", False)),
        "title": str(data.get("title") or "").strip(),
        "mode": "automatic" if data.get("mode") == "automatic" else "manual",
        "product_ids": [str(product_id) for product_id in data.get("product_ids", [])],
    }


def _load_products_by_ids(db, product_ids: list[str]) -> list[Product]:
    if not product_ids:
        return []
    rows = db.query(Product).filter(Product.id.in_(product_ids)).all()
    by_id = {str(product.id): product for product in rows}
    return [by_id[product_id] for product_id in product_ids if product_id in by_id]


def _build_featured_products_text(title: str, products: list[Product]) -> str:
    if not products:
        return _build_empty_featured_text(
            title=title,
            body="Aún no hay productos para mostrar en esta sección.",
        )

    lines = [title, ""]
    for idx, product in enumerate(products, start=1):
        price = float(product.price) if product.price else 0.0
        lines.append(
            f"{idx}. {product.name} - {_format_money(price)}"
            + (f" | Stock: {product.stock}" if product.stock is not None else "")
        )
    lines.append("")
    lines.append("Usa las categorías para ver el detalle de cada producto.")
    return "\n".join(lines)


def _build_empty_featured_text(title: str, body: str) -> str:
    return (
        f"{title}\n\n"
        f"{body}\n"
        "Si lo prefieres, revisa las categorías para ver otras opciones."
    )


def _build_empty_cart_text() -> str:
    return (
        "Tu carrito está vacío por ahora.\n\n"
        "Cuando agregues productos, aparecerán aquí para que puedas continuar tu compra."
    )


def _get_promotions_text() -> tuple[str, list[str]]:
    cfg = _get_business_config_snapshot()
    section = _parse_featured_section(cfg.promotions_config)
    title = section["title"] or "Promociones destacadas del momento:"
    if not section["enabled"]:
        return _build_empty_featured_text(
            title,
            "Aún no hay promociones publicadas.",
        ), []

    db = SessionLocal()
    try:
        products = _load_products_by_ids(db, section["product_ids"])
        if not products:
            product_svc = ProductService(db)
            products = product_svc.list_products(
                available_only=True, skip=0, limit=_FEATURED_MAX_ITEMS
            )
            products = sorted(
                products,
                key=lambda product: (
                    float(product.price) if product.price is not None else 0.0,
                    -int(product.stock or 0),
                    product.name,
                ),
            )
        else:
            products = [p for p in products if p.is_available]

        lines = [title, ""]
        product_names = []
        for idx, product in enumerate(products[:_FEATURED_MAX_ITEMS], start=1):
            price = float(product.price) if product.price else 0.0
            lines.append(
                f"{idx}. {product.name} - {_format_money(price)}"
                + (f" | Stock: {product.stock}" if product.stock is not None else "")
            )
            product_names.append(product.name)
        lines.append("")
        lines.append("Usa las categorías para ver el detalle de cada producto.")
        return "\n".join(lines), product_names
    except Exception as exc:
        logger.exception("Failed to build promotions menu text")
        raise RuntimeError(
            "No pudimos cargar las promociones en este momento."
        ) from exc
    finally:
        db.close()


def _get_best_sellers_text() -> tuple[str, list[str]]:
    cfg = _get_business_config_snapshot()
    section = _parse_featured_section(cfg.best_sellers_config)
    title = section["title"] or "Más vendidos del momento:"
    if not section["enabled"]:
        return _build_empty_featured_text(
            title,
            "Todavía no hay más vendidos para mostrar.",
        ), []

    db = SessionLocal()
    try:
        if section["mode"] == "manual" and section["product_ids"]:
            products = _load_products_by_ids(db, section["product_ids"])
            products = [p for p in products if p.is_available]
            lines = [title, ""]
            product_names = []
            for idx, product in enumerate(products[:_FEATURED_MAX_ITEMS], start=1):
                price = float(product.price) if product.price else 0.0
                lines.append(
                    f"{idx}. {product.name} - {_format_money(price)}"
                    + (
                        f" | Stock: {product.stock}"
                        if product.stock is not None
                        else ""
                    )
                )
                product_names.append(product.name)
            lines.append("")
            lines.append("Usa las categorías para ver el detalle de cada producto.")
            return "\n".join(lines), product_names

        rows = (
            db.query(
                Product.name.label("name"),
                Product.price.label("price"),
                func.sum(OrderItem.quantity).label("units_sold"),
            )
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.status != "cancelled")
            .group_by(Product.id, Product.name, Product.price)
            .order_by(func.sum(OrderItem.quantity).desc(), Product.name.asc())
            .limit(_FEATURED_MAX_ITEMS)
            .all()
        )
        if not rows:
            products = _load_products_by_ids(db, section["product_ids"])
            products = [p for p in products if p.is_available]
            if products:
                lines = [title, ""]
                product_names = []
                for idx, product in enumerate(products[:_FEATURED_MAX_ITEMS], start=1):
                    price = float(product.price) if product.price else 0.0
                    lines.append(
                        f"{idx}. {product.name} - {_format_money(price)}"
                        + (
                            f" | Stock: {product.stock}"
                            if product.stock is not None
                            else ""
                        )
                    )
                    product_names.append(product.name)
                lines.append("")
                lines.append("Usa las categorías para ver el detalle de cada producto.")
                return "\n".join(lines), product_names
            return _build_empty_featured_text(
                title,
                "Todavía no hay ventas suficientes para mostrar esta sección.",
            ), []

        lines = [title, ""]
        product_names = []
        for idx, row in enumerate(rows, start=1):
            price = float(row.price) if row.price is not None else 0.0
            lines.append(
                f"{idx}. {row.name} - {_format_money(price)} | Vendidos: {int(row.units_sold or 0)}"
            )
            product_names.append(row.name)
        return "\n".join(lines), product_names
    except Exception as exc:
        logger.exception("Failed to build best sellers menu text")
        raise RuntimeError(
            "No pudimos cargar los más vendidos en este momento."
        ) from exc
    finally:
        db.close()


def _get_favorites_text() -> tuple[str, list[str]]:
    cfg = _get_business_config_snapshot()
    section = _parse_featured_section(cfg.favorites_config)
    title = section["title"] or "Productos favoritos:"
    if not section["enabled"]:
        return _build_empty_featured_text(
            title,
            "Aún no hay productos favoritos publicados.",
        ), []

    db = SessionLocal()
    try:
        products = _load_products_by_ids(db, section["product_ids"])
        products = [p for p in products if p.is_available]
        lines = [title, ""]
        product_names = []
        for idx, product in enumerate(products[:_FEATURED_MAX_ITEMS], start=1):
            price = float(product.price) if product.price else 0.0
            lines.append(
                f"{idx}. {product.name} - {_format_money(price)}"
                + (f" | Stock: {product.stock}" if product.stock is not None else "")
            )
            product_names.append(product.name)
        lines.append("")
        lines.append("Usa las categorías para ver el detalle de cada producto.")
        return "\n".join(lines), product_names
    except Exception as exc:
        logger.exception("Failed to build favorites menu text")
        raise RuntimeError("No pudimos cargar los favoritos en este momento.") from exc
    finally:
        db.close()


def _get_cart_text(user_id: str) -> str:
    db = SessionLocal()
    try:
        user = UserService(db).get_or_create(external_id=user_id, platform="telegram")
        cart = CartService(db).get_or_create_cart(user.id)
        if not cart.items:
            return _build_empty_cart_text()

        cart_data = cart.to_dict()
        lines = ["Tu carrito actual:", ""]
        total = 0.0
        for idx, item in enumerate(cart_data["items"], start=1):
            item_total = float(item["product_price"]) * int(item["quantity"])
            total += item_total
            lines.append(
                f"{idx}. {item['product_name']} x{item['quantity']} - {_format_money(item_total)}"
            )
        lines.append("")
        lines.append(f"Total estimado: {_format_money(total)}")
        lines.append(
            "Si deseas continuar, vuelve a categorías para agregar más productos."
        )
        return "\n".join(lines)
    except Exception as exc:
        logger.exception("Failed to build cart summary")
        raise RuntimeError("No pudimos cargar tu carrito en este momento.") from exc
    finally:
        db.close()


def _get_cart_summary(user_id: str) -> tuple[str, bool]:
    text = _get_cart_text(user_id)
    return text, text != _build_empty_cart_text()


def _get_orders_text(user_id: str) -> tuple[str, bool]:
    db = SessionLocal()
    try:
        user = UserService(db).get_or_create(external_id=user_id, platform="telegram")
        orders = OrderService(db).list_user_orders(user.id)
        if not orders:
            return "No tienes pedidos realizados aún.", False

        lines = ["Historial de tus pedidos:", ""]
        for idx, order in enumerate(orders[:5], start=1):
            date_str = (
                order.created_at.strftime("%d/%m/%Y %H:%M")
                if order.created_at
                else "Fecha desconocida"
            )
            status_emoji = {
                "pending": "⏳ Pendiente",
                "confirmed": "✅ Confirmado",
                "preparing": "👨‍🍳 Preparando",
                "ready": "📦 Listo para entrega",
                "delivered": "🛵 Entregado",
                "cancelled": "❌ Cancelado",
            }.get(order.status, order.status)
            lines.append(
                f"{idx}. Pedido: `{str(order.id)[:8]}...`\n"
                f"   Estado: {status_emoji}\n"
                f"   Total: {_format_money(float(order.total_amount))}\n"
                f"   Fecha: {date_str}"
            )
        lines.append("")
        lines.append("Se muestran tus últimos 5 pedidos.")
        return "\n".join(lines), True
    except Exception as exc:
        logger.exception("Failed to build orders menu summary")
        raise RuntimeError("No pudimos cargar tus pedidos en este momento.") from exc
    finally:
        db.close()


def _get_orders_summary(user_id: str) -> tuple[str, bool]:
    return _get_orders_text(user_id)


def _create_menu_flow() -> TelegramMenuFlow:
    return TelegramMenuFlow(
        promotions_builder=_get_promotions_text,
        best_sellers_builder=_get_best_sellers_text,
        favorites_builder=_get_favorites_text,
        cart_builder=_get_cart_summary,
        orders_builder=_get_orders_summary,
        categories_cache=_active_categories_cache(),
        products_cache=_active_products_by_category_cache(),
    )


def _create_purchase_flow() -> TelegramPurchaseFlow:
    return TelegramPurchaseFlow(product_cache=_catalog_snapshot.products_by_id)


async def _apply_menu_plan(
    *,
    token: str,
    chat_id: Any,
    user_id: str,
    fsm: TelegramConversationFSM,
    plan: TelegramMenuPlan,
    trace_id: str,
) -> None:
    await send_menu_message(
        bot_token=token,
        chat_id=chat_id,
        text=plan.text,
        reply_markup=plan.reply_markup,
        fsm=fsm,
        trace_id=trace_id,
        user_id=user_id,
        menu_scope=plan.menu_scope,
        menu_stack=plan.menu_stack,
        expected_input=plan.expected_input,
        allow_numeric_input=plan.allow_numeric_input,
        next_state=plan.state,
        context_updates=plan.context_updates,
    )


async def _apply_purchase_plan(
    *,
    token: str,
    chat_id: Any,
    user_id: str,
    fsm: TelegramConversationFSM,
    plan: TelegramPurchasePlan,
    trace_id: str,
) -> None:
    await send_menu_message(
        bot_token=token,
        chat_id=chat_id,
        text=plan.text,
        reply_markup=plan.reply_markup,
        fsm=fsm,
        trace_id=trace_id,
        user_id=user_id,
        menu_scope=plan.menu_scope,
        menu_stack=plan.menu_stack,
        expected_input=plan.expected_input,
        allow_numeric_input=plan.allow_numeric_input,
        next_state=plan.state,
        context_updates=plan.context_updates,
    )


async def _build_telegram_llm_metadata(
    fsm: TelegramConversationFSM,
) -> dict[str, str]:
    state, context = await fsm.get_state_and_context()
    metadata: dict[str, str] = {
        "telegram_fsm_state": state.value,
    }
    menu_scope = context.get("_menu_scope")
    if isinstance(menu_scope, str) and menu_scope:
        metadata["telegram_menu_scope"] = menu_scope
    expected_input = context.get("_expected_input")
    if isinstance(expected_input, str) and expected_input:
        metadata["telegram_expected_input"] = expected_input
    selected_category = context.get("selected_category")
    if isinstance(selected_category, str) and selected_category:
        metadata["telegram_selected_category"] = selected_category
    allowed_actions: list[str] = []
    if state == FSMState.IN_MENU:
        allowed_actions.extend(["stay_in_menu", "go_back", "go_home"])
        if menu_scope == CATEGORIES_MENU_SCOPE:
            allowed_actions.append("open_category")
    elif state == FSMState.AWAITING_QUANTITY:
        allowed_actions.extend(["stay_in_state", "go_back", "go_home"])
    elif state == FSMState.AWAITING_CONFIRMATION:
        allowed_actions.extend(["confirm_pending_action", "go_back", "go_home"])
    elif state == FSMState.AWAITING_PRODUCT_NAME:
        allowed_actions.extend(["stay_in_state", "go_home"])
    if allowed_actions:
        metadata["telegram_allowed_actions"] = ",".join(allowed_actions)
    return metadata


async def _clear_latest_conversation_session(
    user_id: str,
    trace_id: str | None = None,
    reason: str = "manual_reset",
) -> None:
    """Programa o ejecuta el clear de la sesión conversacional más reciente."""
    started_at = time.perf_counter()
    event_id = str(uuid.uuid4())

    try:
        await JobDispatcher().enqueue_job(
            "job_clear_latest_conversation_session",
            user_id=user_id,
            trace_id=trace_id,
            reason=reason,
            event_id=event_id,
            _job_id=f"session-clear:{event_id}",
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="session_clear_enqueued",
                started_at=started_at,
                user_id=user_id,
                extra=f"reason={reason} event_id={event_id}",
            )
    except Exception as exc:
        logger.exception(
            "Failed to enqueue latest conversation session clear [user=%s]",
            user_id,
        )
        raise RuntimeError(
            "ARQ must be available for conversation reset dispatch."
        ) from exc


async def _defer_clear_reply_markup(
    *,
    token: str,
    chat_id: Any,
    message_id: int,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Programa la limpieza del teclado inline con job durable."""
    started_at = time.perf_counter()
    if _reply_markup_cleanup_semaphore.locked():
        logger.warning(
            "[telegram_task] trace=%s stage=reply_markup_clear_dropped user=%s message_id=%s reason=semaphore_saturated",
            trace_id or "-",
            user_id or "-",
            message_id,
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="reply_markup_clear_dropped",
                started_at=started_at,
                user_id=user_id,
                extra=f"message_id={message_id} reason=semaphore_saturated",
            )
        return

    await _reply_markup_cleanup_semaphore.acquire()
    event_id = str(uuid.uuid4())
    try:
        await JobDispatcher().enqueue_job(
            "job_clear_reply_markup",
            token=token,
            chat_id=chat_id,
            message_id=message_id,
            trace_id=trace_id,
            user_id=user_id,
            event_id=event_id,
            _job_id=f"telegram:clear-reply-markup:{event_id}",
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="reply_markup_clear_enqueued",
                started_at=started_at,
                user_id=user_id,
                extra=f"message_id={message_id}",
            )
    except Exception as exc:
        logger.exception(
            "Failed to enqueue reply markup cleanup [user=%s message_id=%s]",
            user_id,
            message_id,
        )
        raise RuntimeError(
            "ARQ must be available for reply markup cleanup dispatch."
        ) from exc
    finally:
        _reply_markup_cleanup_semaphore.release()


async def _process_telegram_update_core(
    token: str,
    chat_id: Any,
    user_id: str,
    message_obj: Any,
    callback_query: Any,
    callback_query_id: Any,
    msg_obj: Any,
    process_message_uc: Any,
    trace_id: str,
) -> None:
    """Núcleo del procesamiento de actualizaciones de Telegram."""
    core_started_at = time.perf_counter()
    _log_timing(
        trace_id=trace_id,
        stage="background_core_start",
        started_at=core_started_at,
        user_id=user_id,
        extra=f"has_callback={bool(callback_query)} has_message={bool(message_obj)}",
    )
    fsm = TelegramConversationFSM(user_id=user_id, state_store=get_fsm_store())

    await _refresh_catalog_cache_if_remote_version_changed(
        trace_id=trace_id,
        user_id=user_id,
    )
    menu_flow = _create_menu_flow()
    purchase_flow = _create_purchase_flow()
    input_router = TelegramInputRouter()
    _log_cache_snapshot(trace_id=trace_id, user_id=user_id)

    # Chequeo de expiración por inactividad de 30 minutos (1800 segundos)
    fsm_context_started_at = time.perf_counter()
    ctx = await fsm.get_context()
    _log_timing(
        trace_id=trace_id,
        stage="initial_fsm_context_loaded",
        started_at=fsm_context_started_at,
        user_id=user_id,
        extra=f"context_keys={len(ctx)}",
    )
    last_interaction = ctx.get("_last_interaction_at")
    if last_interaction is not None:
        if time.time() - last_interaction >= 1800:
            logger.info(
                "Session for user %s expired due to inactivity. Resetting FSM & LLM context.",
                user_id,
            )
            expiry_started_at = time.perf_counter()
            await fsm.reset()

            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason="expired_inactivity",
            )
            _log_timing(
                trace_id=trace_id,
                stage="expired_session_reset",
                started_at=expiry_started_at,
                user_id=user_id,
                extra="reason=expired_inactivity",
            )
            welcome_expired_text = (
                "Tu sesión anterior expiró por inactividad. Puedes retomar desde el inicio. 🙂\n\n"
                "Negocio El Buen Trago.\n"
                "Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00.\n"
                "Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio.\n"
                "Ubicación: Santiago, Chile.\n\n"
                "¿En qué puedo ayudarte hoy?"
            )
            expired_plan = _render_main_menu_plan()
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text=welcome_expired_text,
                reply_markup=expired_plan.reply_markup,
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
                menu_scope=expired_plan.menu_scope,
                menu_stack=expired_plan.menu_stack,
                expected_input=expired_plan.expected_input,
                allow_numeric_input=expired_plan.allow_numeric_input,
                next_state=expired_plan.state,
            )
            return

    route_started_at = time.perf_counter()
    event = await input_router.route(
        message_obj=message_obj,
        callback_query=callback_query,
        callback_query_id=callback_query_id,
        fsm=fsm,
    )
    _log_timing(
        trace_id=trace_id,
        stage="input_routed",
        started_at=route_started_at,
        user_id=user_id,
        extra=f"kind={event.kind.value if event is not None else 'none'}",
    )
    if event is None:
        return

    if event.kind in {
        TelegramInputKind.CALLBACK,
        TelegramInputKind.LEGACY_NUMERIC_MENU,
    }:
        callback_started_at = time.perf_counter()
        raw_callback_data = event.callback_data
        if not raw_callback_data:
            return

        validation_started_at = time.perf_counter()
        runtime_snapshot = await fsm.get_runtime_snapshot()
        current_state = runtime_snapshot.state
        active_menu_id = runtime_snapshot.active_menu_id
        current_fsm_version = runtime_snapshot.fsm_version
        is_valid = False
        btn_version = None
        is_numeric_selection = event.kind == TelegramInputKind.LEGACY_NUMERIC_MENU

        if (
            active_menu_id is not None
            and event.message_obj
            and not is_numeric_selection
        ):
            is_valid = event.message_obj.get("message_id") == active_menu_id
        else:
            if "#" in raw_callback_data:
                try:
                    btn_version = int(raw_callback_data.split("#")[1])
                except ValueError:
                    btn_version = None
            if btn_version is not None:
                is_valid = btn_version == current_fsm_version
            else:
                msg_date = event.message_obj.get("date", 0) if event.message_obj else 0
                current_time = int(time.time())
                is_valid = (current_time - msg_date < 600) and (
                    current_state in {FSMState.IDLE, FSMState.IN_MENU}
                )
        _log_timing(
            trace_id=trace_id,
            stage="callback_validated",
            started_at=validation_started_at,
            user_id=user_id,
            extra=(
                f"valid={is_valid} numeric={is_numeric_selection} "
                f"state={current_state.value} active_menu_id={active_menu_id} "
                f"current_version={current_fsm_version}"
            ),
        )

        if not is_valid:
            logger.warning(
                "Rejected expired callback [user=%s]: msg_id=%s (active=%s), btn_ver=%s (current=%s)",
                user_id,
                event.message_obj.get("message_id") if event.message_obj else None,
                active_menu_id,
                btn_version,
                current_fsm_version,
            )
            if event.callback_query_id:
                await answer_telegram_callback_query(
                    bot_token=token,
                    callback_query_id=event.callback_query_id,
                    text="Este menú ha expirado o ya no está activo.",
                    trace_id=trace_id,
                )
            if event.message_obj and event.message_obj.get("message_id"):
                await _defer_clear_reply_markup(
                    token=token,
                    chat_id=chat_id,
                    message_id=event.message_obj["message_id"],
                    trace_id=trace_id,
                    user_id=user_id,
                )
            return

        if event.callback_query_id:
            _create_logged_task(
                answer_telegram_callback_query(
                    bot_token=token,
                    callback_query_id=event.callback_query_id,
                    trace_id=trace_id,
                ),
                trace_id=trace_id,
                stage="callback_ack",
                user_id=user_id,
            )
        if (
            event.message_obj
            and event.message_obj.get("message_id")
            and event.kind == TelegramInputKind.CALLBACK
        ):
            _create_logged_task(
                _defer_clear_reply_markup(
                    token=token,
                    chat_id=chat_id,
                    message_id=event.message_obj["message_id"],
                    trace_id=trace_id,
                    user_id=user_id,
                ),
                trace_id=trace_id,
                stage="callback_reply_markup_cleanup_enqueue",
                user_id=user_id,
            )

        callback_data = raw_callback_data.split("#")[0]
        stack_started_at = time.perf_counter()
        current_stack = runtime_snapshot.menu_stack
        _log_timing(
            trace_id=trace_id,
            stage="menu_stack_loaded_from_snapshot",
            started_at=stack_started_at,
            user_id=user_id,
            extra=f"depth={len(current_stack)} callback={callback_data}",
        )
        plan: TelegramMenuPlan | None = None

        render_started_at = time.perf_counter()
        if callback_data == "menu:categorias":
            plan = _render_static_menu_plan(
                CATEGORIES_MENU_SCOPE,
                current_stack=current_stack,
            )
        elif callback_data.startswith("product_select:"):
            product_id = callback_data.split(":", 1)[1]
            purchase_plan = purchase_flow.render_quantity_prompt(product_id=product_id)
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data.startswith("qty_select:"):
            quantity = purchase_flow.parse_quantity(callback_data.split(":", 1)[1])
            pending_product_id = runtime_snapshot.context.get("pending_product_id")
            if quantity is None or not isinstance(pending_product_id, str):
                plan = _render_static_menu_plan(MAIN_MENU_SCOPE)
                await _apply_menu_plan(
                    token=token,
                    chat_id=chat_id,
                    user_id=user_id,
                    fsm=fsm,
                    plan=plan,
                    trace_id=trace_id,
                )
                return
            purchase_plan = purchase_flow.render_confirmation_prompt(
                product_id=pending_product_id,
                quantity=quantity,
            )
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data == "cart:change_quantity":
            pending_product_id = runtime_snapshot.context.get("pending_product_id")
            if not isinstance(pending_product_id, str):
                plan = _render_static_menu_plan(MAIN_MENU_SCOPE)
                await _apply_menu_plan(
                    token=token,
                    chat_id=chat_id,
                    user_id=user_id,
                    fsm=fsm,
                    plan=plan,
                    trace_id=trace_id,
                )
                return
            purchase_plan = purchase_flow.render_quantity_prompt(
                product_id=pending_product_id
            )
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data == "cart:add_confirm":
            context = runtime_snapshot.context
            pending_product_id = context.get("pending_product_id")
            pending_quantity = context.get("pending_quantity")
            if not isinstance(pending_product_id, str) or not isinstance(
                pending_quantity, int
            ):
                plan = _render_static_menu_plan(MAIN_MENU_SCOPE)
                await _apply_menu_plan(
                    token=token,
                    chat_id=chat_id,
                    user_id=user_id,
                    fsm=fsm,
                    plan=plan,
                    trace_id=trace_id,
                )
                return
            purchase_plan = purchase_flow.confirm_add_to_cart(
                external_user_id=user_id,
                product_id=pending_product_id,
                quantity=pending_quantity,
            )
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data == "cart:start_checkout":
            purchase_plan = purchase_flow.render_checkout_confirmation()
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data == "checkout:confirm":
            purchase_plan = purchase_flow.confirm_checkout(external_user_id=user_id)
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data == "cart:clear":
            purchase_plan = purchase_flow.clear_cart(external_user_id=user_id)
            await _apply_purchase_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=purchase_plan,
                trace_id=trace_id,
            )
            return
        elif callback_data.startswith("cat_select:"):
            slug = callback_data.split(":", 1)[1]
            plan = _render_static_menu_plan(
                f"{CATEGORY_SCOPE_PREFIX}{slug}",
                current_stack=current_stack,
            )
            if plan is None:
                await asyncio.to_thread(prime_catalog_cache)
                menu_flow = _create_menu_flow()
                plan = _render_static_menu_plan(
                    f"{CATEGORY_SCOPE_PREFIX}{slug}",
                    current_stack=current_stack,
                ) or menu_flow.render_category_detail(
                    category_slug=slug,
                    current_stack=current_stack,
                )
        elif callback_data == "menu:promociones":
            plan = menu_flow.render_promotions_menu(
                current_stack=current_stack,
                user_id=user_id,
            )
        elif callback_data == "menu:mas_vendidos":
            plan = menu_flow.render_best_sellers_menu(current_stack=current_stack)
        elif callback_data == "menu:favoritos":
            plan = menu_flow.render_favorites_menu(current_stack=current_stack)
        elif callback_data == "menu:carrito":
            plan = menu_flow.render_cart_menu(
                current_stack=current_stack,
                user_id=user_id,
            )
        elif callback_data == "menu:pedidos":
            plan = menu_flow.render_orders_menu(
                current_stack=current_stack,
                user_id=user_id,
            )
        elif callback_data == "menu:buscar_pedido_prompt":
            await fsm.set_state(
                FSMState.AWAITING_ORDER_ID,
                {
                    "action": "search",
                    "_expected_input": ExpectedInput.ORDER_ID.value,
                    "_menu_stack": current_stack,
                    "_menu_scope": PEDIDOS_MENU_SCOPE,
                },
            )
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text="Por favor, escribe el ID (código o UUID) del pedido que deseas buscar:",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "↩️ Volver", "callback_data": "menu:back"}],
                        [{"text": "🏠 Menú principal", "callback_data": "menu:home"}],
                    ]
                },
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
                expected_input=ExpectedInput.ORDER_ID,
                next_state=FSMState.AWAITING_ORDER_ID,
            )
            return
        elif callback_data == "menu:cancelar_pedido_prompt":
            await fsm.set_state(
                FSMState.AWAITING_ORDER_ID,
                {
                    "action": "cancel",
                    "_expected_input": ExpectedInput.ORDER_ID.value,
                    "_menu_stack": current_stack,
                    "_menu_scope": PEDIDOS_MENU_SCOPE,
                },
            )
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text="Por favor, escribe el ID (código o UUID) del pedido que deseas cancelar:",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "↩️ Volver", "callback_data": "menu:back"}],
                        [{"text": "🏠 Menú principal", "callback_data": "menu:home"}],
                    ]
                },
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
                expected_input=ExpectedInput.ORDER_ID,
                next_state=FSMState.AWAITING_ORDER_ID,
            )
            return
        elif callback_data in {"menu:home", "menu:back_to_main", "menu:inicio"}:
            plan = _render_static_menu_plan(MAIN_MENU_SCOPE)
        elif callback_data == "menu:back":
            previous_scope = menu_flow.resolve_back_scope(current_stack)
            plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=previous_scope,
                user_id=user_id,
                current_stack=current_stack[:-1],
            )

        if plan is not None:
            _log_timing(
                trace_id=trace_id,
                stage="callback_menu_plan_rendered",
                started_at=render_started_at,
                user_id=user_id,
                extra=f"callback={callback_data} scope={plan.menu_scope}",
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            _log_timing(
                trace_id=trace_id,
                stage="callback_done",
                started_at=callback_started_at,
                user_id=user_id,
                extra=f"callback={callback_data}",
            )
            return

        transition_started_at = time.perf_counter()
        new_state, context = await fsm.transition(raw_callback_data)
        _log_timing(
            trace_id=trace_id,
            stage="callback_fsm_transition_done",
            started_at=transition_started_at,
            user_id=user_id,
            extra=f"callback={callback_data} next_state={new_state.value}",
        )
        intent = context.get("intent")
        if intent == "consultar_stock":
            response_text = "Escribe el nombre del producto."
        elif intent == "consultar_precio":
            response_text = "Escribe el producto para revisar su precio."
        elif intent == "get_chatbot_info":
            response_text = "Nuestro horario de atención es de Lunes a Sábado de 10:00 a 22:00, y Domingo de 12:00 a 20:00."
        elif intent == "contactar_humano":
            response_text = "Un ejecutivo se pondrá en contacto contigo pronto."
        else:
            response_text = "No entendí esa acción. Usa el menú para continuar."

        await send_menu_message(
            bot_token=token,
            chat_id=chat_id,
            text=response_text,
            reply_markup=None,
            fsm=fsm,
            trace_id=trace_id,
            user_id=user_id,
            next_state=new_state,
            context_updates=context,
        )
        return

    # Procesamiento de Mensajes de Texto
    text_started_at = time.perf_counter()
    message_text = event.text
    if not message_text:
        return

    text_state_started_at = time.perf_counter()
    current_state, fsm_context = await fsm.get_state_and_context()
    _log_timing(
        trace_id=trace_id,
        stage="text_fsm_state_loaded",
        started_at=text_state_started_at,
        user_id=user_id,
        extra=f"state={current_state.value} context_keys={len(fsm_context)}",
    )

    # Interceptar comandos de reinicio / salida
    cmd_text = message_text.strip().lower()
    if cmd_text in {"/start", "/cancel", "/exit", "/salir", "/clear", "/reset"}:
        await fsm.reset()
        home_plan = _render_main_menu_plan()

        if cmd_text == "/start":
            start_command_at = time.perf_counter()
            welcome_text = (
                "¡Bienvenido! 🙂\n\n"
                "Negocio El Buen Trago.\n"
                "Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00.\n"
                "Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio.\n"
                "Ubicación: Santiago, Chile.\n\n"
                "¿En qué puedo ayudarte hoy?"
            )
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text=welcome_text,
                reply_markup=home_plan.reply_markup,
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
                menu_scope=home_plan.menu_scope,
                menu_stack=home_plan.menu_stack,
                expected_input=home_plan.expected_input,
                allow_numeric_input=home_plan.allow_numeric_input,
                next_state=home_plan.state,
            )
            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason="start_command",
            )
            _schedule_idle_prewarm(
                trace_id=trace_id,
                user_id=user_id,
                reason="start_command",
            )
            _log_timing(
                trace_id=trace_id,
                stage="start_command_responded",
                started_at=start_command_at,
                user_id=user_id,
            )
        else:
            reset_command_at = time.perf_counter()
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text="Sesión conversacional reiniciada y limpia. Tu carro de compra sigue conservado intacto. ¿En qué puedo ayudarte hoy?",
                reply_markup=home_plan.reply_markup,
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
                menu_scope=home_plan.menu_scope,
                menu_stack=home_plan.menu_stack,
                expected_input=home_plan.expected_input,
                allow_numeric_input=home_plan.allow_numeric_input,
                next_state=home_plan.state,
            )
            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason=f"reset_command:{cmd_text}",
            )
            _schedule_idle_prewarm(
                trace_id=trace_id,
                user_id=user_id,
                reason=f"reset_command:{cmd_text}",
            )
            _log_timing(
                trace_id=trace_id,
                stage="reset_command_responded",
                started_at=reset_command_at,
                user_id=user_id,
                extra=f"command={cmd_text}",
            )
        return

    if current_state == FSMState.IN_MENU:
        override_scope = menu_flow.try_resolve_scope_override(message_text)
        if override_scope is not None:
            override_stack = (
                [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE, override_scope]
                if override_scope.startswith("category:")
                else [MAIN_MENU_SCOPE, override_scope]
            )
            plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=override_scope,
                user_id=user_id,
                current_stack=override_stack[:-1],
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return

    if current_state == FSMState.AWAITING_QUANTITY:
        override_scope = menu_flow.try_resolve_scope_override(message_text)
        if override_scope is not None:
            override_stack = (
                [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE, override_scope]
                if override_scope.startswith("category:")
                else [MAIN_MENU_SCOPE, override_scope]
            )
            plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=override_scope,
                user_id=user_id,
                current_stack=override_stack[:-1],
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        pending_product_id = fsm_context.get("pending_product_id")
        if not isinstance(pending_product_id, str):
            plan = _render_main_menu_plan()
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        quantity = purchase_flow.parse_quantity(message_text)
        purchase_plan = (
            purchase_flow.render_confirmation_prompt(
                product_id=pending_product_id,
                quantity=quantity,
            )
            if quantity is not None
            else purchase_flow.render_quantity_prompt(
                product_id=pending_product_id,
                invalid_input=True,
            )
        )
        await _apply_purchase_plan(
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            fsm=fsm,
            plan=purchase_plan,
            trace_id=trace_id,
        )
        return

    if current_state == FSMState.AWAITING_CONFIRMATION:
        override_scope = menu_flow.try_resolve_scope_override(message_text)
        if override_scope is not None:
            override_stack = (
                [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE, override_scope]
                if override_scope.startswith("category:")
                else [MAIN_MENU_SCOPE, override_scope]
            )
            plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=override_scope,
                user_id=user_id,
                current_stack=override_stack[:-1],
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        normalized = cmd_text
        context = fsm_context
        pending_action = context.get("pending_action")
        pending_product_id = context.get("pending_product_id")
        pending_quantity = context.get("pending_quantity")
        if (
            normalized in {"si", "sí", "confirmar", "ok"}
            and pending_action == "checkout"
        ):
            purchase_plan = purchase_flow.confirm_checkout(external_user_id=user_id)
        elif (
            normalized in {"no", "volver", "cancelar"} and pending_action == "checkout"
        ):
            plan = menu_flow.render_cart_menu(
                current_stack=await fsm.get_menu_stack(),
                user_id=user_id,
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        elif (
            normalized in {"si", "sí", "confirmar", "ok"}
            and isinstance(pending_product_id, str)
            and isinstance(pending_quantity, int)
        ):
            purchase_plan = purchase_flow.confirm_add_to_cart(
                external_user_id=user_id,
                product_id=pending_product_id,
                quantity=pending_quantity,
            )
        elif normalized in {"no", "cambiar", "editar"} and isinstance(
            pending_product_id, str
        ):
            purchase_plan = purchase_flow.render_quantity_prompt(
                product_id=pending_product_id
            )
        elif isinstance(pending_product_id, str) and isinstance(pending_quantity, int):
            purchase_plan = purchase_flow.render_confirmation_prompt(
                product_id=pending_product_id,
                quantity=pending_quantity,
                invalid_input=True,
            )
        else:
            plan = _render_main_menu_plan()
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        await _apply_purchase_plan(
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            fsm=fsm,
            plan=purchase_plan,
            trace_id=trace_id,
        )
        return

    if current_state == FSMState.AWAITING_ORDER_ID:
        override_scope = menu_flow.try_resolve_scope_override(message_text)
        if override_scope is not None:
            override_stack = (
                [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE, override_scope]
                if override_scope.startswith("category:")
                else [MAIN_MENU_SCOPE, override_scope]
            )
            plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=override_scope,
                user_id=user_id,
                current_stack=override_stack[:-1],
            )
            await _apply_menu_plan(
                token=token,
                chat_id=chat_id,
                user_id=user_id,
                fsm=fsm,
                plan=plan,
                trace_id=trace_id,
            )
            return
        action = fsm_context.get("action", "search")
        db = SessionLocal()
        try:
            user = UserService(db).get_or_create(
                external_id=user_id, platform="telegram"
            )
            order_svc = OrderService(db)
            order_uuid = None
            try:
                # Intentar parsear el ID de pedido ingresado por el usuario
                raw_id = message_text.strip()
                if len(raw_id) > 8:
                    order_uuid = uuid.UUID(raw_id)
                else:
                    # Búsqueda parcial por prefijo si es un ID corto
                    user_orders = order_svc.list_user_orders(user.id)
                    matched_orders = [
                        o for o in user_orders if str(o.id).startswith(raw_id)
                    ]
                    if matched_orders:
                        order_uuid = matched_orders[0].id
            except ValueError:
                pass

            if order_uuid is None:
                # No se pudo encontrar por UUID ni por prefijo
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text="No encontré ningún pedido con ese ID. Por favor, asegúrate de escribir el ID completo o los primeros caracteres correctamente.",
                    reply_markup={
                        "inline_keyboard": [
                            [{"text": "↩️ Volver", "callback_data": "menu:back"}],
                            [
                                {
                                    "text": "🏠 Menú principal",
                                    "callback_data": "menu:home",
                                }
                            ],
                        ]
                    },
                    fsm=fsm,
                    trace_id=trace_id,
                    user_id=user_id,
                    expected_input=ExpectedInput.ORDER_ID,
                    next_state=FSMState.AWAITING_ORDER_ID,
                )
                return

            if action == "search":
                order = order_svc.get_order(order_uuid)
                if not order or order.user_id != user.id:
                    msg = "No encontré ese pedido."
                else:
                    status_emoji = {
                        "pending": "⏳ Pendiente",
                        "confirmed": "✅ Confirmado",
                        "preparing": "👨‍🍳 Preparando",
                        "ready": "📦 Listo para entrega",
                        "delivered": "🛵 Entregado",
                        "cancelled": "❌ Cancelado",
                    }.get(order.status, order.status)
                    date_str = (
                        order.created_at.strftime("%d/%m/%Y %H:%M")
                        if order.created_at
                        else "Fecha desconocida"
                    )
                    msg = (
                        f"📊 *Detalle del Pedido:*\n"
                        f"• ID: `{str(order.id)}`\n"
                        f"• Estado: {status_emoji}\n"
                        f"• Total: {_format_money(float(order.total_amount))}\n"
                        f"• Fecha: {date_str}\n\n"
                        f"Detalle de productos:\n"
                    )
                    for item in order.items:
                        msg += f" - {item.product.name} x{item.quantity} ({_format_money(float(item.total_price))})\n"

                # Volver al menú de pedidos
                stack = await fsm.get_menu_stack()
                plan = menu_flow.render_orders_menu(
                    current_stack=stack, user_id=user_id
                )
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=plan.reply_markup,
                    fsm=fsm,
                    trace_id=trace_id,
                    user_id=user_id,
                    menu_scope=plan.menu_scope,
                    menu_stack=plan.menu_stack,
                    expected_input=plan.expected_input,
                    allow_numeric_input=plan.allow_numeric_input,
                    next_state=plan.state,
                )
                return
            elif action == "cancel":
                try:
                    order_svc.cancel_order(order_uuid, user.id)
                    db.commit()
                    msg = f"✅ Pedido `{str(order_uuid)[:8]}...` cancelado exitosamente. Se ha restaurado el stock."
                except ValueError as e:
                    msg = f"❌ No se pudo cancelar el pedido: {str(e)}"

                stack = await fsm.get_menu_stack()
                plan = menu_flow.render_orders_menu(
                    current_stack=stack, user_id=user_id
                )
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=plan.reply_markup,
                    fsm=fsm,
                    trace_id=trace_id,
                    user_id=user_id,
                    menu_scope=plan.menu_scope,
                    menu_stack=plan.menu_stack,
                    expected_input=plan.expected_input,
                    allow_numeric_input=plan.allow_numeric_input,
                    next_state=plan.state,
                )
                return
        finally:
            db.close()

    # Si estamos esperando algo específico (ej: producto), podemos prefijar el texto
    if current_state == FSMState.AWAITING_PRODUCT_NAME:
        intent = fsm_context.get("intent")
        if intent == "consultar_stock":
            message_text = f"¿Tienen stock de {message_text}?"
        elif intent == "consultar_precio":
            message_text = f"¿Cuál es el precio de {message_text}?"
        await fsm.reset()  # Volver a IDLE tras procesar

    # Delega la lógica de negocio al Use Case
    metadata_started_at = time.perf_counter()
    metadata = await _build_telegram_llm_metadata(fsm)
    _log_timing(
        trace_id=trace_id,
        stage="llm_metadata_built",
        started_at=metadata_started_at,
        user_id=user_id,
        extra=f"keys={len(metadata)}",
    )
    cmd = ProcessMessageCommand(
        user_id=user_id,
        platform="telegram",
        message=message_text,
        metadata=metadata,
    )

    try:
        use_case_started_at = time.perf_counter()
        result = await process_message_uc.execute(cmd)
        response_text = result.response
        _log_timing(
            trace_id=trace_id,
            stage="process_message_uc_done",
            started_at=use_case_started_at,
            user_id=user_id,
            extra=f"response_empty={not bool(response_text)}",
        )
    except Exception as e:
        logger.error("Error processing telegram message: %s", e)
        response_text = "Ocurrió un error al procesar tu solicitud. Intenta nuevamente."

    # Si la respuesta es vacía, significa que el bot está pausado (Human Takeover activo)
    if not response_text:
        return

    # Enviar respuesta con el menú principal siempre activo si estamos en IDLE
    post_llm_state_started_at = time.perf_counter()
    current_state = await fsm.get_state()
    _log_timing(
        trace_id=trace_id,
        stage="post_llm_fsm_state_loaded",
        started_at=post_llm_state_started_at,
        user_id=user_id,
        extra=f"state={current_state.value}",
    )
    reply_markup = None
    menu_scope = None
    menu_stack = None
    expected_input = ExpectedInput.FREE_TEXT
    allow_numeric_input = False
    if current_state == FSMState.IDLE:
        home_plan = _render_main_menu_plan()
        reply_markup = home_plan.reply_markup
        menu_scope = home_plan.menu_scope
        menu_stack = home_plan.menu_stack
        expected_input = home_plan.expected_input
        allow_numeric_input = home_plan.allow_numeric_input
        current_state = home_plan.state
    elif current_state == FSMState.IN_MENU:
        current_scope = await fsm.get_menu_scope()
        current_stack = await fsm.get_menu_stack()
        if current_scope:
            current_plan = _render_menu_scope_plan(
                menu_flow=menu_flow,
                scope=current_scope,
                user_id=user_id,
                current_stack=current_stack[:-1] if current_stack else None,
            )
            reply_markup = current_plan.reply_markup
            menu_scope = current_plan.menu_scope
            menu_stack = current_stack or current_plan.menu_stack
            expected_input = current_plan.expected_input
            allow_numeric_input = current_plan.allow_numeric_input

    await send_menu_message(
        bot_token=token,
        chat_id=chat_id,
        text=response_text,
        reply_markup=reply_markup,
        fsm=fsm,
        trace_id=trace_id,
        user_id=user_id,
        menu_scope=menu_scope,
        menu_stack=menu_stack,
        expected_input=expected_input,
        allow_numeric_input=allow_numeric_input,
        next_state=current_state,
    )
    _log_timing(
        trace_id=trace_id,
        stage="text_message_done",
        started_at=text_started_at,
        user_id=user_id,
    )


async def process_telegram_update_background(
    token: str,
    chat_id: Any,
    user_id: str,
    message_obj: Any,
    callback_query: Any,
    callback_query_id: Any,
    msg_obj: Any,
    process_message_uc: Any,
    lock_key: str,
    lock_acquired: bool,
    redis_client: Any,
    trace_id: str,
    webhook_started_at: float | None = None,
) -> None:
    """Manejador en segundo plano para procesar la actualización y liberar el lock."""
    background_started_at = time.perf_counter()
    if webhook_started_at is not None:
        _log_timing(
            trace_id=trace_id,
            stage="background_started_after_webhook",
            started_at=webhook_started_at,
            user_id=user_id,
        )
    try:
        await _process_telegram_update_core(
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            message_obj=message_obj,
            callback_query=callback_query,
            callback_query_id=callback_query_id,
            msg_obj=msg_obj,
            process_message_uc=process_message_uc,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("Error in background telegram processing: %s", e)
    finally:
        if lock_acquired:
            if redis_client is not None:
                try:
                    await redis_client.delete(lock_key)
                except Exception as e:
                    logger.error(
                        "Failed to release Redis lock in background task: %s", e
                    )
            else:
                _local_locks.discard(user_id)
        _log_timing(
            trace_id=trace_id,
            stage="background_task_finished",
            started_at=background_started_at,
            user_id=user_id,
        )
        if webhook_started_at is not None:
            _log_timing(
                trace_id=trace_id,
                stage="webhook_to_background_finished",
                started_at=webhook_started_at,
                user_id=user_id,
            )


@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    process_message_uc: ProcessMessageUCDep,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Recibe updates de Telegram, valida el webhook y agenda su procesamiento asíncrono."""
    webhook_started_at = time.perf_counter()
    if token != settings.telegram_bot_token:
        logger.warning("Unauthorized webhook request with token: %s", token)
        raise HTTPException(403, "Forbidden: Invalid Telegram bot token")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse Telegram payload: %s", e)
        raise HTTPException(400, "Invalid JSON payload")

    # Detectar tipo de update: Mensaje o Callback Query
    message_obj = payload.get("message") or payload.get("edited_message")
    callback_query = payload.get("callback_query")

    if not message_obj and not callback_query:
        return {"status": "ok", "detail": "no message or callback in payload"}

    # Resolver chat_id y user_id de forma unificada
    chat_id = None
    user_id = None
    callback_query_id = None
    msg_obj = None
    if callback_query:
        from_obj = callback_query.get("from")
        msg_obj = callback_query.get("message")
        chat_id = msg_obj.get("chat", {}).get("id") if msg_obj else None
        user_id = str(from_obj.get("id")) if from_obj else str(chat_id)
        callback_query_id = callback_query.get("id")
    else:
        chat_obj = message_obj.get("chat")
        from_obj = message_obj.get("from")
        chat_id = chat_obj.get("id") if chat_obj else None
        user_id = str(from_obj.get("id") if from_obj else chat_id)

    if not user_id or not chat_id:
        return {"status": "ok", "detail": "invalid user_id or chat_id"}

    update_kind = "callback" if callback_query else "message"
    raw_update_id = payload.get("update_id")
    trace_id = (
        f"tg:{user_id}:{raw_update_id}"
        if raw_update_id is not None
        else f"tg:{user_id}:{int(time.time() * 1000)}"
    )
    _log_timing(
        trace_id=trace_id,
        stage="webhook_parsed",
        started_at=webhook_started_at,
        user_id=user_id,
        extra=f"kind={update_kind}",
    )

    # 1. Concurrency Lock: block concurrent requests from the same user_id (adquirido síncronamente)
    lock_key = f"lock:telegram:user:{user_id}"
    redis_client = get_redis_client()
    lock_acquired = False

    if redis_client is not None:
        try:
            lock_started_at = time.perf_counter()
            lock_acquired = await redis_client.set(lock_key, "locked", ex=20, nx=True)
            _log_timing(
                trace_id=trace_id,
                stage="redis_lock_checked",
                started_at=lock_started_at,
                user_id=user_id,
                extra=f"acquired={bool(lock_acquired)}",
            )
            if not lock_acquired:
                logger.warning(
                    "Concurrency warning: duplicate request from user %s blocked",
                    user_id,
                )
                if callback_query:
                    callback_query_id = callback_query.get("id")
                if callback_query_id:
                    background_tasks.add_task(
                        answer_telegram_callback_query,
                        bot_token=token,
                        callback_query_id=callback_query_id,
                        text="Procesando tu solicitud anterior, por favor espera...",
                        trace_id=trace_id,
                    )
                    _log_timing(
                        trace_id=trace_id,
                        stage="duplicate_callback_deferred",
                        started_at=webhook_started_at,
                        user_id=user_id,
                    )
                _log_timing(
                    trace_id=trace_id,
                    stage="webhook_response_ready",
                    started_at=webhook_started_at,
                    user_id=user_id,
                    extra=f"detail=duplicate_request_blocked kind={update_kind}",
                )
                return {"status": "ok", "detail": "duplicate request blocked"}
        except Exception as e:
            logger.exception("Redis concurrency lock error")
            raise RuntimeError("Failed to acquire Redis concurrency lock") from e
    else:
        lock_started_at = time.perf_counter()
        if user_id in _local_locks:
            logger.warning(
                "Local concurrency warning: duplicate request from user %s blocked",
                user_id,
            )
            if callback_query:
                callback_query_id = callback_query.get("id")
            if callback_query_id:
                background_tasks.add_task(
                    answer_telegram_callback_query,
                    bot_token=token,
                    callback_query_id=callback_query_id,
                    text="Procesando tu solicitud anterior, por favor espera...",
                    trace_id=trace_id,
                )
                _log_timing(
                    trace_id=trace_id,
                    stage="duplicate_callback_deferred",
                    started_at=webhook_started_at,
                    user_id=user_id,
                )
            _log_timing(
                trace_id=trace_id,
                stage="webhook_response_ready",
                started_at=webhook_started_at,
                user_id=user_id,
                extra=f"detail=duplicate_request_blocked kind={update_kind}",
            )
            return {"status": "ok", "detail": "duplicate request blocked"}
        _local_locks.add(user_id)
        lock_acquired = True
        _log_timing(
            trace_id=trace_id,
            stage="local_lock_checked",
            started_at=lock_started_at,
            user_id=user_id,
            extra="acquired=True",
        )

    # 2. Programar ejecución en segundo plano y responder de inmediato
    schedule_started_at = time.perf_counter()
    background_tasks.add_task(
        process_telegram_update_background,
        token=token,
        chat_id=chat_id,
        user_id=user_id,
        message_obj=message_obj,
        callback_query=callback_query,
        callback_query_id=callback_query_id,
        msg_obj=msg_obj if callback_query else None,
        process_message_uc=process_message_uc,
        lock_key=lock_key,
        lock_acquired=lock_acquired,
        redis_client=redis_client,
        trace_id=trace_id,
        webhook_started_at=webhook_started_at,
    )
    _log_timing(
        trace_id=trace_id,
        stage="background_task_scheduled",
        started_at=schedule_started_at,
        user_id=user_id,
        extra=f"kind={update_kind}",
    )

    _log_timing(
        trace_id=trace_id,
        stage="webhook_scheduled",
        started_at=webhook_started_at,
        user_id=user_id,
        extra=f"lock_acquired={lock_acquired} kind={update_kind}",
    )
    _log_timing(
        trace_id=trace_id,
        stage="webhook_response_ready",
        started_at=webhook_started_at,
        user_id=user_id,
        extra=f"detail=scheduled kind={update_kind}",
    )

    return {"status": "ok", "detail": "scheduled"}
