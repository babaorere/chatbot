from __future__ import annotations

from typing import Generic, TypeVar, Type, Optional, List, Any

from sqlalchemy.orm import Session

from config.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class JpaRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session) -> None:
        self.model = model
        self.db = db

    def find_by_id(self, id: int) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def find_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def find_by(self, **filters: Any) -> List[ModelType]:
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.all()

    def find_one_by(self, **filters: Any) -> Optional[ModelType]:
        results = self.find_by(**filters)
        return results[0] if results else None

    def save(self, instance: ModelType) -> ModelType:
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return instance

    def save_all(self, instances: List[ModelType]) -> List[ModelType]:
        self.db.add_all(instances)
        self.db.flush()
        for instance in instances:
            self.db.refresh(instance)
        return instances

    def delete_by_id(self, id: int) -> bool:
        instance = self.find_by_id(id)
        if instance:
            self.db.delete(instance)
            self.db.flush()
            return True
        return False

    def count(self, **filters: Any) -> int:
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.count()

    def exists_by(self, **filters: Any) -> bool:
        return self.count(**filters) > 0
