from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def transactional(func: Callable[..., Any]) -> Callable[..., Any]:
    """Envuelve una función para hacer commit o rollback automático si encuentra una sesión SQLAlchemy."""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        db: Session | None = None
        for arg in args:
            if isinstance(arg, Session):
                db = arg
                break
        if not db:
            db = getattr(args[0], "db", None) if args else None

        if not db:
            return func(*args, **kwargs)

        try:
            result = func(*args, **kwargs)
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            logger.error("Transaction rolled back in %s: %s", func.__name__, e)
            raise

    return wrapper
