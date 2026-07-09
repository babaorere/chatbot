from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.security import require_tenant_or_admin_access
from config.database import get_db, safe_transaction
from services.category_service import CategoryService
from services.catalog_cache_service import refresh_catalog_cache_after_commit

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
    dependencies=[Depends(require_tenant_or_admin_access)],
)


class CategoryCreateRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=100, description="Nombre de la categoría"
    )


class CategoryUpdateRequest(BaseModel):
    new_name: str = Field(
        ..., min_length=1, max_length=100, description="Nuevo nombre de la categoría"
    )


@router.get("")
def list_categories(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lista todas las categorías disponibles para clasificación de productos."""
    try:
        svc = CategoryService(db)
        categories = svc.list_categories()
        return [c.to_dict() for c in categories]
    except Exception as e:
        logger.error("Failed to list categories: %s", e)
        raise HTTPException(500, "Error al listar categorías")


@router.post("")
def create_category(
    data: CategoryCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crea una nueva categoría de productos protegida por la API key administrativa."""
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            category = svc.create_category(data.name)
        refresh_catalog_cache_after_commit("category_created")
        return {"status": "success", "category": category.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to create category: %s", e)
        raise HTTPException(500, "Error al crear categoría")


@router.put("/{name}")
def update_category(
    name: str,
    data: CategoryUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Renombra una categoría existente dentro de una transacción segura."""
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            category = svc.update_category(name, data.new_name)
        refresh_catalog_cache_after_commit("category_updated")
        return {"status": "success", "category": category.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to update category '%s': %s", name, e)
        raise HTTPException(500, "Error al actualizar categoría")


@router.delete("/{name}")
def delete_category(
    name: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Elimina una categoría existente protegida por la API key administrativa."""
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            svc.delete_category(name)
        refresh_catalog_cache_after_commit("category_deleted")
        return {
            "status": "success",
            "message": f"Categoría '{name}' eliminada correctamente.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to delete category '%s': %s", name, e)
        raise HTTPException(500, "Error al eliminar categoría")
