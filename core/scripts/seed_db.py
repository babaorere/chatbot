from __future__ import annotations

import logging
import sys
from decimal import Decimal

# Permitir importación del módulo core
sys.path.insert(0, ".")

from config.database import SessionLocal
from models.category import Category
from models.product import Product
from services.category_service import slugify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_db")

CATEGORIES_TO_SEED = [
    "Bebidas",
    "Cervezas",
    "Licores",
    "Piscos",
    "Vinos",
]

PRODUCTS_TO_SEED = [
    # Bebidas
    {
        "sku": "COCA-15L",
        "name": "Coca-Cola Original 1.5L",
        "description": "Bebida gaseosa refrescante sabor original.",
        "price": 1890.0,
        "cost": 1200.0,
        "stock": 50,
        "category": "Bebidas",
        "format": "1.5L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.36,
        "taxes": 0.19,
    },
    {
        "sku": "SPRITE-15L",
        "name": "Sprite Zero 1.5L",
        "description": "Bebida gaseosa sabor lima-limón sin azúcar.",
        "price": 1890.0,
        "cost": 1200.0,
        "stock": 30,
        "category": "Bebidas",
        "format": "1.5L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.36,
        "taxes": 0.19,
    },
    {
        "sku": "AGUA-16L",
        "name": "Agua Mineral Cachantun Con Gas 1.6L",
        "description": "Agua mineral natural gasificada de manantial.",
        "price": 1190.0,
        "cost": 700.0,
        "stock": 40,
        "category": "Bebidas",
        "format": "1.6L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.41,
        "taxes": 0.19,
    },
    {
        "sku": "TONICA-15L",
        "name": "Tónica Schweppes 1.5L",
        "description": "Agua tónica ideal para mixología y gin tonic.",
        "price": 1990.0,
        "cost": 1300.0,
        "stock": 25,
        "category": "Bebidas",
        "format": "1.5L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.34,
        "taxes": 0.19,
    },
    # Cervezas
    {
        "sku": "HEIN-6PACK",
        "name": "Cerveza Heineken Lager Pack 6x330cc",
        "description": "Pack de 6 botellas de cerveza premium lager holandesa.",
        "price": 6490.0,
        "cost": 4500.0,
        "stock": 20,
        "category": "Cervezas",
        "format": "Pack 6x330cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.30,
        "taxes": 0.19,
    },
    {
        "sku": "CORONA-355",
        "name": "Cerveza Corona Extra 355cc",
        "description": "Botella individual de cerveza mexicana suave y refrescante.",
        "price": 1290.0,
        "cost": 850.0,
        "stock": 60,
        "category": "Cervezas",
        "format": "355cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.34,
        "taxes": 0.19,
    },
    {
        "sku": "KROSS-STOUT",
        "name": "Cerveza Kross Stout 330cc",
        "description": "Cerveza artesanal chilena tipo Stout con notas a café y chocolate.",
        "price": 1890.0,
        "cost": 1250.0,
        "stock": 18,
        "category": "Cervezas",
        "format": "330cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.33,
        "taxes": 0.19,
    },
    {
        "sku": "KUNST-TORO",
        "name": "Cerveza Kunstmann Torobayo 330cc",
        "description": "Cerveza artesanal chilena de Valdivia, ámbar de sabor balanceado.",
        "price": 1990.0,
        "cost": 1350.0,
        "stock": 24,
        "category": "Cervezas",
        "format": "330cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.32,
        "taxes": 0.19,
    },
    # Licores
    {
        "sku": "JW-BLACK-750",
        "name": "Whisky Johnnie Walker Black Label 750cc",
        "description": "Whisky escocés de mezcla premium de 12 años.",
        "price": 28990.0,
        "cost": 20000.0,
        "stock": 10,
        "category": "Licores",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "RON-PAMPERO-700",
        "name": "Ron Pampero Aniversario Reserva 700cc",
        "description": "Ron añejo premium venezolano en saco de cuero tradicional.",
        "price": 24990.0,
        "cost": 17000.0,
        "stock": 8,
        "category": "Licores",
        "format": "700cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "GIN-TANQ-750",
        "name": "Gin Tanqueray London Dry 750cc",
        "description": "Gin clásico destilado con botánicos seleccionados.",
        "price": 16490.0,
        "cost": 11000.0,
        "stock": 15,
        "category": "Licores",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.33,
        "taxes": 0.19,
    },
    {
        "sku": "VODKA-ABSOLUT-750",
        "name": "Vodka Absolut Blue 750cc",
        "description": "Vodka sueco puro de grano de alta calidad.",
        "price": 10990.0,
        "cost": 7500.0,
        "stock": 22,
        "category": "Licores",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    # Piscos
    {
        "sku": "MISTRAL-35-1L",
        "name": "Pisco Mistral 35° 1L",
        "description": "Pisco premium chileno envejecido en roble americano.",
        "price": 8490.0,
        "cost": 5800.0,
        "stock": 35,
        "category": "Piscos",
        "format": "1L",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    {
        "sku": "ADC-40-750",
        "name": "Pisco Alto del Carmen 40° 750cc",
        "description": "Pisco premium chileno transparente de sabor intenso.",
        "price": 7990.0,
        "cost": 5400.0,
        "stock": 30,
        "category": "Piscos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.32,
        "taxes": 0.19,
    },
    {
        "sku": "3R-35-750",
        "name": "Pisco Tres Erres 35° 750cc",
        "description": "Pisco artesanal del Valle del Elqui, tradición centenaria.",
        "price": 5490.0,
        "cost": 3700.0,
        "stock": 25,
        "category": "Piscos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.32,
        "taxes": 0.19,
    },
    {
        "sku": "CONTROL-43-750",
        "name": "Pisco Control Gran Pisco 43° 750cc",
        "description": "Pisco chileno de alta graduación con notas frutales maduras.",
        "price": 8990.0,
        "cost": 6200.0,
        "stock": 15,
        "category": "Piscos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.31,
        "taxes": 0.19,
    },
    # Vinos
    {
        "sku": "CASILLERO-CS-750",
        "name": "Vino Casillero del Diablo Cabernet Sauvignon 750cc",
        "description": "Vino tinto chileno de gran cuerpo y aromas a ciruelas.",
        "price": 5490.0,
        "cost": 3600.0,
        "stock": 25,
        "category": "Vinos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.34,
        "taxes": 0.19,
    },
    {
        "sku": "GATO-SB-750",
        "name": "Vino Gato Negro Sauvignon Blanc 750cc",
        "description": "Vino blanco fresco y fácil de tomar con notas cítricas.",
        "price": 2890.0,
        "cost": 1800.0,
        "stock": 40,
        "category": "Vinos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.37,
        "taxes": 0.19,
    },
    {
        "sku": "SANTAEMA-CARM-750",
        "name": "Vino Santa Ema Gran Reserva Carmenere 750cc",
        "description": "Vino premium tinto con toques de especias y vainilla.",
        "price": 9990.0,
        "cost": 6800.0,
        "stock": 12,
        "category": "Vinos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.32,
        "taxes": 0.19,
    },
    {
        "sku": "MARQUES-CHARD-750",
        "name": "Vino Marques de Casa Concha Chardonnay 750cc",
        "description": "Vino blanco premium con crianza en barrica francesa.",
        "price": 14990.0,
        "cost": 10500.0,
        "stock": 10,
        "category": "Vinos",
        "format": "750cc",
        "unit_of_measure": "un",
        "is_available": True,
        "margin": 0.30,
        "taxes": 0.19,
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        logger.info("Iniciando sembrado de la base de datos...")

        # 1. Sembrar categorías ordenadas alfabéticamente
        categories_dict = {}
        for cat_name in sorted(CATEGORIES_TO_SEED):
            slug = slugify(cat_name)
            category = db.query(Category).filter(Category.name == cat_name).first()
            if not category:
                category = Category(name=cat_name, slug=slug, is_system=False)
                db.add(category)
                db.flush()
                logger.info("Categoría creada: %s (slug: %s)", cat_name, slug)
            else:
                logger.info("Categoría existente: %s", cat_name)
            categories_dict[cat_name] = category

        # 2. Sembrar productos (respetando integridad referencial con categorías)
        for p_data in PRODUCTS_TO_SEED:
            sku = p_data["sku"]
            product = db.query(Product).filter(Product.sku == sku).first()
            category_name = p_data["category"]

            if not product:
                product = Product(
                    sku=sku,
                    name=p_data["name"],
                    description=p_data["description"],
                    price=Decimal(str(p_data["price"])),
                    cost=Decimal(str(p_data["cost"])),
                    stock=p_data["stock"],
                    category=category_name,
                    format=p_data["format"],
                    unit_of_measure=p_data["unit_of_measure"],
                    is_available=p_data["is_available"],
                    margin=Decimal(str(p_data["margin"])),
                    taxes=Decimal(str(p_data["taxes"])),
                )
                db.add(product)
                logger.info("Producto creado: %s (SKU: %s)", p_data["name"], sku)
            else:
                product.name = p_data["name"]
                product.description = p_data["description"]
                product.price = Decimal(str(p_data["price"]))
                product.cost = Decimal(str(p_data["cost"]))
                product.stock = p_data["stock"]
                product.category = category_name
                product.format = p_data["format"]
                product.unit_of_measure = p_data["unit_of_measure"]
                product.is_available = p_data["is_available"]
                product.margin = Decimal(str(p_data["margin"]))
                product.taxes = Decimal(str(p_data["taxes"]))
                logger.info("Producto actualizado: %s (SKU: %s)", p_data["name"], sku)

        db.commit()
        logger.info("Sembrado de base de datos finalizado exitosamente.")
    except Exception as e:
        db.rollback()
        logger.error("Error durante el sembrado de base de datos: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
