from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from config.database import SessionLocal
from infrastructure.channels.telegram_fsm import ExpectedInput, FSMState
from models.product import Product
from services.business_config_service import BusinessConfigService
from services.cart_service import CartService
from services.order_service import OrderService
from services.user_service import UserService


@dataclass(frozen=True)
class TelegramPurchasePlan:
    text: str
    reply_markup: dict | None
    state: FSMState
    expected_input: ExpectedInput
    menu_scope: str | None = None
    menu_stack: list[str] | None = None
    allow_numeric_input: bool = False
    context_updates: dict[str, Any] = field(default_factory=dict)


class TelegramPurchaseFlow:
    """Orquesta el subflujo producto -> cantidad -> confirmación en Telegram."""

    def __init__(
        self,
        *,
        product_cache: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._product_cache = product_cache or {}

    def render_quantity_prompt(
        self,
        *,
        product_id: str,
        invalid_input: bool = False,
    ) -> TelegramPurchasePlan:
        product = self._get_product_data(product_id)
        prefix = (
            "No entendí esa cantidad. Ingresa un número válido.\n\n"
            if invalid_input
            else ""
        )
        text = (
            f"{prefix}¿Cuántas unidades de {product['name']} quieres agregar?\n"
            f"Precio referencial: {self._format_money(product['price'])} por {product['unit_of_measure'] or 'un'}."
        )
        return TelegramPurchasePlan(
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "1", "callback_data": "qty_select:1"},
                        {"text": "2", "callback_data": "qty_select:2"},
                        {"text": "3", "callback_data": "qty_select:3"},
                    ],
                    [
                        {"text": "4", "callback_data": "qty_select:4"},
                        {"text": "5", "callback_data": "qty_select:5"},
                        {"text": "6", "callback_data": "qty_select:6"},
                    ],
                    [
                        {"text": "↩️ Volver", "callback_data": "menu:back"},
                        {"text": "🏠 Menú principal", "callback_data": "menu:home"},
                    ],
                ]
            },
            state=FSMState.AWAITING_QUANTITY,
            expected_input=ExpectedInput.QUANTITY,
            context_updates={
                "pending_product_id": str(product["id"]),
                "pending_product_name": product["name"],
                "pending_product_category": product["category"],
            },
        )

    def render_confirmation_prompt(
        self,
        *,
        product_id: str,
        quantity: int,
        invalid_input: bool = False,
    ) -> TelegramPurchasePlan:
        product = self._get_product_data(product_id)
        total = (
            float(product["price"]) if product["price"] is not None else 0.0
        ) * quantity
        prefix = (
            "No entendí tu respuesta. Confirma o cambia la cantidad.\n\n"
            if invalid_input
            else ""
        )
        text = (
            f"{prefix}Agregar {quantity} x {product['name']} al carrito.\n"
            f"Total estimado: {self._format_money(total)}."
        )
        return TelegramPurchasePlan(
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Confirmar",
                            "callback_data": "cart:add_confirm",
                        },
                        {
                            "text": "🔢 Cambiar cantidad",
                            "callback_data": "cart:change_quantity",
                        },
                    ],
                    [
                        {"text": "↩️ Volver", "callback_data": "menu:back"},
                        {"text": "🏠 Menú principal", "callback_data": "menu:home"},
                    ],
                ]
            },
            state=FSMState.AWAITING_CONFIRMATION,
            expected_input=ExpectedInput.CONFIRMATION,
            context_updates={
                "pending_product_id": str(product["id"]),
                "pending_product_name": product["name"],
                "pending_product_category": product["category"],
                "pending_quantity": quantity,
            },
        )

    def confirm_add_to_cart(
        self,
        *,
        external_user_id: str,
        product_id: str,
        quantity: int,
    ) -> TelegramPurchasePlan:
        db = SessionLocal()
        try:
            user = UserService(db).get_or_create(
                external_id=external_user_id,
                platform="telegram",
            )
            cart = CartService(db).add_to_cart(
                user_id=user.id,
                product_id=uuid.UUID(product_id),
                quantity=quantity,
            )
            db.commit()
            product = self._get_product_with_session(db, product_id)
            items_count = sum(int(item.quantity) for item in cart.items)
            text = (
                f"Agregué {quantity} x {product.name} al carrito.\n"
                f"Ahora tienes {items_count} item(s) en tu carrito."
            )
            return TelegramPurchasePlan(
                text=text,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "🛒 Ver carrito",
                                "callback_data": "menu:carrito",
                            },
                            {
                                "text": "🛍️ Seguir comprando",
                                "callback_data": "menu:categorias",
                            },
                        ],
                        [
                            {"text": "🏠 Menú principal", "callback_data": "menu:home"},
                        ],
                    ]
                },
                state=FSMState.IN_MENU,
                expected_input=ExpectedInput.MENU_SELECTION,
                menu_scope="menu:main",
                menu_stack=["menu:main"],
                allow_numeric_input=True,
                context_updates={
                    "pending_product_id": None,
                    "pending_product_name": None,
                    "pending_product_category": None,
                    "pending_quantity": None,
                },
            )
        finally:
            db.close()

    def render_checkout_confirmation(self) -> TelegramPurchasePlan:
        return TelegramPurchasePlan(
            text="Vas a generar un pedido con los productos de tu carrito. ¿Confirmas?",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Confirmar pedido",
                            "callback_data": "checkout:confirm",
                        },
                        {
                            "text": "🛒 Revisar carrito",
                            "callback_data": "menu:carrito",
                        },
                    ],
                    [
                        {"text": "V. ↩️ Volver", "callback_data": "menu:back"},
                        {"text": "M. 🏠 Menú principal", "callback_data": "menu:home"},
                    ],
                ]
            },
            state=FSMState.AWAITING_CONFIRMATION,
            expected_input=ExpectedInput.CONFIRMATION,
            context_updates={"pending_action": "checkout"},
        )

    def confirm_checkout(self, *, external_user_id: str) -> TelegramPurchasePlan:
        db = SessionLocal()
        try:
            user = UserService(db).get_or_create(
                external_id=external_user_id,
                platform="telegram",
            )
            order = OrderService(db).checkout_cart(user_id=user.id)
            estimated_minutes = (
                BusinessConfigService(db).get_config().estimated_attention_minutes
            )
            db.commit()
            text = self._build_checkout_confirmation_message(
                order_id=str(order.id),
                total_amount=float(order.total_amount or 0.0),
                estimated_attention_minutes=estimated_minutes,
            )
            return TelegramPurchasePlan(
                text=text,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "🛍️ Seguir comprando",
                                "callback_data": "menu:categorias",
                            },
                            {
                                "text": "M. 🏠 Menú principal",
                                "callback_data": "menu:home",
                            },
                        ]
                    ]
                },
                state=FSMState.IN_MENU,
                expected_input=ExpectedInput.MENU_SELECTION,
                menu_scope="menu:main",
                menu_stack=["menu:main"],
                allow_numeric_input=True,
                context_updates={
                    "pending_action": None,
                    "pending_product_id": None,
                    "pending_product_name": None,
                    "pending_product_category": None,
                    "pending_quantity": None,
                },
            )
        finally:
            db.close()

    def clear_cart(self, *, external_user_id: str) -> TelegramPurchasePlan:
        db = SessionLocal()
        try:
            user = UserService(db).get_or_create(
                external_id=external_user_id,
                platform="telegram",
            )
            CartService(db).clear_cart(user.id)
            db.commit()
            return TelegramPurchasePlan(
                text="Vacié tu carrito. Puedes seguir explorando productos cuando quieras.",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "🛍️ Seguir comprando",
                                "callback_data": "menu:categorias",
                            },
                            {
                                "text": "M. 🏠 Menú principal",
                                "callback_data": "menu:home",
                            },
                        ]
                    ]
                },
                state=FSMState.IN_MENU,
                expected_input=ExpectedInput.MENU_SELECTION,
                menu_scope="menu:main",
                menu_stack=["menu:main"],
                allow_numeric_input=True,
            )
        finally:
            db.close()

    @staticmethod
    def parse_quantity(text: str) -> int | None:
        stripped = text.strip()
        if not stripped.isdigit():
            return None
        quantity = int(stripped)
        if quantity <= 0 or quantity > 99:
            return None
        return quantity

    def _get_product_data(self, product_id: str) -> dict[str, Any]:
        cached = self._product_cache.get(product_id)
        if cached is not None:
            return cached
        product = self._get_product(product_id)
        return self._product_to_data(product)

    def _get_product(self, product_id: str) -> Product:
        db = SessionLocal()
        try:
            return self._get_product_with_session(db, product_id)
        finally:
            db.close()

    @staticmethod
    def _product_to_data(product: Product) -> dict[str, Any]:
        return {
            "id": str(product.id),
            "name": product.name,
            "price": float(product.price) if product.price is not None else 0.0,
            "stock": int(product.stock) if product.stock is not None else 0,
            "category": product.category,
            "unit_of_measure": product.unit_of_measure,
        }

    @staticmethod
    def _get_product_with_session(db, product_id: str) -> Product:
        product = db.query(Product).filter(Product.id == uuid.UUID(product_id)).first()
        if product is None:
            raise ValueError("Product not found")
        return product

    @staticmethod
    def _format_money(value: object) -> str:
        amount = float(value) if value is not None else 0.0
        return f"${amount:,.0f}"

    @classmethod
    def _build_checkout_confirmation_message(
        cls,
        *,
        order_id: str,
        total_amount: float,
        estimated_attention_minutes: int,
    ) -> str:
        parts = [
            "Pedido generado.",
            "",
            f"Pedido: {order_id or 'sin identificador'}",
            f"Total: {cls._format_money(total_amount)}",
            f"Tiempo estimado de atención: {estimated_attention_minutes} minutos.",
            "Te contactaremos para coordinar pago, envío u otros detalles.",
        ]
        return "\n".join(parts)
