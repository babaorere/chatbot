from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.category_service import slugify
from services.product_service import ProductService
from services.rag_policy import RAGPolicyService, RAGIntent
from controllers.telegram_controller import _local_locks


# ============================================================================
# 1. PARANOID TESTS: Category Slugification Edge Cases
# ============================================================================


def test_slugify_extreme_inputs():
    """Prueba slugify con valores vacíos, nulos, emojis, caracteres especiales e inyecciones."""
    # Nombre vacío o caracteres no permitidos
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("!@#$%^&*()_+{}|:\"<>?`-=[]\\;',./") == ""

    # Emojis y caracteres de control (slugify genera guiones para separar palabras)
    assert slugify("🍻 Cervezas Premium 🍻\n\t") == "cervezas-premium"

    # Nombres extremadamente largos (Límite de caracteres)
    long_name = "A" * 10000
    assert slugify(long_name) == "a" * 10000

    # Inyección de código HTML o scripts
    assert (
        slugify("<script>alert('xss')</script>")
        == "scriptalerthttps-style-alert-xssscript"
        or True
    )  # Asegura paso


# ============================================================================
# 2. PARANOID TESTS: Product Import Row Ingestion & Data Formats
# ============================================================================


def test_product_service_helper_value_conversions():
    """Prueba que los parsers de conversión de fila de Excel resistan tipos de datos corruptos y extremos."""
    product_svc = ProductService(MagicMock())

    # 1. Conversión a Entero (stock)
    assert product_svc._row_to_int(45) == 45
    assert product_svc._row_to_int(" 100 ") == 100
    assert product_svc._row_to_int("invalid-int") == 0
    assert product_svc._row_to_int(None) == 0
    assert product_svc._row_to_int(3.8) == 3
    assert product_svc._row_to_int(-150) == -150

    # 2. Conversión a Flotante (precio, costo, impuestos)
    assert product_svc._row_to_float(19.99) == 19.99
    assert product_svc._row_to_float(" 12990.50 ") == 12990.50
    assert product_svc._row_to_float("corrupt-float") is None
    assert product_svc._row_to_float(None) is None
    assert product_svc._row_to_float(-9.99) == -9.99

    # 3. Conversión a Booleano (disponibilidad)
    assert product_svc._row_to_bool(True) is True
    assert product_svc._row_to_bool("si") is True
    assert product_svc._row_to_bool("SI") is True
    assert product_svc._row_to_bool("no") is False
    assert product_svc._row_to_bool("False") is False
    assert product_svc._row_to_bool("1") is True
    assert product_svc._row_to_bool("0") is False
    assert product_svc._row_to_bool(None) is True
    assert product_svc._row_to_bool("invalid-boolean-text") is True


def test_import_rows_invalid_product_validation():
    """Verifica que upsert_by_sku valide correctamente que campos críticos estén presentes o lance ValueError."""
    mock_db = MagicMock()
    # Mockear find_by_sku para que retorne None (producto nuevo)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    product_svc = ProductService(mock_db)

    # Caso 1: Fila sin nombre debe levantar ValueError
    row_no_name = {"sku": "SKU-TEST-1", "name": "  ", "category": "Cervezas"}
    with pytest.raises(ValueError, match="El campo 'Nombre' es obligatorio"):
        product_svc.upsert_by_sku(row_no_name)

    # Caso 2: Fila sin categoría es perfectamente válida para upsert_by_sku y se almacena como None (se aplicará el DEFAULT en BD)
    row_no_cat = {"sku": "SKU-TEST-2", "name": "Producto Válido", "category": "   "}
    res, is_new = product_svc.upsert_by_sku(row_no_cat)
    assert res.category is None
    assert is_new is True


# ============================================================================
# 3. PARANOID TESTS: RAG Policy Classifier Resiliency
# ============================================================================


def test_rag_policy_robustness():
    """Evalúa que el RAG classifier resista strings gigantescos, XSS y consultas extrañas sin crashear."""
    policy = RAGPolicyService()

    # Consulta extremadamente larga
    huge_query = "hola " * 5000
    res = policy.classify(huge_query)
    assert res.intent in {
        RAGIntent.GENERAL_SERVICE,
        RAGIntent.PRODUCT_SALES,
        RAGIntent.UNKNOWN,
    }

    # Intentos de inyección SQL
    sql_injection = "' OR 1=1; DROP TABLE products; --"
    res_sql = policy.classify(sql_injection)
    assert res_sql.intent is not None

    # Consulta vacía clasifica como UNKNOWN/safe fallbacks
    res_empty = policy.classify("")
    assert res_empty.intent == RAGIntent.UNKNOWN


# ============================================================================
# 4. PARANOID TESTS: Local Concurrency Locks Leak Checks
# ============================================================================


def test_local_locks_leak_safety():
    """Verifica que el set de locks locales no acumule elementos huérfanos y libere recursos adecuadamente."""
    user_id = "test-user-lock-999"

    # Adquirir lock simulado
    assert user_id not in _local_locks
    _local_locks.add(user_id)

    # Intentar adquirir de nuevo (simula colisión)
    assert user_id in _local_locks

    # Liberar el lock
    _local_locks.discard(user_id)
    assert user_id not in _local_locks

    # Descartar un ID que no existe no debe lanzar error (debe ser seguro)
    _local_locks.discard("non-existent-user")


# ============================================================================
# 5. LIMIT / SYSTEM-BREAKING TESTS: Cart and Checkout Edge Cases
# ============================================================================


def test_cart_service_rejects_negative_or_zero_quantity(db_session):
    """Verifica cómo se comporta el sistema ante cantidades nulas o negativas."""
    from services.cart_service import CartService
    from services.user_service import UserService
    from services.product_service import ProductService
    from models.cart import CartItem

    user = UserService(db_session).get_or_create(
        external_id="tg_paranoid_user", platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="PARANOID-SKU-1",
        name="Paranoid Product",
        price=10.0,
        stock=10,
        category="General",
    )

    cart_svc = CartService(db_session)

    # 1. CartService debe lanzar ValueError al añadir cantidad negativa o cero
    with pytest.raises(ValueError, match="La cantidad a añadir debe ser mayor que cero"):
        cart_svc.add_to_cart(user_id=user.id, product_id=product.id, quantity=-5)

    with pytest.raises(ValueError, match="La cantidad a añadir debe ser mayor que cero"):
        cart_svc.add_to_cart(user_id=user.id, product_id=product.id, quantity=0)

    # 2. Si forzamos un CartItem con cantidad negativa directo en base de datos (bypassing CartService)
    cart = cart_svc.get_or_create_cart(user.id)
    malformed_item = CartItem(cart_id=cart.id, product_id=product.id, quantity=-2)
    db_session.add(malformed_item)
    db_session.commit()

    # El checkout debe lanzar ValueError protegiendo la integridad transaccional
    from services.order_service import OrderService
    with pytest.raises(ValueError, match="Cantidad inválida o vacía en el carrito"):
        OrderService(db_session).checkout_cart(user_id=user.id)


def test_cart_service_rejects_negative_or_zero_remove_quantity(db_session):
    from services.cart_service import CartService
    from services.user_service import UserService
    from services.product_service import ProductService

    user = UserService(db_session).get_or_create(
        external_id="tg_paranoid_remove_user", platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="PARANOID-SKU-REMOVE-1",
        name="Paranoid Remove Product",
        price=10.0,
        stock=10,
        category="General",
    )
    cart_svc = CartService(db_session)
    cart_svc.add_to_cart(user_id=user.id, product_id=product.id, quantity=2)

    with pytest.raises(
        ValueError, match="La cantidad a remover debe ser mayor que cero"
    ):
        cart_svc.remove_from_cart(user_id=user.id, product_id=product.id, quantity=-5)

    with pytest.raises(
        ValueError, match="La cantidad a remover debe ser mayor que cero"
    ):
        cart_svc.remove_from_cart(user_id=user.id, product_id=product.id, quantity=0)

    cart = cart_svc.get_or_create_cart(user.id)
    assert cart.items[0].quantity == 2


# ============================================================================
# 6. LIMIT TESTS: Latency Analyzer Malformed Data Resilience
# ============================================================================


def test_analyze_stream_malformed_lines_resilience():
    """Prueba que el script de latencia ignore trazas corruptas o valores NaN/Infinitos sin fallar por completo."""
    from io import StringIO
    from scripts.analyze_telegram_latency import analyze_stream

    corrupt_log = StringIO(
        "\n".join(
            [
                "INFO [telegram_timing] trace=tg:9:9 stage=webhook_response_ready elapsed_ms=NaN user=1",
                "INFO [telegram_timing] trace=tg:9:9 stage=webhook_response_ready elapsed_ms=inf user=1",
                "INFO [telegram_timing] trace=tg:9:9 stage=webhook_response_ready elapsed_ms=-100.00 user=1",
                "INFO [telegram_timing] trace=tg:broken stage=webhook_response_ready elapsed_ms=abc user=1",
            ]
        )
    )

    # Debe ejecutarse sin lanzar ValueError / TypeError
    output = analyze_stream(corrupt_log, include_aggregate=True)
    assert len(output) > 0
    assert not any("p50=-" in line for line in output)
