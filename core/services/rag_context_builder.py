from __future__ import annotations

import logging

from services.kb_service import KBService

logger = logging.getLogger(__name__)


class RAGContextBuilder:
    """
    Builds RAG context from knowledge base and injects it into
    the LLM system prompt.

    Pattern:
    1. Search KB with FTS Spanish
    2. Format results into XML-like block
    3. Append to system instruction
    """

    def __init__(self, kb_service: KBService) -> None:
        self.kb_service = kb_service

    async def build_context(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> str:
        try:
            entries = self.kb_service.search(query, top_k=top_k, category=category)
            if not entries:
                return ""

            context = "<KNOWLEDGE_BASE_CONTEXT>\n"
            context += "Información relevante de la base de conocimiento:\n\n"
            for i, entry in enumerate(entries, 1):
                context += f"[{i}] {entry['title']} ({entry['category']})\n"
                context += f"    {entry['content']}\n\n"
            context += "</KNOWLEDGE_BASE_CONTEXT>"

            return context
        except Exception as e:
            logger.error(
                "RAGContextBuilder.build_context failed [query=%s]: %s",
                query,
                e,
            )
            raise

    def inject_into_instruction(
        self,
        base_instruction: str,
        rag_context: str,
    ) -> str:
        if not rag_context:
            return base_instruction

        return (
            f"{base_instruction}\n\n"
            f"{rag_context}\n\n"
            f"Usa la información anterior para responder con precisión. "
            f"Si la información no es suficiente, responde honestamente "
            f"y ofrece contactar a un humano."
        )
