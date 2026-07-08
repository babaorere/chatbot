from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from config.database import SessionLocal
from infrastructure.channels.telegram_fsm import ExpectedInput, FSMState
from services.category_service import CategoryService, normalize_category_name
from services.telegram_service import build_main_menu

MAIN_MENU_SCOPE = "menu:main"
CATEGORIES_MENU_SCOPE = "menu:categories"
PROMOTIONS_MENU_SCOPE = "menu:promotions"
BEST_SELLERS_MENU_SCOPE = "menu:best_sellers"
FAVORITES_MENU_SCOPE = "menu:favorites"
CART_MENU_SCOPE = "menu:cart"
PEDIDOS_MENU_SCOPE = "menu:pedidos"
CATEGORY_SCOPE_PREFIX = "category:"


@dataclass(frozen=True)
class TelegramMenuPlan:
    text: str
    reply_markup: dict | None
    state: FSMState
    menu_scope: str | None = None
    menu_stack: list[str] = field(default_factory=list)
    expected_input: ExpectedInput = ExpectedInput.FREE_TEXT
    allow_numeric_input: bool = False
    context_updates: dict[str, Any] = field(default_factory=dict)


class TelegramMenuFlow:
    """Construye planes de navegación Telegram sin ejecutar side effects."""

    def __init__(
        self,
        *,
        promotions_builder: Callable[[], tuple[str, list[str]]],
        best_sellers_builder: Callable[[], tuple[str, list[str]]],
        favorites_builder: Callable[[], tuple[str, list[str]]],
        cart_builder: Callable[[str], tuple[str, bool]],
        orders_builder: Callable[[str], tuple[str, bool]] | None = None,
        categories_cache: list[dict[str, Any]] | None = None,
        products_cache: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._promotions_builder = promotions_builder
        self._best_sellers_builder = best_sellers_builder
        self._favorites_builder = favorites_builder
        self._cart_builder = cart_builder
        self._orders_builder = orders_builder
        self._categories_cache = categories_cache or []
        self._products_cache = products_cache or {}

    def render_scope(
        self,
        *,
        scope: str,
        user_id: str,
        current_stack: list[str] | None = None,
    ) -> TelegramMenuPlan:
        if scope == MAIN_MENU_SCOPE:
            return self.render_main_menu()
        if scope == CATEGORIES_MENU_SCOPE:
            return self.render_categories_menu(current_stack=current_stack or [])
        if scope == PROMOTIONS_MENU_SCOPE:
            return self.render_promotions_menu(
                current_stack=current_stack or [], user_id=user_id
            )
        if scope == BEST_SELLERS_MENU_SCOPE:
            return self.render_best_sellers_menu(current_stack=current_stack or [])
        if scope == FAVORITES_MENU_SCOPE:
            return self.render_favorites_menu(current_stack=current_stack or [])
        if scope == CART_MENU_SCOPE:
            return self.render_cart_menu(
                current_stack=current_stack or [], user_id=user_id
            )
        if scope == PEDIDOS_MENU_SCOPE:
            return self.render_orders_menu(
                current_stack=current_stack or [], user_id=user_id
            )
        if scope.startswith(CATEGORY_SCOPE_PREFIX):
            slug = scope.split(":", 1)[1]
            return self.render_category_detail(
                category_slug=slug,
                current_stack=current_stack or [],
            )
        raise ValueError(f"Unsupported telegram menu scope: {scope}")

    def render_main_menu(self) -> TelegramMenuPlan:
        return TelegramMenuPlan(
            text="¿En qué puedo ayudarte hoy?",
            reply_markup=build_main_menu(False),
            state=FSMState.IN_MENU,
            menu_scope=MAIN_MENU_SCOPE,
            menu_stack=[MAIN_MENU_SCOPE],
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_categories_menu(self, *, current_stack: list[str]) -> TelegramMenuPlan:
        buttons = []
        idx = 1
        for i in range(0, len(self._categories_cache), 2):
            row = []
            for category in self._categories_cache[i : i + 2]:
                row.append(
                    {
                        "text": f"{idx}. 🏷️ {category['name']}",
                        "callback_data": f"cat_select:{category['slug']}",
                    }
                )
                idx += 1
            buttons.append(row)

        # Volver y Menú principal
        buttons.append(
            [
                {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
            ]
        )
        return TelegramMenuPlan(
            text="Selecciona una categoría.",
            reply_markup={"inline_keyboard": buttons},
            state=FSMState.IN_MENU,
            menu_scope=CATEGORIES_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, CATEGORIES_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_category_detail(
        self,
        *,
        category_slug: str,
        current_stack: list[str],
    ) -> TelegramMenuPlan:
        # Encontrar categoría en la cache
        category = next(
            (c for c in self._categories_cache if c["slug"] == category_slug), None
        )
        if category is None:
            return TelegramMenuPlan(
                text="No encontré esa categoría. Elige otra opción.",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                            {
                                "text": "M. 🏠 Menú principal",
                                "callback_data": "menu:home",
                            },
                        ]
                    ]
                },
                state=FSMState.IN_MENU,
                menu_scope=CATEGORIES_MENU_SCOPE,
                menu_stack=self._push_scope([MAIN_MENU_SCOPE], CATEGORIES_MENU_SCOPE),
                expected_input=ExpectedInput.MENU_SELECTION,
                allow_numeric_input=True,
            )

        products = self._products_cache.get(category["name"], [])
        buttons: list[list[dict[str, str]]] = []
        idx = 1
        if not products:
            text = f"No hay productos disponibles en '{category['name']}' por ahora."
        else:
            lines = [f"Disponibles en {category['name']}:", ""]
            for product in products:
                price = product["price"]
                stock = product["stock"]
                lines.append(f"• {product['name']} - ${price:,.0f} | Stock: {stock}")
                buttons.append(
                    [
                        {
                            "text": f"{idx}. Agregar {product['name']}",
                            "callback_data": f"product_select:{product['id']}",
                        }
                    ]
                )
                idx += 1
            text = "\n".join(lines)

        # Volver y Menú principal
        buttons.append(
            [
                {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
            ]
        )

        return TelegramMenuPlan(
            text=text,
            reply_markup={"inline_keyboard": buttons},
            state=FSMState.IN_MENU,
            menu_scope=f"{CATEGORY_SCOPE_PREFIX}{category['slug']}",
            menu_stack=self._push_scope(
                current_stack or [MAIN_MENU_SCOPE, CATEGORIES_MENU_SCOPE],
                f"{CATEGORY_SCOPE_PREFIX}{category['slug']}",
            ),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
            context_updates={
                "selected_category": category["name"],
                "visible_product_names": [product["name"] for product in products],
            },
        )

    def render_promotions_menu(
        self,
        *,
        current_stack: list[str],
        user_id: str,
    ) -> TelegramMenuPlan:
        built = self._promotions_builder()
        text = built[0] if isinstance(built, tuple) else built
        return TelegramMenuPlan(
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                        {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
                    ]
                ]
            },
            state=FSMState.IN_MENU,
            menu_scope=PROMOTIONS_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, PROMOTIONS_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_best_sellers_menu(self, *, current_stack: list[str]) -> TelegramMenuPlan:
        built = self._best_sellers_builder()
        text = built[0] if isinstance(built, tuple) else built
        return TelegramMenuPlan(
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                        {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
                    ]
                ]
            },
            state=FSMState.IN_MENU,
            menu_scope=BEST_SELLERS_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, BEST_SELLERS_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_favorites_menu(self, *, current_stack: list[str]) -> TelegramMenuPlan:
        built = self._favorites_builder()
        text = built[0] if isinstance(built, tuple) else built
        return TelegramMenuPlan(
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                        {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
                    ]
                ]
            },
            state=FSMState.IN_MENU,
            menu_scope=FAVORITES_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, FAVORITES_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_cart_menu(
        self, *, current_stack: list[str], user_id: str
    ) -> TelegramMenuPlan:
        text, has_items = self._cart_builder(user_id)
        idx = 1
        if has_items:
            action_rows = [
                [
                    {
                        "text": f"{idx}. 🧾 Generar pedido",
                        "callback_data": "cart:start_checkout",
                    },
                    {
                        "text": f"{idx + 1}. 🛍️ Seguir comprando",
                        "callback_data": "menu:categorias",
                    },
                ],
                [
                    {
                        "text": f"{idx + 2}. 🗑️ Vaciar carrito",
                        "callback_data": "cart:clear",
                    }
                ],
            ]
        else:
            action_rows = [
                [
                    {
                        "text": f"{idx}. 🛍️ Seguir comprando",
                        "callback_data": "menu:categorias",
                    }
                ]
            ]

        action_rows.append(
            [
                {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
            ]
        )

        return TelegramMenuPlan(
            text=text,
            reply_markup={"inline_keyboard": action_rows},
            state=FSMState.IN_MENU,
            menu_scope=CART_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, CART_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def render_orders_menu(
        self, *, current_stack: list[str], user_id: str
    ) -> TelegramMenuPlan:
        text = "No pudimos cargar tus pedidos en este momento."
        has_orders = False
        if self._orders_builder:
            text, has_orders = self._orders_builder(user_id)

        action_rows = []
        idx = 1
        if has_orders:
            action_rows.append(
                [
                    {
                        "text": f"{idx}. 🔍 Buscar Pedido",
                        "callback_data": "menu:buscar_pedido_prompt",
                    },
                    {
                        "text": f"{idx + 1}. ❌ Cancelar Pedido",
                        "callback_data": "menu:cancelar_pedido_prompt",
                    },
                ]
            )

        action_rows.append(
            [
                {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
            ]
        )

        return TelegramMenuPlan(
            text=text,
            reply_markup={"inline_keyboard": action_rows},
            state=FSMState.IN_MENU,
            menu_scope=PEDIDOS_MENU_SCOPE,
            menu_stack=self._push_scope(current_stack, PEDIDOS_MENU_SCOPE),
            expected_input=ExpectedInput.MENU_SELECTION,
            allow_numeric_input=True,
        )

    def resolve_back_scope(self, current_stack: list[str]) -> str:
        if len(current_stack) >= 2:
            return current_stack[-2]
        return MAIN_MENU_SCOPE

    def try_resolve_category_override(self, text: str) -> str | None:
        normalized_text = normalize_category_name(text)
        for category in self._categories_cache:
            name = category.get("name")
            slug = category.get("slug")
            if (
                isinstance(name, str)
                and isinstance(slug, str)
                and normalize_category_name(name) in normalized_text
            ):
                return f"{CATEGORY_SCOPE_PREFIX}{slug}"

        db = SessionLocal()
        try:
            for category in CategoryService(db).list_categories():
                if normalize_category_name(category.name) in normalized_text:
                    return f"{CATEGORY_SCOPE_PREFIX}{category.slug}"
            return None
        finally:
            db.close()

    def try_resolve_scope_override(self, text: str) -> str | None:
        normalized_text = normalize_category_name(text)
        keyword_map = {
            "categoria": CATEGORIES_MENU_SCOPE,
            "catalogo": CATEGORIES_MENU_SCOPE,
            "promo": PROMOTIONS_MENU_SCOPE,
            "promocione": PROMOTIONS_MENU_SCOPE,
            "carrito": CART_MENU_SCOPE,
            "carro": CART_MENU_SCOPE,
            "favorito": FAVORITES_MENU_SCOPE,
            "recomendado": BEST_SELLERS_MENU_SCOPE,
            "pedido": PEDIDOS_MENU_SCOPE,
            "compra": PEDIDOS_MENU_SCOPE,
            "cerveza": None,
        }
        for keyword, scope in keyword_map.items():
            if keyword in normalized_text and scope is not None:
                return scope
        return self.try_resolve_category_override(text)

    @staticmethod
    def _push_scope(current_stack: list[str], scope: str) -> list[str]:
        base = [item for item in current_stack if item]
        if not base:
            base = [MAIN_MENU_SCOPE]
        if base[-1] == scope:
            return base
        return [*base, scope]

    @staticmethod
    def _navigation_rows() -> list[list[dict[str, str]]]:
        return [
            [
                {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
            ]
        ]

    def _navigation_markup(self) -> dict[str, Any]:
        return {"inline_keyboard": self._navigation_rows()}
