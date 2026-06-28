from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from config.database import SessionLocal
from services.kb_service import KBService
from services.embedding_service import EmbeddingService
from repositories.kb_repository import KBRepository
from models.knowledge_base import KnowledgeBase


@pytest.mark.asyncio
async def test_embedding_service_mock_and_real_fallbacks():
    """Prueba que el EmbeddingService genere vectores de 1536 floats tanto para texto real como determinista ficticio."""
    emb_svc = EmbeddingService()

    # Entrada vacía
    v_empty = await emb_svc.get_embedding("")
    assert len(v_empty) == 1536
    assert all(x == 0.0 for x in v_empty)

    # Entrada de texto normal (debería llamar al mock determinista si la API key no está activa)
    v_text = await emb_svc.get_embedding("¿Cuál es el horario de delivery?")
    assert len(v_text) == 1536
    # Al menos algunos valores deben ser no-cero
    assert any(x != 0.0 for x in v_text)


@pytest.mark.asyncio
async def test_kb_service_hybrid_search_integration():
    """Prueba de integración de creación y búsqueda híbrida en la base de datos."""
    db: Session = SessionLocal()
    kb_svc = KBService(db)
    
    try:
        # 1. Crear entradas en la base de conocimientos
        entry1 = await kb_svc.create_entry(
            category="horarios",
            title="Horario de Atención General",
            content="Atendemos de lunes a sábado desde las 10:00 hasta las 22:00 horas. Domingos de 12:00 a 20:00 horas."
        )
        
        await kb_svc.create_entry(
            category="delivery",
            title="Cobertura y Despacho a Domicilio",
            content="Realizamos envíos a toda la comuna de Santiago de lunes a viernes entre las 11:00 y las 19:00 horas."
        )

        assert entry1.id is not None
        assert entry1.embedding is not None
        assert len(entry1.embedding) == 1536

        # 2. Realizar búsqueda híbrida (semántica + FTS) para horario
        results = await kb_svc.search(query="a qué hora abren?", top_k=2)
        assert len(results) > 0
        # El primer resultado debería ser el del horario debido a la relevancia semántica
        assert results[0]["title"] == "Horario de Atención General"

        # 3. Realizar búsqueda híbrida para despacho
        results_delivery = await kb_svc.search(query="envían a domicilio?", top_k=2)
        assert len(results_delivery) > 0
        assert results_delivery[0]["title"] == "Cobertura y Despacho a Domicilio"

        # 4. Búsqueda filtrada por categoría
        results_filtered = await kb_svc.search(query="delivery", top_k=5, category="horarios")
        for r in results_filtered:
            assert r["category"] == "horarios"

    finally:
        # Limpiar registros creados
        db.query(KnowledgeBase).filter(KnowledgeBase.category.in_(["horarios", "delivery"])).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_search_hybrid_fallback_to_fts_without_vector():
    """Prueba que el KBRepository use FTS puro si el vector es None."""
    db: Session = SessionLocal()
    repo = KBRepository(db)
    try:
        # Invocar search_hybrid con query_vector=None
        results = repo.search_hybrid(query="cobertura", query_vector=None, top_k=5)
        # Debería ejecutar la rama de FTS puro sin crashear
        assert isinstance(results, list)
    finally:
        db.close()
