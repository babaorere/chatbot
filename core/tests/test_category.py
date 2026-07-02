import pytest
from services.category_service import CategoryService
from services.product_service import ProductService


def test_category_crud_and_collision_prevention(db_session):
    cat_svc = CategoryService(db_session)
    prod_svc = ProductService(db_session)

    # 1. Verify default 'General' is present (seeded during lifespan/setup)
    general = cat_svc.get_category("General")
    assert general is not None
    assert general.is_system is True

    # 2. Create custom category
    pisco_cat = cat_svc.create_category("Pisco")
    assert pisco_cat.name == "Pisco"
    assert pisco_cat.slug == "pisco"

    # 3. Test exact name collision
    with pytest.raises(ValueError, match="ya existe"):
        cat_svc.create_category("Pisco")

    # 4. Test slug collision (e.g., case variance)
    with pytest.raises(ValueError, match="ya ocupa un identificador similar"):
        cat_svc.create_category("pisco")

    # 5. Test mathematical similarity collision using pg_trgm
    with pytest.raises(ValueError, match="Colisión matemática detectada"):
        cat_svc.create_category("Piscos")  # "Piscos" has >75% similarity to "Pisco"

    # 6. Test system protections
    with pytest.raises(ValueError, match="No se permite editar"):
        cat_svc.update_category("General", "General Modificado")

    with pytest.raises(ValueError, match="No se permite eliminar"):
        cat_svc.delete_category("General")

    # 7. Test delete cascades (set default 'General')
    # Create product in category 'Pisco'
    product = prod_svc.create_product(
        sku="PIS-001", name="Pisco Mistral", price=8990.00, stock=5, category="Pisco"
    )
    assert product.category == "Pisco"

    # Delete category 'Pisco'
    cat_svc.delete_category("Pisco")
    db_session.commit()

    # Verify category is deleted and product category fallback to 'General'
    db_session.refresh(product)
    assert product.category == "General"
