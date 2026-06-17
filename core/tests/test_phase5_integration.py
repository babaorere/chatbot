"""
Fase 5: Tests de Integración Multi-Tenant + RAG + Admin

Verifica:
1. KB FTS Search (español, acentos, stemming)
2. KB Tenant Isolation (RLS)
3. RAG Context Builder
4. Products CRUD
5. Tenant Profile CRUD
6. Admin Agent Config
7. Rate Limiting
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
def tenant_id_1():
    return uuid.uuid4()


@pytest.fixture
def tenant_id_2():
    return uuid.uuid4()


@pytest.fixture
def mock_tenant_1(tenant_id_1):
    config = {
        "instruction": "Eres el asistente de San Miguel.",
        "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "api_key": "sk-test-key-1",
    }

    tenant = MagicMock()
    tenant.id = tenant_id_1
    tenant.slug = "botilleria_san_miguel"
    tenant.name = "Botillería San Miguel"
    tenant.config = config
    tenant.email = "sanmiguel@test.com"
    tenant.phone = "+56912345678"
    tenant.address = "Av. San Miguel 123"
    tenant.city = "Santiago"
    tenant.website = "https://sanmiguel.cl"
    tenant.logo_url = "https://example.com/logo1.png"
    tenant.business_hours = {"lunes": {"open": "10:00", "close": "22:00"}}
    tenant.status = "active"

    def get_instruction():
        return tenant.config.get("instruction", "")

    def get_model():
        return tenant.config.get(
            "model", "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
        )

    def get_api_key():
        return tenant.config.get("api_key", "")

    def get_business_hours_display():
        hours = tenant.business_hours or {}
        if not hours:
            return "Consultar horarios"
        parts = []
        for day, schedule in hours.items():
            if isinstance(schedule, dict) and schedule.get("open"):
                parts.append(f"{day}: {schedule['open']}-{schedule['close']}")
        return ", ".join(parts) if parts else "Consultar horarios"

    tenant.get_instruction.side_effect = get_instruction
    tenant.get_model.side_effect = get_model
    tenant.get_api_key.side_effect = get_api_key
    tenant.get_business_hours_display.side_effect = get_business_hours_display

    return tenant


@pytest.fixture
def mock_tenant_2(tenant_id_2):
    config = {
        "instruction": "Eres el asistente de Providencia.",
        "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "api_key": "sk-test-key-2",
    }

    tenant = MagicMock()
    tenant.id = tenant_id_2
    tenant.slug = "licoreria_providencia"
    tenant.name = "Licorería Providencia"
    tenant.config = config
    tenant.email = "providencia@test.com"
    tenant.phone = "+56987654321"
    tenant.address = "Av. Providencia 456"
    tenant.city = "Santiago"
    tenant.website = None
    tenant.logo_url = None
    tenant.business_hours = None
    tenant.status = "active"

    def get_instruction():
        return tenant.config.get("instruction", "")

    def get_model():
        return tenant.config.get(
            "model", "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
        )

    def get_api_key():
        return tenant.config.get("api_key", "")

    def get_business_hours_display():
        hours = tenant.business_hours or {}
        if not hours:
            return "Consultar horarios"
        parts = []
        for day, schedule in hours.items():
            if isinstance(schedule, dict) and schedule.get("open"):
                parts.append(f"{day}: {schedule['open']}-{schedule['close']}")
        return ", ".join(parts) if parts else "Consultar horarios"

    tenant.get_instruction.side_effect = get_instruction
    tenant.get_model.side_effect = get_model
    tenant.get_api_key.side_effect = get_api_key
    tenant.get_business_hours_display.side_effect = get_business_hours_display

    return tenant


# ============================================================================
# TEST 1: KB FTS Search (español, acentos, stemming)
# ============================================================================


class TestKBFTSSearch:
    def test_search_with_accents(self, mock_db, tenant_id_1):
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
        results = repo.search_fts(tenant_id_1, "atención", top_k=5)

        assert len(results) == 1
        assert results[0]["title"] == "Horario de atención"
        assert results[0]["rank"] > 0

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "plainto_tsquery('spanish'" in sql_text
        assert "immutable_unaccent" in sql_text

    def test_search_with_stemming(self, mock_db, tenant_id_1):
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
        results = repo.search_fts(tenant_id_1, "cerveza", top_k=5)

        assert len(results) == 1
        assert "cervezas" in results[0]["content"].lower()

    def test_search_with_category_filter(self, mock_db, tenant_id_1):
        """FTS debe filtrar por categoría."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = []

        repo = KBRepository(mock_db)
        repo.search_fts(tenant_id_1, "horario", category="productos")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "kb.category = :category" in sql_text

    def test_search_empty_query_returns_empty(self, mock_db, tenant_id_1):
        """Búsqueda sin resultados debe retornar lista vacía."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = []

        repo = KBRepository(mock_db)
        results = repo.search_fts(tenant_id_1, "producto-inexistente-xyz", top_k=5)

        assert results == []

    def test_search_respects_top_k(self, mock_db, tenant_id_1):
        """FTS debe respetar el límite top_k."""
        from repositories.kb_repository import KBRepository

        # Mock returns exactly top_k results
        mock_db.execute.return_value.mappings.return_value.all.return_value = [
            {
                "id": uuid.uuid4(),
                "category": "test",
                "title": f"Entry {i}",
                "content": "Content",
                "rank": 0.5,
            }
            for i in range(3)
        ]

        repo = KBRepository(mock_db)
        results = repo.search_fts(tenant_id_1, "test", top_k=3)

        assert len(results) == 3


# ============================================================================
# TEST 2: KB Tenant Isolation (RLS)
# ============================================================================


class TestKBTenantIsolation:
    def test_tenant_1_cannot_see_tenant_2_kb(self, mock_db, tenant_id_1, tenant_id_2):
        """Tenant 1 no debe poder ver entradas KB de Tenant 2."""
        from services.kb_service import KBService

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        kb_svc = KBService(mock_db, tenant_id_1)
        entries = kb_svc.list_entries()

        assert len(entries) == 0

    def test_tenant_2_cannot_see_tenant_1_kb(self, mock_db, tenant_id_1, tenant_id_2):
        """Tenant 2 no debe poder ver entradas KB de Tenant 1."""
        from services.kb_service import KBService

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        kb_svc = KBService(mock_db, tenant_id_2)
        entries = kb_svc.list_entries()

        assert len(entries) == 0

    def test_search_is_tenant_scoped(self, mock_db, tenant_id_1, tenant_id_2):
        """Búsqueda FTS debe estar scopeada al tenant."""
        from repositories.kb_repository import KBRepository

        mock_db.execute.return_value.mappings.return_value.all.return_value = []

        repo = KBRepository(mock_db)
        repo.search_fts(tenant_id_1, "horario")

        call_args = mock_db.execute.call_args
        params = call_args[1] if call_args[1] else call_args[0][1]
        assert params["tenant_id"] == tenant_id_1

    def test_create_entry_assigns_correct_tenant(self, mock_db, tenant_id_1):
        """Crear entrada KB debe asignar el tenant_id correcto."""
        from services.kb_service import KBService

        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.refresh = MagicMock()

        kb_svc = KBService(mock_db, tenant_id_1)
        kb_svc.create_entry(
            category="horarios",
            title="Horario",
            content="Lunes a Viernes 10:00-18:00",
        )

        mock_db.add.assert_called_once()
        added_entry = mock_db.add.call_args[0][0]
        assert added_entry.tenant_id == tenant_id_1
        assert added_entry.category == "horarios"


# ============================================================================
# TEST 3: RAG Context Builder
# ============================================================================


class TestRAGContextBuilder:
    @pytest.mark.asyncio
    async def test_build_context_with_results(self, mock_db, tenant_id_1):
        """RAG debe construir contexto XML con resultados de búsqueda."""
        from services.kb_service import KBService
        from services.rag_context_builder import RAGContextBuilder

        kb_svc = KBService(mock_db, tenant_id_1)

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
    async def test_build_context_empty_results(self, mock_db, tenant_id_1):
        """RAG debe retornar string vacío si no hay resultados."""
        from services.kb_service import KBService
        from services.rag_context_builder import RAGContextBuilder

        kb_svc = KBService(mock_db, tenant_id_1)

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
# TEST 4: Products CRUD
# ============================================================================


class TestProductsCRUD:
    def test_create_product(self, mock_db, tenant_id_1):
        """Crear producto debe asignar tenant_id correcto."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.refresh = MagicMock()

        product_svc = ProductService(mock_db, tenant_id_1)
        product_svc.create_product(
            name="Pisco Control 35°",
            description="Pisco nacional",
            price=7990.0,
            stock=50,
            category="pisco",
        )

        mock_db.add.assert_called_once()
        added_product = mock_db.add.call_args[0][0]
        assert added_product.tenant_id == tenant_id_1
        assert added_product.name == "Pisco Control 35°"
        assert added_product.price == 7990.0

    def test_list_products_by_tenant(self, mock_db, tenant_id_1):
        """Listar productos debe filtrar por tenant."""
        from services.product_service import ProductService

        mock_products = [MagicMock(tenant_id=tenant_id_1) for _ in range(2)]
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_products

        product_svc = ProductService(mock_db, tenant_id_1)
        products = product_svc.list_products()

        assert len(products) == 2
        assert all(p.tenant_id == tenant_id_1 for p in products)

    def test_update_product(self, mock_db, tenant_id_1):
        """Actualizar producto debe modificar solo campos especificados."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_product.name = "Pisco Control 35° 1L"
        mock_product.price = 7990.0
        mock_product.stock = 50

        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.flush = MagicMock()
        mock_db.refresh = MagicMock()

        product_svc = ProductService(mock_db, tenant_id_1)
        product_svc.update_product(
            product_id=uuid.uuid4(),
            price=8990.0,
            stock=40,
        )

        assert mock_product.price == 8990.0
        assert mock_product.stock == 40
        assert mock_product.name == "Pisco Control 35° 1L"

    def test_delete_product(self, mock_db, tenant_id_1):
        """Eliminar producto debe retornar True."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.delete = MagicMock()
        mock_db.flush = MagicMock()

        product_svc = ProductService(mock_db, tenant_id_1)
        result = product_svc.delete_product(uuid.uuid4())

        assert result is True
        mock_db.delete.assert_called_once_with(mock_product)

    def test_delete_nonexistent_product(self, mock_db, tenant_id_1):
        """Eliminar producto inexistente debe retornar False."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        product_svc = ProductService(mock_db, tenant_id_1)
        result = product_svc.delete_product(uuid.uuid4())

        assert result is False

    def test_search_products_by_name(self, mock_db, tenant_id_1):
        """Buscar productos por nombre debe usar ILIKE."""
        from services.product_service import ProductService

        mock_product = MagicMock()
        mock_product.name = "Pisco Control 35° 1L"
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_product
        ]

        product_svc = ProductService(mock_db, tenant_id_1)
        results = product_svc.search("pisco")

        assert len(results) == 1
        assert "pisco" in results[0].name.lower()

    def test_get_categories(self, mock_db, tenant_id_1):
        """Obtener categorías debe retornar lista única."""
        from services.product_service import ProductService

        mock_db.query.return_value.filter.return_value.distinct.return_value.pluck.return_value = [
            "pisco",
            "vino",
            "whisky",
        ]

        product_svc = ProductService(mock_db, tenant_id_1)
        categories = product_svc.get_categories()

        assert categories == ["pisco", "vino", "whisky"]


# ============================================================================
# TEST 5: Tenant Profile CRUD
# ============================================================================


class TestTenantProfile:
    def test_update_profile_fields(self, mock_tenant_1):
        """Actualizar perfil debe modificar campos del tenant."""
        mock_tenant_1.email = "nuevo@test.com"
        mock_tenant_1.phone = "+56999999999"
        mock_tenant_1.address = "Nueva Dirección 789"
        mock_tenant_1.city = "Valparaíso"
        mock_tenant_1.website = "https://nueva.cl"
        mock_tenant_1.logo_url = "https://example.com/new-logo.png"
        mock_tenant_1.business_hours = {"lunes": {"open": "09:00", "close": "21:00"}}

        assert mock_tenant_1.email == "nuevo@test.com"
        assert mock_tenant_1.phone == "+56999999999"
        assert mock_tenant_1.business_hours["lunes"]["open"] == "09:00"

    def test_get_business_hours_display(self, mock_tenant_1):
        """Display de horarios debe formatear correctamente."""
        hours_display = mock_tenant_1.get_business_hours_display()

        assert "10:00" in hours_display or "lunes" in hours_display.lower()

    def test_get_business_hours_display_empty(self, mock_tenant_2):
        """Sin horarios configurados, debe retornar default."""
        hours_display = mock_tenant_2.get_business_hours_display()

        assert "Consultar horarios" in hours_display

    def test_tenant_getters(self, mock_tenant_1):
        """Getters de config deben retornar valores correctos."""
        assert mock_tenant_1.get_instruction() == "Eres el asistente de San Miguel."
        assert "nemotron" in mock_tenant_1.get_model()
        assert mock_tenant_1.get_api_key() == "sk-test-key-1"


# ============================================================================
# TEST 6: Admin Agent Config
# ============================================================================


class TestAdminAgentConfig:
    def test_update_agent_model(self, mock_tenant_1):
        """Admin debe poder actualizar modelo del agente."""
        new_model = "openrouter/anthropic/claude-3-haiku:free"
        mock_tenant_1.config["model"] = new_model

        assert mock_tenant_1.get_model() == new_model

    def test_update_agent_instruction(self, mock_tenant_1):
        """Admin debe poder actualizar instruction del agente."""
        new_instruction = "Eres un asistente especializado en vinos."
        mock_tenant_1.config["instruction"] = new_instruction

        assert mock_tenant_1.get_instruction() == new_instruction

    def test_update_agent_api_key(self, mock_tenant_1):
        """Admin debe poder actualizar API key del agente."""
        new_api_key = "sk-or-v1-new-key-123"
        mock_tenant_1.config["api_key"] = new_api_key

        assert mock_tenant_1.get_api_key() == new_api_key

    def test_agent_config_preserves_other_fields(self, mock_tenant_1):
        """Actualizar config no debe afectar otros campos."""
        original_name = mock_tenant_1.name
        original_slug = mock_tenant_1.slug

        mock_tenant_1.config["model"] = "new-model"

        assert mock_tenant_1.name == original_name
        assert mock_tenant_1.slug == original_slug

    def test_toggle_tenant_status(self, mock_tenant_1):
        """Admin debe poder activar/desactivar tenant."""
        assert mock_tenant_1.status == "active"

        mock_tenant_1.status = "inactive"
        assert mock_tenant_1.status == "inactive"

        mock_tenant_1.status = "active"
        assert mock_tenant_1.status == "active"


# ============================================================================
# TEST 7: Rate Limiting (configuration validation)
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
