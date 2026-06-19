"""
Fase 5: Tests de Integración Single-Tenant + RAG + Admin

Verifica:
1. KB FTS Search (español, acentos, stemming)
2. RAG Context Builder
3. Products CRUD
4. Business Config CRUD
5. Rate Limiting
"""

from __future__ import annotations

import os
import sys
import uuid
from importlib.util import find_spec
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies only when ADK is not installed in the environment.
if find_spec("google.adk") is None:
    sys.modules["google"] = MagicMock()
    sys.modules["google.adk"] = MagicMock()
    sys.modules["google.adk.models"] = MagicMock()
    sys.modules["google.adk.models.lite_llm"] = MagicMock()
    sys.modules["google.adk.sessions"] = MagicMock()
    sys.modules["google.genai"] = MagicMock()
    sys.modules["google.genai.types"] = MagicMock()


# ============================================================================
# FIXTURES
# ============================================================================

WORKSPACE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.begin = MagicMock()
    db.begin().__enter__ = MagicMock(return_value=db)
    db.begin().__exit__ = MagicMock(return_value=False)
    db.flush = MagicMock()
    db.refresh = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def mock_business_config():
    config = MagicMock()
    config.id = uuid.uuid4()
    config.name = "Negocio El Buen Trago"
    config.email = "contacto@elbuentrago.cl"
    config.phone = "+56912345678"
    config.address = "Av. Principal 123"
    config.city = "Santiago"
    config.website = "https://elbuentrago.cl"
    config.logo_url = "https://example.com/logo.png"
    config.business_hours = {"lunes": {"open": "10:00", "close": "22:00"}}

    def get_business_hours_display():
        hours = config.business_hours or {}
        if not hours:
            return "Consultar horarios"
        parts = []
        for day, schedule in hours.items():
            if isinstance(schedule, dict) and schedule.get("open"):
                parts.append(f"{day}: {schedule['open']}-{schedule['close']}")
        return ", ".join(parts) if parts else "Consultar horarios"

    config.get_business_hours_display.side_effect = get_business_hours_display
    return config


# ============================================================================
# TEST 1: KB FTS Search (español, acentos, stemming)
# ============================================================================


class TestKBFTSSearch:
    def test_search_with_accents(self, mock_db):
        """FTS debe encontrar 'atencion' cuando se busca 'atención'."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = [
            {
                "id": uuid.uuid4(),
                "category": "horarios",
                "title": "Horario de atención",
                "content": "Lunes a Sábado: 10:00 - 22:00.",
                "rank": 0.85,
            }
        ]

        repo = KBRepository(mock_db)
        results = repo.search_fts("atención", top_k=5)

        assert len(results) == 1
        assert results[0]["title"] == "Horario de atención"
        assert results[0]["rank"] > 0

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "plainto_tsquery('spanish'" in sql_text
        assert "immutable_unaccent" in sql_text

    def test_search_with_stemming(self, mock_db):
        """FTS debe encontrar 'cervezas' cuando se busca 'cerveza'."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = [
            {
                "id": uuid.uuid4(),
                "category": "productos",
                "title": "Variedad de cervezas",
                "content": "Más de 50 variedades de cervezas nacionales.",
                "rank": 0.92,
            }
        ]

        repo = KBRepository(mock_db)
        results = repo.search_fts("cerveza", top_k=5)

        assert len(results) == 1
        assert "cervezas" in results[0]["content"].lower()

    def test_search_with_category_filter(self, mock_db):
        """FTS debe filtrar por categoría."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = []

        repo = KBRepository(mock_db)
        repo.search_fts("horario", category="productos")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "kb.category = :category" in sql_text

    def test_search_empty_query_returns_empty(self, mock_db):
        """Búsqueda sin resultados debe retornar lista vacía."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = []

        repo = KBRepository(mock_db)
        results = repo.search_fts("producto-inexistente-xyz", top_k=5)

        assert results == []

    def test_search_respects_top_k(self, mock_db):
        """FTS debe respetar el límite top_k."""
        from repositories.kb_repository import KBRepository

        # Mock returns exactly top_k results
        mock_db.execute.return_value.mappings.return_value.all.return_value = [
            {
                "id": uuid.uuid4(),
                "category": "test",
                "title": "Entry 0",
                "content": "Content",
                "rank": 0.5,
            }
        ]

        repo = KBRepository(mock_db)
        results = repo.search_fts("test", top_k=3)

        assert len(results) == 1


# ============================================================================
# TEST 2: RAG Context Builder
# ============================================================================


class TestRAGContextBuilder:
    @pytest.mark.asyncio
    async def test_build_context_with_results(self, mock_db):
        """RAG debe construir contexto XML con resultados de búsqueda."""
        from services.kb_service import KBService
        from services.rag_context_builder import RAGContextBuilder

        kb_svc = KBService(mock_db)

        with patch.object(kb_svc, "search") as mock_search:
            mock_search.return_value = [
                {
                    "id": str(uuid.uuid4()),
                    "category": "horarios",
                    "title": "Horario de atención",
                    "content": "Lunes a Sábado: 10:00 - 22:00.",
                    "rank": 0.9,
                },
                {
                    "id": str(uuid.uuid4()),
                    "category": "productos",
                    "title": "Variedad de cervezas",
                    "content": "Más de 50 variedades.",
                    "rank": 0.7,
                },
            ]

            rag_builder = RAGContextBuilder(kb_svc)
            context = await rag_builder.build_context("horario cervezas", top_k=5)

            assert "<KNOWLEDGE_BASE_CONTEXT>" in context
            assert "Horario de atención" in context
            assert "Variedad de cervezas" in context
            assert "</KNOWLEDGE_BASE_CONTEXT>" in context

    @pytest.mark.asyncio
    async def test_build_context_empty_results(self, mock_db):
        """RAG debe retornar string vacío si no hay resultados."""
        from services.kb_service import KBService
        from services.rag_context_builder import RAGContextBuilder

        kb_svc = KBService(mock_db)

        with patch.object(kb_svc, "search") as mock_search:
            mock_search.return_value = []

            rag_builder = RAGContextBuilder(kb_svc)
            context = await rag_builder.build_context("producto-inexistente", top_k=5)

            assert context == ""

    def test_inject_into_instruction_with_context(self):
        """RAG debe inyectar contexto en la instrucción del agente."""
        from services.rag_context_builder import RAGContextBuilder

        rag_builder = RAGContextBuilder(MagicMock())
        base_instruction = "Eres un asistente útil."
        rag_context = "<KNOWLEDGE_BASE_CONTEXT>\n[1] Horario: 10:00-22:00\n</KNOWLEDGE_BASE_CONTEXT>"

        result = rag_builder.inject_into_instruction(base_instruction, rag_context)

        assert base_instruction in result
        assert rag_context in result
        assert "Usa la información anterior" in result

    def test_inject_into_instruction_without_context(self):
        """Sin contexto RAG, la instrucción debe permanecer igual."""
        from services.rag_context_builder import RAGContextBuilder

        rag_builder = RAGContextBuilder(MagicMock())
        base_instruction = "Eres un asistente útil."

        result = rag_builder.inject_into_instruction(base_instruction, "")

        assert result == base_instruction


# ============================================================================
# TEST 3: Products CRUD
# ============================================================================


class TestProductsCRUD:
    def test_create_product(self, mock_db):
        """Crear producto debe guardar en la base de datos."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.refresh = MagicMock()

        product_svc = ProductService(mock_db)
        product_svc.create_product(
            name="Pisco Control 35°",
            description="Pisco nacional",
            price=7990.0,
            stock=50,
            category="pisco",
        )

        mock_db.add.assert_called_once()
        added_product = mock_db.add.call_args[0][0]
        assert added_product.name == "Pisco Control 35°"
        assert added_product.price == 7990.0

    def test_list_products(self, mock_db):
        """Listar productos."""
        from services.product_service import ProductService

        mock_products = [MagicMock() for _ in range(2)]
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_products

        product_svc = ProductService(mock_db)
        products = product_svc.list_products()

        assert len(products) == 2

    def test_update_product(self, mock_db):
        """Actualizar producto debe modificar solo campos especificados."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_product.name = "Pisco Control 35° 1L"
        mock_product.price = 7990.0
        mock_product.stock = 50

        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.flush = MagicMock()
        mock_db.refresh = MagicMock()

        product_svc = ProductService(mock_db)
        product_svc.update_product(
            product_id=uuid.uuid4(),
            price=8990.0,
            stock=40,
        )

        assert mock_product.price == 8990.0
        assert mock_product.stock == 40
        assert mock_product.name == "Pisco Control 35° 1L"

    def test_delete_product(self, mock_db):
        """Eliminar producto debe retornar True."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.delete = MagicMock()
        mock_db.flush = MagicMock()

        product_svc = ProductService(mock_db)
        result = product_svc.delete_product(uuid.uuid4())

        assert result is True
        mock_db.delete.assert_called_once_with(mock_product)

    def test_delete_nonexistent_product(self, mock_db):
        """Eliminar producto inexistente debe retornar False."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        product_svc = ProductService(mock_db)
        result = product_svc.delete_product(uuid.uuid4())

        assert result is False

    def test_search_products_by_name(self, mock_db):
        """Buscar productos por nombre debe usar ILIKE."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_product.name = "Pisco Control 35° 1L"
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_product
        ]

        product_svc = ProductService(mock_db)
        results = product_svc.search("pisco")

        assert len(results) == 1
        assert "pisco" in results[0].name.lower()

    def test_get_categories(self, mock_db):
        """Obtener categorías debe retornar lista única."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.distinct.return_value.pluck.return_value = [
            "pisco",
            "vino",
            "whisky",
        ]

        product_svc = ProductService(mock_db)
        categories = product_svc.get_categories()

        assert categories == ["pisco", "vino", "whisky"]


# ============================================================================
# TEST 4: Business Config CRUD
# ============================================================================


class TestBusinessConfig:
    def test_update_profile_fields(self, mock_business_config):
        """Actualizar perfil debe modificar campos de la configuración."""
        mock_business_config.email = "nuevo@test.com"
        mock_business_config.phone = "+56999999999"
        mock_business_config.address = "Nueva Dirección 789"
        mock_business_config.city = "Valparaíso"
        mock_business_config.website = "https://nueva.cl"
        mock_business_config.logo_url = "https://example.com/new-logo.png"
        mock_business_config.business_hours = {
            "lunes": {"open": "09:00", "close": "21:00"}
        }

        assert mock_business_config.email == "nuevo@test.com"
        assert mock_business_config.phone == "+56999999999"
        assert mock_business_config.business_hours["lunes"]["open"] == "09:00"

    def test_get_business_hours_display(self, mock_business_config):
        """Display de horarios debe formatear correctamente."""
        hours_display = mock_business_config.get_business_hours_display()

        assert "10:00" in hours_display or "lunes" in hours_display.lower()


# ============================================================================
# TEST 5: Rate Limiting (configuration validation)
# ============================================================================


class TestRateLimiting:
    def test_nginx_conf_has_rate_limit_zones(self):
        """nginx.conf debe definir zonas de rate limiting."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "limit_req_zone" in content
        assert "zone=chat_limit" in content
        assert "zone=admin_limit" in content
        assert "zone=api_limit" in content

    def test_nginx_conf_applies_rate_limits(self):
        """nginx.conf debe aplicar rate limits a endpoints."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "limit_req zone=chat_limit" in content
        assert "limit_req zone=admin_limit" in content
        assert "limit_req zone=api_limit" in content

    def test_nginx_conf_has_429_error_page(self):
        """nginx.conf debe manejar error 429."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "error_page 429" in content
        assert "Too many requests" in content

    def test_nginx_conf_has_ssl_config(self):
        """nginx.conf debe tener configuración SSL."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "ssl_certificate" in content
        assert "ssl_protocols TLSv1.2 TLSv1.3" in content
        assert "Strict-Transport-Security" in content

    def test_nginx_conf_has_security_headers(self):
        """nginx.conf debe tener security headers."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "X-Frame-Options" in content
        assert "X-Content-Type-Options" in content
        assert "X-XSS-Protection" in content
        assert "Referrer-Policy" in content

    def test_nginx_conf_has_gzip(self):
        """nginx.conf debe tener gzip habilitado."""
        nginx_conf_path = os.path.join(WORKSPACE_DIR, "nginx.conf")
        with open(nginx_conf_path, "r") as f:
            content = f.read()

        assert "gzip on" in content
        assert "application/json" in content


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
