from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.rag.kb_rag_provider import KBRAGProvider
from services.rag_policy import RAGIntent, RAGPolicyService


class TestRAGPolicyService:
    @pytest.mark.parametrize(
        ("query", "expected_intent"),
        [
            ("¿Tienen pisco sour?", RAGIntent.PRODUCT_SALES),
            ("¿Hay cerveza Kunstmann?", RAGIntent.PRODUCT_SALES),
            ("¿Está disponible la cerveza de trigo?", RAGIntent.PRODUCT_SALES),
            ("¿Cuánto vale el vino Santa Carolina?", RAGIntent.PRODUCT_SALES),
            ("¿Precio del pisco Control?", RAGIntent.PRODUCT_SALES),
            ("Cotízame dos vinos y una cerveza", RAGIntent.PRODUCT_SALES),
            ("Quiero comprar un pisco", RAGIntent.PRODUCT_SALES),
            ("¿Qué venden?", RAGIntent.PRODUCT_SALES),
        ],
    )
    def test_classify_blocks_product_stock_price_queries(
        self,
        query: str,
        expected_intent: RAGIntent,
    ) -> None:
        policy = RAGPolicyService()

        result = policy.classify(query)

        assert result.allowed is False
        assert result.intent == expected_intent

    @pytest.mark.parametrize(
        ("query", "expected_intent"),
        [
            ("¿Cuál es el horario de atención?", RAGIntent.GENERAL_SERVICE),
            ("¿En qué comunas hacen delivery?", RAGIntent.GENERAL_SERVICE),
            ("¿Qué zonas cubren?", RAGIntent.GENERAL_SERVICE),
            ("¿Aceptan transferencia?", RAGIntent.GENERAL_SERVICE),
            ("¿Aceptan efectivo?", RAGIntent.GENERAL_SERVICE),
            ("¿Hacen delivery?", RAGIntent.GENERAL_SERVICE),
            ("¿Qué métodos de pago tienen?", RAGIntent.GENERAL_SERVICE),
            ("¿Están abiertos ahora?", RAGIntent.GENERAL_SERVICE),
        ],
    )
    def test_classify_allows_general_service_queries(
        self,
        query: str,
        expected_intent: RAGIntent,
    ) -> None:
        policy = RAGPolicyService()

        result = policy.classify(query)

        assert result.allowed is True
        assert result.intent == expected_intent

    def test_classify_marks_unknown_queries_as_not_allowed(self) -> None:
        policy = RAGPolicyService()

        result = policy.classify("hola")

        assert result.allowed is False
        assert result.intent == RAGIntent.UNKNOWN

    def test_category_guards_block_product_categories(self) -> None:
        policy = RAGPolicyService()

        assert policy.is_blocked_category("productos") is True
        assert policy.is_blocked_category("catalogo_productos") is True
        assert policy.is_safe_category("horarios") is True
        assert policy.is_safe_category("zonas_atencion") is True
        assert policy.is_safe_category("formas_pago") is True
        assert policy.is_safe_category("delivery") is True
        assert policy.is_safe_category("servicios") is True
        assert policy.is_safe_category("productos") is False
        assert policy.is_safe_category("catalogo") is False


class TestKBRAGProviderPolicy:
    @pytest.mark.asyncio
    async def test_build_context_returns_none_for_product_query(self) -> None:
        db = MagicMock()
        provider = KBRAGProvider(db)

        context = await provider.build_context("¿Tienen pisco sour?")

        assert context is None
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_context_returns_none_for_blocked_category(self) -> None:
        db = MagicMock()
        provider = KBRAGProvider(db)

        context = await provider.build_context(
            "¿Cuál es el horario de atención?", category="productos"
        )

        assert context is None
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_context_uses_repository_for_allowed_query(self) -> None:
        db = MagicMock()
        provider = KBRAGProvider(db)
        query = "¿Cuál es el horario de atención?"

        with patch("infrastructure.rag.kb_rag_provider.KBRepository") as repo_cls:
            repo_cls.return_value.search_fts.return_value = [
                {
                    "category": "horarios",
                    "title": "Horario de atención",
                    "content": "Lunes a Sábado: 10:00-22:00.",
                }
            ]

            context = await provider.build_context(query)

        assert "Horario de atención" in context
        repo_cls.return_value.search_fts.assert_called_once_with(
            query=query,
            top_k=5,
            category=None,
        )

    @pytest.mark.asyncio
    async def test_build_context_returns_none_when_repository_raises(self) -> None:
        db = MagicMock()
        provider = KBRAGProvider(db)

        with patch("infrastructure.rag.kb_rag_provider.KBRepository") as repo_cls:
            repo_cls.return_value.search_fts.side_effect = RuntimeError("db exploded")

            context = await provider.build_context("¿Cuál es el horario de atención?")

        assert context is None
