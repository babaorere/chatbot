from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from config.database import get_db, safe_transaction
from services.category_service import CategoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Nombre de la categoría")


class CategoryUpdateRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=100, description="Nuevo nombre de la categoría")


@router.get("")
def list_categories(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        svc = CategoryService(db)
        categories = svc.list_categories()
        return [c.to_dict() for c in categories]
    except Exception as e:
        logger.error("Failed to list categories: %s", e)
        raise HTTPException(500, f"Error al listar categorías: {e}")


@router.post("")
def create_category(
    data: CategoryCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            category = svc.create_category(data.name)
        return {"status": "success", "category": category.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to create category: %s", e)
        raise HTTPException(500, f"Error al crear categoría: {e}")


@router.put("/{name}")
def update_category(
    name: str,
    data: CategoryUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            category = svc.update_category(name, data.new_name)
        return {"status": "success", "category": category.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to update category '%s': %s", name, e)
        raise HTTPException(500, f"Error al actualizar categoría: {e}")


@router.delete("/{name}")
def delete_category(
    name: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        svc = CategoryService(db)
        with safe_transaction(db):
            svc.delete_category(name)
        return {"status": "success", "message": f"Categoría '{name}' eliminada correctamente."}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to delete category '%s': %s", name, e)
        raise HTTPException(500, f"Error al eliminar categoría: {e}")
