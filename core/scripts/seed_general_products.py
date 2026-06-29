from __future__ import annotations

import logging
import sys
from decimal import Decimal

# Permitir importación del módulo core
sys.path.insert(0, ".")

from config.database import SessionLocal
from models.category import Category
from models.product import Product

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_general_products")

GENERAL_PRODUCTS = [
    # 5 Presentaciones diferentes del mismo producto (Pisco Mistral)
    {
        "sku": "MISTRAL-35-750",
        "name": "Pisco Mistral 35° 750cc",
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
    {
        "sku": "MISTRAL-40-750",
        "name": "Pisco Mistral 40° 750cc",
        "description": "Pisco Mistral Añejado en Roble de 40 grados en presentación de 750cc.",
        "price": 8490.0,
        "cost": 5800.0,
        "stock": 25,
        "category": "General",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-40-1L",
        "name": "Pisco Mistral 40° 1L",
        "description": "Pisco Mistral Especial Añejado de 40 grados en presentación de 1 Litro.",
        "price": 10490.0,
        "cost": 7200.0,
        "stock": 15,
        "category": "General",
        "format": "1L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "MISTRAL-46-750",
        "name": "Pisco Mistral Nobel 46° 750cc",
        "description": "Edición especial Pisco Mistral Nobel de 46 grados añejado en barricas de roble.",
        "price": 15990.0,
        "cost": 11000.0,
        "stock": 10,
        "category": "General",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    # 5 Productos adicionales diferentes en la categoría General
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


def seed_general() -> None:
    db = SessionLocal()
    try:
        logger.info("Verificando existencia de la categoría 'General'...")
        category = db.query(Category).filter(Category.name == "General").first()
        if not category:
            category = Category(name="General", slug="general", is_system=True)
            db.add(category)
            db.flush()
            logger.info("Categoría 'General' creada exitosamente.")
        else:
            logger.info("Categoría 'General' ya existe.")

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
                logger.info("Producto general creado: %s (SKU: %s)", p_data["name"], sku)
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
                logger.info("Producto general actualizado: %s (SKU: %s)", p_data["name"], sku)

        db.commit()
        logger.info("Sembrado de productos generales finalizado exitosamente.")
    except Exception as e:
        db.rollback()
        logger.error("Error durante el sembrado de productos generales: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_general()
