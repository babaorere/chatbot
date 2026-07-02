from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.security import get_admin_api_key
from config.database import get_db
from services import UserService
from dtos.request import UserCreateRequest
from dtos.response import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_admin_api_key)],
)


@router.post("", response_model=UserResponse)
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> UserResponse:
    """Crea o recupera un usuario lógico a partir de su identificador externo de canal."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(
            external_id=data.external_id,
            platform=data.platform,
            display_name=data.display_name,
        )
        return UserResponse.model_validate(user)
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error("create_user failed [request_id=%s]: %s", request_id, e)
        raise HTTPException(500, f"Failed to create user: {e}")


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> UserResponse:
    """Recupera un usuario persistido por su identificador interno."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_by_id(user_id)
        if not user:
            logger.warning("User not found: user_id=%s", user_id)
            raise HTTPException(404, "User not found")
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error(
            "get_user failed [request_id=%s, user_id=%s]: %s", request_id, user_id, e
        )
        raise HTTPException(500, f"Failed to retrieve user: {e}")


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[UserResponse]:
    """Lista usuarios paginados para tareas administrativas o de soporte."""
    try:
        user_svc = UserService(db)
        users = user_svc.list_users(skip=skip, limit=limit)
        return [UserResponse.model_validate(u) for u in users]
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error("list_users failed [request_id=%s]: %s", request_id, e)
        raise HTTPException(500, f"Failed to list users: {e}")
