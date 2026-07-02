from __future__ import annotations

import logging
import litellm
from config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.api_key = settings.openrouter_api_key
        # Usamos un modelo estándar de embeddings de OpenAI/OpenRouter
        self.model = "openrouter/openai/text-embedding-3-small"

    async def get_embedding(self, text: str) -> list[float]:
        """Genera el vector de embeddings para el texto provisto.

        Si falla o no hay API key de OpenRouter, genera un vector determinista ficticio
        de 1536 dimensiones para asegurar robustez en local y pruebas.
        """
        if not text or not text.strip():
            return [0.0] * 1536

        if not self.api_key or self.api_key == "dummy_key":
            logger.warning(
                "No OpenRouter API key found. Using mock deterministic embedding vector."
            )
            return self._mock_embedding(text)

        try:
            # Invocar embedding asíncronamente con LiteLLM
            response = await litellm.aembedding(
                model=self.model,
                input=[text],
                api_key=self.api_key,
            )
            # Extraer vector resultante
            vector = response["data"][0]["embedding"]
            return [float(x) for x in vector]
        except Exception as e:
            logger.error(
                "Failed to generate real embedding via LiteLLM: %s. Falling back to mock.",
                e,
            )
            return self._mock_embedding(text)

    def _mock_embedding(self, text: str) -> list[float]:
        """Genera un vector determinista de 1536 floats basado en el string."""
        import hashlib

        h = hashlib.sha256(text.encode("utf-8")).digest()
        vector = []
        for i in range(1536):
            # Derivar float determinista entre -1.0 y 1.0
            idx = i % 32
            val = (h[idx] ^ i) / 255.0
            vector.append(val)
        return vector
