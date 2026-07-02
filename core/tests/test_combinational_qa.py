from __future__ import annotations

import uuid
import pytest
from unittest.mock import MagicMock

from models.conversation import Conversation
from services.product_service import ProductService
from services.rag_context_builder import RAGContextBuilder


# ============================================================================
# FSM Transitions Combinational Tests
# ============================================================================


@pytest.mark.parametrize(
    "start_state, target_state, expected_allowed",
    [
        ("CHAT_LIBRE", "AWAITING_PRODUCT", True),
        ("CHAT_LIBRE", "AWAITING_CONFIRMATION", True),
        ("CHAT_LIBRE", "CLOSED", True),
        ("CHAT_LIBRE", "CHAT_LIBRE", True),  # transition_to returns early if same state
        ("AWAITING_PRODUCT", "CHAT_LIBRE", True),
        ("AWAITING_PRODUCT", "CLOSED", True),
        ("AWAITING_PRODUCT", "AWAITING_CONFIRMATION", False),
        ("AWAITING_CONFIRMATION", "CHAT_LIBRE", True),
        ("AWAITING_CONFIRMATION", "CLOSED", True),
        ("AWAITING_CONFIRMATION", "AWAITING_PRODUCT", False),
        ("CLOSED", "CHAT_LIBRE", True),
        ("CLOSED", "CLOSED", True),
        ("CLOSED", "AWAITING_PRODUCT", False),
    ],
)
def test_fsm_combinational_transitions(
    start_state: str, target_state: str, expected_allowed: bool
) -> None:
    conv = Conversation(state=start_state)
    if expected_allowed:
        conv.transition_to(target_state)
        assert conv.state == target_state
    else:
        with pytest.raises(ValueError):
            conv.transition_to(target_state)


# ============================================================================
# RAG Context Builder Combinational Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rag_combinational_empty_and_filled() -> None:
    # 1. Test builder with empty search results
    from unittest.mock import AsyncMock

    kb_svc_mock = MagicMock()
    kb_svc_mock.search = AsyncMock(return_value=[])

    rag_builder = RAGContextBuilder(kb_svc_mock)
    context = await rag_builder.build_context("unrelated query")
    assert context == ""

    # 2. Test builder with matching search results
    kb_svc_mock.search = AsyncMock(
        return_value=[
            {
                "id": str(uuid.uuid4()),
                "category": "horarios",
                "title": "Horario Especial",
                "content": "Abierto 24/7",
                "rank": 0.99,
            }
        ]
    )
    context = await rag_builder.build_context("horarios")
    assert "<KNOWLEDGE_BASE_CONTEXT>" in context
    assert "Horario Especial" in context
    assert "Abierto 24/7" in context


# ============================================================================
# Product Repository & Service Combinational Tests
# ============================================================================


def test_product_service_crud_combinations() -> None:
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.refresh = MagicMock()

    product_svc = ProductService(mock_db)

    # Combinations of create input parameters
    product_svc.create_product(
        name="Cerveza Test",
        description="Test desc",
        price=1500.0,
        stock=10,
        category="cerveza",
    )
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert added.name == "Cerveza Test"
    assert added.price == 1500.0
    assert added.stock == 10
