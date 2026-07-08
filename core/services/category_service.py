from __future__ import annotations

import unicodedata
from sqlalchemy.orm import Session
from sqlalchemy import text
from models.category import Category


def slugify(text_val: str) -> str:
    """Genera un slug limpio y simplificado a partir de un texto."""
    text_val = text_val.strip().lower()
    text_val = "".join(
        c
        for c in unicodedata.normalize("NFD", text_val)
        if unicodedata.category(c) != "Mn"
    )
    # Reemplazar caracteres no alfanuméricos por guiones sin usar regex
    parts: list[str] = []
    current: list[str] = []
    for ch in text_val:
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                parts.append("".join(current))
                current = []
    if current:
        parts.append("".join(current))
    return "-".join(parts)


def normalize_category_name(name: str) -> str:
    """Normaliza un nombre de categoría para comparación semántica básica (remueve acentos, minúsculas, y plurales simples)."""
    name = name.strip().lower()
    name = "".join(
        c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn"
    )
    # Regla básica de singularización en español
    if name.endswith("es"):
        name = name[:-2]
    elif name.endswith("s") and not name.endswith("is") and not name.endswith("us"):
        name = name[:-1]
    return name


class CategoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_categories(self) -> list[Category]:
        return self.db.query(Category).order_by(Category.name.asc()).all()

    def get_category(self, name: str) -> Category | None:
        return self.db.query(Category).filter(Category.name == name).first()

    def get_category_by_slug(self, slug: str) -> Category | None:
        return self.db.query(Category).filter(Category.slug == slug).first()

    def create_category(self, name: str) -> Category:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("El nombre de la categoría no puede estar vacío.")

        # Evitar colisión exacta
        existing = self.get_category(cleaned_name)
        if existing:
            raise ValueError(f"La categoría '{cleaned_name}' ya existe.")

        slug = slugify(cleaned_name)
        # Validar colisión por slug único
        existing_slug = self.db.query(Category).filter(Category.slug == slug).first()
        if existing_slug:
            raise ValueError(
                f"Colisión de slug: la categoría '{existing_slug.name}' ya ocupa un identificador similar."
            )

        # Validar colisión matemática de similitud usando pg_trgm en la base de datos
        # Excluimos categorías muy cortas para evitar falsos positivos
        if len(cleaned_name) > 3:
            similar = self.db.execute(
                text(
                    "SELECT name FROM categories WHERE similarity(name, :new_name) > 0.60 LIMIT 1;"
                ),
                {"new_name": cleaned_name},
            ).fetchone()
            if similar:
                raise ValueError(
                    f"Colisión matemática detectada: el nombre '{cleaned_name}' "
                    f"es demasiado similar a la categoría existente '{similar[0]}' (similitud > 60%)."
                )

        category = Category(name=cleaned_name, slug=slug, is_system=False)
        self.db.add(category)
        self.db.flush()
        return category

    def update_category(self, old_name: str, new_name: str) -> Category:
        cleaned_new = new_name.strip()
        if not cleaned_new:
            raise ValueError("El nuevo nombre no puede estar vacío.")

        category = self.get_category(old_name)
        if not category:
            raise ValueError("Categoría no encontrada.")

        if category.is_system or old_name == "General":
            raise ValueError("No se permite editar la categoría del sistema 'General'.")

        # Evitar colisión exacta con otras
        if cleaned_new != old_name:
            existing = self.get_category(cleaned_new)
            if existing:
                raise ValueError(f"La categoría '{cleaned_new}' ya existe.")

            slug = slugify(cleaned_new)
            existing_slug = (
                self.db.query(Category)
                .filter(Category.slug == slug, Category.name != old_name)
                .first()
            )
            if existing_slug:
                raise ValueError(
                    f"Colisión de slug: la categoría '{existing_slug.name}' ya ocupa un identificador similar."
                )

            if len(cleaned_new) > 3:
                similar = self.db.execute(
                    text(
                        "SELECT name FROM categories WHERE name != :old_name AND similarity(name, :new_name) > 0.60 LIMIT 1;"
                    ),
                    {"old_name": old_name, "new_name": cleaned_new},
                ).fetchone()
                if similar:
                    raise ValueError(
                        f"Colisión matemática detectada: el nombre '{cleaned_new}' "
                        f"es demasiado similar a la categoría existente '{similar[0]}' (similitud > 60%)."
                    )

            # Actualizar primary key cascades values in products thanks to ON UPDATE CASCADE
            category.name = cleaned_new
            category.slug = slug

        self.db.flush()
        return category

    def delete_category(self, name: str) -> None:
        category = self.get_category(name)
        if not category:
            raise ValueError("Categoría no encontrada.")

        if category.is_system or name == "General":
            raise ValueError(
                "No se permite eliminar la categoría del sistema 'General'."
            )

        self.db.delete(category)
        self.db.flush()
