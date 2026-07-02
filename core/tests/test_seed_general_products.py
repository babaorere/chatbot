from __future__ import annotations

import logging
import pytest

from scripts.seed_general_products import (
    GENERAL_PRODUCTS,
    PresentationValidationError,
    _find_presentation_collisions,
    _raise_for_similar_presentations,
)


def test_find_presentation_collisions_groups_by_family_and_format() -> None:
    collisions = _find_presentation_collisions(GENERAL_PRODUCTS)

    assert len(collisions) == 2
    assert {collision.normalized_value for collision in collisions} == {
        "pisco mistral:750ml",
        "pisco mistral:1000ml",
    }


def test_raise_for_similar_presentations_blocks_seed(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="seed_general_products"):
        with pytest.raises(PresentationValidationError):
            _raise_for_similar_presentations(GENERAL_PRODUCTS)

    assert any(
        "Colisión matemática detectada en presentaciones equivalentes" in record.message
        for record in caplog.records
    )
