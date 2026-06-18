from __future__ import annotations

import logging
import uuid
from sqlalchemy.orm import Session
from models.cart import Cart, CartItem
from models.product import Product

logger = logging.getLogger(__name__)


class CartService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_cart(self, user_id: int) -> Cart:
        try:
            cart = self.db.query(Cart).filter(Cart.user_id == user_id).first()
            if not cart:
                cart = Cart(user_id=user_id)
                self.db.add(cart)
                self.db.flush()
                self.db.refresh(cart)
            return cart
        except Exception as e:
            logger.error(
                "CartService.get_or_create_cart failed [user_id=%s]: %s", user_id, e
            )
            raise

    def add_to_cart(
        self, user_id: int, product_id: uuid.UUID, quantity: int = 1
    ) -> Cart:
        try:
            cart = self.get_or_create_cart(user_id)

            product = self.db.query(Product).filter(Product.id == product_id).first()
            if not product:
                raise ValueError("Product not found")
            if not product.is_available:
                raise ValueError("Product is not available for purchase")

            item = (
                self.db.query(CartItem)
                .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
                .first()
            )

            if item:
                item.quantity += quantity
            else:
                item = CartItem(
                    cart_id=cart.id, product_id=product_id, quantity=quantity
                )
                self.db.add(item)

            self.db.flush()
            self.db.refresh(cart)
            return cart
        except Exception as e:
            logger.error("CartService.add_to_cart failed [user_id=%s]: %s", user_id, e)
            raise

    def remove_from_cart(
        self, user_id: int, product_id: uuid.UUID, quantity: int | None = None
    ) -> Cart:
        try:
            cart = self.get_or_create_cart(user_id)
            item = (
                self.db.query(CartItem)
                .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
                .first()
            )

            if item:
                if quantity is not None and item.quantity > quantity:
                    item.quantity -= quantity
                else:
                    self.db.delete(item)
                self.db.flush()

            self.db.refresh(cart)
            return cart
        except Exception as e:
            logger.error(
                "CartService.remove_from_cart failed [user_id=%s]: %s", user_id, e
            )
            raise

    def clear_cart(self, user_id: int) -> None:
        try:
            cart = self.get_or_create_cart(user_id)
            cart.items.clear()
            self.db.flush()
        except Exception as e:
            logger.error("CartService.clear_cart failed [user_id=%s]: %s", user_id, e)
            raise
