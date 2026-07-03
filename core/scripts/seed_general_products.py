from __future__ import annotations

import logging
import sys
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import text

# Permitir importación del módulo core
sys.path.insert(0, ".")

from config.database import SessionLocal
from models.category import Category
from models.product import Product

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_general_products")

_PRESENTATION_PATTERN = re.compile(
    r"^\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>ml|cc|l|lt|lts|litro|litros|g|gr|kg)?\s*$",
    re.IGNORECASE,
)

GENERAL_PRODUCTS = [
    # 5 presentaciones diferentes del mismo producto (Pisco Mistral)
    {
        "sku": "MISTRAL-35-200",
        "name": "Pisco Mistral 35° 200cc",
        "presentation_family": "Pisco Mistral",
        "description": "Pisco Mistral tradicional de 35 grados en presentación de 200cc.",
        "price": 2990.0,
        "cost": 1800.0,
        "stock": 40,
        "category": "General",
        "format": "200cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-35-350",
        "name": "Pisco Mistral 35° 350cc",
        "presentation_family": "Pisco Mistral",
        "description": "Pisco Mistral tradicional de 35 grados en presentación de 350cc.",
        "price": 4290.0,
        "cost": 2600.0,
        "stock": 32,
        "category": "General",
        "format": "350cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-35-500",
        "name": "Pisco Mistral 35° 500cc",
        "presentation_family": "Pisco Mistral",
        "description": "Pisco Mistral tradicional de 35 grados en presentación de 500cc.",
        "price": 5690.0,
        "cost": 3700.0,
        "stock": 28,
        "category": "General",
        "format": "500cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-35-750",
        "name": "Pisco Mistral 35° 750cc",
        "presentation_family": "Pisco Mistral",
        "description": "Pisco Mistral tradicional de 35 grados en presentación de 750cc.",
        "price": 7290.0,
        "cost": 5000.0,
        "stock": 35,
        "category": "General",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-35-1L",
        "name": "Pisco Mistral 35° 1L",
        "presentation_family": "Pisco Mistral",
        "description": "Pisco Mistral tradicional de 35 grados en presentación familiar de 1 Litro.",
        "price": 8990.0,
        "cost": 6200.0,
        "stock": 20,
        "category": "General",
        "format": "1L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    # 5 productos adicionales diferentes en la categoría General
    {
        "sku": "COCA-350",
        "name": "Coca-Cola Original Lata 350cc",
        "description": "Bebida gaseosa refrescante sabor original en lata individual.",
        "price": 990.0,
        "cost": 600.0,
        "stock": 100,
        "category": "General",
        "format": "Lata 350cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.39,
        "taxes": 0.19,
    },
    {
        "sku": "HEIN-330",
        "name": "Cerveza Heineken Botella 330cc",
        "description": "Cerveza Heineken Lager premium en botella individual de vidrio.",
        "price": 1290.0,
        "cost": 850.0,
        "stock": 80,
        "category": "General",
        "format": "330cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.34,
        "taxes": 0.19,
    },
    {
        "sku": "RED-BULL-250",
        "name": "Bebida Energética Red Bull 250cc",
        "description": "Bebida energética Red Bull clásica en lata de 250cc.",
        "price": 1890.0,
        "cost": 1200.0,
        "stock": 50,
        "category": "General",
        "format": "250cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.36,
        "taxes": 0.19,
    },
    {
        "sku": "GIN-BEEFEATER-750",
        "name": "Gin Beefeater London Dry 750cc",
        "description": "Gin importado Beefeater London Dry destilado tradicional de 750cc.",
        "price": 16990.0,
        "cost": 11500.0,
        "stock": 12,
        "category": "General",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.32,
        "taxes": 0.19,
    },
    {
        "sku": "PAPA-LAY-TARRO",
        "name": "Papas Fritas Lays Tarro 135g",
        "description": "Papas fritas Lays en tarro rígido sabor original de 135 gramos.",
        "price": 2190.0,
        "cost": 1400.0,
        "stock": 45,
        "category": "General",
        "format": "135g",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.36,
        "taxes": 0.19,
    },
]


@dataclass(frozen=True)
class PresentationCollision:
    normalized_value: str
    products: tuple[dict[str, object], ...]


class PresentationValidationError(ValueError):
    pass


def _normalize_presentation(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "")


def _normalize_family(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _presentation_to_ml(value: object) -> int | None:
    normalized = str(value).strip().lower()
    match = _PRESENTATION_PATTERN.match(normalized)
    if not match:
        return None

    amount = float(match.group("amount").replace(",", "."))
    unit = (match.group("unit") or "").lower()
    if unit in {"l", "lt", "lts", "litro", "litros"}:
        return int(round(amount * 1000))
    if unit in {"ml", "cc"}:
        return int(round(amount))
    return None


def _find_presentation_collisions(
    products: Iterable[dict[str, object]],
) -> list[PresentationCollision]:
    grouped: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for product in products:
        family = _normalize_family(
            product.get("presentation_family")
            or product.get("family")
            or product.get("name")
        )
        presentation = _normalize_presentation(product.get("format"))
        if not presentation:
            continue
        ml_value = _presentation_to_ml(product.get("format"))
        normalized_value = f"{ml_value}ml" if ml_value is not None else presentation
        grouped[family][normalized_value].append(product)

    collisions: list[PresentationCollision] = []
    for family, family_groups in grouped.items():
        for normalized_value, items in family_groups.items():
            if len(items) > 1:
                collisions.append(
                    PresentationCollision(
                        normalized_value=f"{family}:{normalized_value}",
                        products=tuple(items),
                    )
                )
    return collisions


def _raise_for_similar_presentations(products: Iterable[dict[str, object]]) -> None:
    collisions = _find_presentation_collisions(products)
    if not collisions:
        return

    collision_details: list[str] = []
    for collision in collisions:
        product_labels = ", ".join(
            f"{item['sku']}={item['format']}" for item in collision.products
        )
        collision_details.append(
            f"{collision.normalized_value} ({len(collision.products)}): {product_labels}"
        )
        logger.warning(
            "Colisión matemática detectada en presentaciones equivalentes "
            "[normalized=%s, count=%s]: %s",
            collision.normalized_value,
            len(collision.products),
            product_labels,
        )
    raise PresentationValidationError(
        "El seed fue bloqueado por presentaciones equivalentes duplicadas: "
        + "; ".join(collision_details)
    )


def _reset_existing_general_catalog(db) -> None:
    db.execute(
        text("DELETE FROM cart_items WHERE product_id IN (SELECT id FROM products);")
    )
    db.execute(
        text("DELETE FROM order_items WHERE product_id IN (SELECT id FROM products);")
    )
    db.execute(text("DELETE FROM products;"))


def seed_general(reset_existing_products: bool = True) -> None:
    db = None
    try:
        _raise_for_similar_presentations(GENERAL_PRODUCTS)

        db = SessionLocal()

        logger.info("Verificando existencia de la categoría 'General'...")
        category = db.query(Category).filter(Category.name == "General").first()
        if not category:
            category = Category(name="General", slug="general", is_system=True)
            db.add(category)
            db.flush()
            logger.info("Categoría 'General' creada exitosamente.")
        else:
            logger.info("Categoría 'General' ya existe.")

        if reset_existing_products:
            logger.info(
                "Limpiando catálogo existente para sembrar productos generales..."
            )
            _reset_existing_general_catalog(db)
            db.flush()

        for p_data in GENERAL_PRODUCTS:
            sku = p_data["sku"]
            product = db.query(Product).filter(Product.sku == sku).first()

            if not product:
                product = Product(
                    sku=sku,
                    name=p_data["name"],
                    description=p_data["description"],
                    price=Decimal(str(p_data["price"])),
                    cost=Decimal(str(p_data["cost"])),
                    stock=p_data["stock"],
                    category="General",
                    format=p_data["format"],
                    unit_of_measure=p_data["unit_of_measure"],
                    is_available=p_data["is_available"],
                    margin=Decimal(str(p_data["margin"])),
                    taxes=Decimal(str(p_data["taxes"])),
                )
                db.add(product)
                logger.info(
                    "Producto general creado: %s (SKU: %s)", p_data["name"], sku
                )
            else:
                product.name = p_data["name"]
                product.description = p_data["description"]
                product.price = Decimal(str(p_data["price"]))
                product.cost = Decimal(str(p_data["cost"]))
                product.stock = p_data["stock"]
                product.category = "General"
                product.format = p_data["format"]
                product.unit_of_measure = p_data["unit_of_measure"]
                product.is_available = p_data["is_available"]
                product.margin = Decimal(str(p_data["margin"]))
                product.taxes = Decimal(str(p_data["taxes"]))
                logger.info(
                    "Producto general actualizado: %s (SKU: %s)", p_data["name"], sku
                )

        db.commit()
        logger.info("Sembrado de productos generales finalizado exitosamente.")
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error("Error durante el sembrado de productos generales: %s", e)
        raise
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    seed_general()
