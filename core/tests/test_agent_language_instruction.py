from __future__ import annotations

from agents.constants import (
    GADK_INSTRUCTION,
    SPANISH_LANGUAGE_RULE,
    build_effective_instruction,
)
from infrastructure.llm.adk_provider import ADKLLMProvider


def test_build_effective_instruction_appends_spanish_rule_to_custom_prompt() -> None:
    base_instruction = "You are a helpful assistant."

    result = build_effective_instruction(base_instruction)

    assert base_instruction in result
    assert SPANISH_LANGUAGE_RULE in result


def test_build_effective_instruction_uses_default_prompt_when_missing() -> None:
    result = build_effective_instruction(None)

    assert GADK_INSTRUCTION in result
    assert SPANISH_LANGUAGE_RULE in result


def test_build_content_always_adds_final_spanish_directive() -> None:
    content = ADKLLMProvider._build_content("Hello", None)

    assert content.parts[0].text is not None
    assert "REGLA FINAL DE IDIOMA" in content.parts[0].text
    assert "responde exclusivamente en español" in content.parts[0].text
