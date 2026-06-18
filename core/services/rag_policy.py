"""
RAGPolicyService — Política de acceso RAG a nivel de aplicación.

Determina si una consulta de usuario debe alimentar el pipeline RAG
(recuperación de contexto de la base de conocimiento) o si debe ser
bloqueada porque corresponde a consultas de productos, stock, precios,
catálogo o intención de compra. Esos casos deben resolverse exclusivamente
con las herramientas ADK `consultar_stock` y `consultar_precio`.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class RAGIntent(StrEnum):
    """Intención clasificada para el uso de RAG."""

    GENERAL_SERVICE = "general_service"
    PRODUCT_SALES = "product_sales"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RAGPolicyResult:
    """Resultado de la clasificación de política RAG.

    Attributes:
        allowed: Si ``True``, se debe construir contexto RAG para la query.
        intent: Intención inferida para la consulta.
        reason: Explicación de la decisión para logging/debugging.
    """

    allowed: bool
    intent: RAGIntent
    reason: str


class RAGPolicyService:
    """Clasifica consultas de usuario para determinar si RAG debe aplicarse.

    La política es defensiva: ante consultas ambiguas o relacionadas con
    productos, stock, precios o compra, se evita RAG y se delega la respuesta
    al LLM sin contexto de KB o a las herramientas reales del agente.
    """

    RAG_SAFE_CATEGORIES: tuple[str, ...] = (
        "horarios",
        "horario",
        "zonas_atencion",
        "zona_atencion",
        "zonas",
        "zona",
        "cobertura",
        "delivery",
        "despacho",
        "formas_pago",
        "forma_pago",
        "pagos",
        "pago",
        "servicios",
        "servicio",
        "informacion_general",
        "informacion_servicio",
        "general",
    )

    _RAG_BLOCKED_CATEGORIES: tuple[str, ...] = (
        "productos",
        "producto",
        "catalogo",
        "catalogo_productos",
        "stock",
        "precios",
        "precio",
        "ventas",
        "venta",
        "compras",
        "compra",
    )

    _STOCK_KEYWORDS: tuple[str, ...] = (
        "stock",
        "disponible",
        "disponibilidad",
        "quedan",
        "queda",
    )

    _SOFT_STOCK_KEYWORDS: tuple[str, ...] = (
        "tienen",
        "hay",
        "venden",
    )

    _PRICE_KEYWORDS: tuple[str, ...] = (
        "precio",
        "precios",
        "vale",
        "valor",
        "cuesta",
        "cuestan",
        "costo",
        "cuanto",
        "cotizacion",
        "cotizame",
        "cotizar",
        "oferta",
        "ofertas",
        "descuento",
        "descuentos",
        "rebaja",
        "barato",
        "caro",
    )

    _PURCHASE_KEYWORDS: tuple[str, ...] = (
        "comprar",
        "compra",
        "compras",
        "pedido",
        "pedidos",
        "pedir",
        "encargar",
        "encargo",
        "llevar",
        "quiero",
        "necesito",
        "busco",
        "dame",
        "me das",
        "ordenar",
        "reservar",
        "reserva",
    )

    _PRODUCT_KEYWORDS: tuple[str, ...] = (
        "licor",
        "licores",
        "cerveza",
        "cervezas",
        "vino",
        "vinos",
        "pisco",
        "whisky",
        "ron",
        "vodka",
        "tequila",
        "gin",
        "rum",
        "champagne",
        "espumante",
        "botella",
        "botellas",
        "caja",
        "cajas",
        "pack",
        "packs",
        "lata",
        "latas",
        "producto",
        "productos",
        "catalogo",
        "santa carolina",
        "casillero",
        "control",
        "kunstmann",
        "aura",
        "johnnie walker",
        "jack daniels",
        "absolut",
        "smirnoff",
    )

    _SAFE_KEYWORDS: tuple[str, ...] = (
        "horario",
        "horarios",
        "hora",
        "horas",
        "abierto",
        "abierta",
        "abiertos",
        "abiertas",
        "atienden",
        "atencion",
        "zona",
        "zonas",
        "comuna",
        "comunas",
        "cobertura",
        "delivery",
        "despacho",
        "pago",
        "pagos",
        "transferencia",
        "efectivo",
        "tarjeta",
        "tarjetas",
        "metodo",
        "metodos",
        "servicio",
        "servicios",
        "hacen",
        "cubren",
        "aceptan",
        "ubicacion",
        "direccion",
    )

    def classify(self, query: str) -> RAGPolicyResult:
        """Clasifica una query y determina si RAG debe aplicarse.

        Args:
            query: Texto de la consulta del usuario.

        Returns:
            RAGPolicyResult con la decisión, intención y razón.
        """
        normalized: str = self._normalize(query)

        has_price: bool = self._contains_any_keyword(normalized, self._PRICE_KEYWORDS)
        has_purchase: bool = self._contains_any_keyword(
            normalized, self._PURCHASE_KEYWORDS
        )
        has_direct_stock: bool = self._contains_any_keyword(
            normalized, self._STOCK_KEYWORDS
        )
        has_soft_stock: bool = self._contains_any_keyword(
            normalized, self._SOFT_STOCK_KEYWORDS
        )
        has_product: bool = self._contains_any_keyword(
            normalized, self._PRODUCT_KEYWORDS
        )
        has_safe_intent: bool = self._contains_any_keyword(
            normalized, self._SAFE_KEYWORDS
        )

        if has_price or has_purchase or has_direct_stock:
            return self._blocked(
                normalized,
                RAGIntent.PRODUCT_SALES,
                "query appears to be about stock/prices/purchase — should use tools instead",
            )

        if has_product:
            return self._blocked(
                normalized,
                RAGIntent.PRODUCT_SALES,
                "query appears to mention a product — should use product tools instead",
            )

        if has_soft_stock and not has_safe_intent:
            return self._blocked(
                normalized,
                RAGIntent.PRODUCT_SALES,
                "query asks general availability without a RAG-safe service topic",
            )

        if has_safe_intent:
            return RAGPolicyResult(
                allowed=True,
                intent=RAGIntent.GENERAL_SERVICE,
                reason="query is about general business service information",
            )

        return RAGPolicyResult(
            allowed=False,
            intent=RAGIntent.UNKNOWN,
            reason="query does not match any RAG-safe general-service topic",
        )

    def is_rag_allowed(self, query: str) -> bool:
        """Retorna si una query puede usar RAG.

        Args:
            query: Texto de la consulta del usuario.

        Returns:
            ``True`` cuando RAG puede construir contexto, ``False`` cuando
            debe omitirse.
        """
        return self.classify(query).allowed

    def is_blocked_category(self, category: str | None) -> bool:
        """Retorna si una categoría de KB debe excluirse de RAG.

        Args:
            category: Categoría almacenada en la base de conocimiento.

        Returns:
            ``True`` cuando la categoría no es segura para RAG.
        """
        if not category:
            return False

        normalized: str = self._normalize(category)
        return normalized in set(self._RAG_BLOCKED_CATEGORIES)

    def is_safe_category(self, category: str | None) -> bool:
        """Retorna si una categoría de KB es segura para RAG.

        Args:
            category: Categoría almacenada en la base de conocimiento.

        Returns:
            ``True`` cuando la categoría pertenece al conjunto permitido.
        """
        if not category:
            return True

        normalized: str = self._normalize(category)
        return normalized in set(self.RAG_SAFE_CATEGORIES)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza texto para comparación insensible a acentos y casing.

        Convierte a minúsculas, elimina diacríticos y reemplaza ``ñ`` por
        ``n`` para permitir matching robusto contra las listas de keywords.

        Args:
            text: Texto a normalizar.

        Returns:
            Texto normalizado en minúsculas sin acentos.
        """
        nfkd: str = unicodedata.normalize("NFKD", text.lower())
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    def _blocked(
        self, normalized_query: str, intent: RAGIntent, reason: str
    ) -> RAGPolicyResult:
        logger.debug(
            "RAG blocked [reason=%s, query='%s']", reason, normalized_query[:80]
        )
        return RAGPolicyResult(allowed=False, intent=intent, reason=reason)

    @staticmethod
    def _contains_any_keyword(normalized_query: str, keywords: tuple[str, ...]) -> bool:
        return any(
            RAGPolicyService._contains_keyword(normalized_query, keyword)
            for keyword in keywords
        )

    @staticmethod
    def _contains_keyword(normalized_query: str, keyword: str) -> bool:
        escaped: str = re.escape(keyword)
        pattern: str = rf"(?<!\w){escaped}(?!\w)"
        return re.search(pattern, normalized_query) is not None
