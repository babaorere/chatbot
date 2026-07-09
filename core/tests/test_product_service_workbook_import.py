from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.product_service import FIELD_NAMES, ProductService


def test_load_import_rows_from_workbook_bytes_skips_blank_rows_and_maps_fields() -> None:
    db_mock = MagicMock()
    service = ProductService(db_mock)
    row_values = [None for _ in FIELD_NAMES]
    row_values[FIELD_NAMES.index("sku")] = "SKU-1"
    row_values[FIELD_NAMES.index("name")] = "Producto importado"
    row_values[FIELD_NAMES.index("price")] = 1290

    workbook_mock = MagicMock()
    workbook_mock.active.iter_rows.return_value = [
        tuple(row_values),
        tuple(None for _ in FIELD_NAMES),
    ]

    with patch("services.product_service.load_workbook", return_value=workbook_mock):
        rows = service.load_import_rows_from_workbook_bytes(b"xlsx")

    assert rows == [
        {
            "sku": "SKU-1",
            "name": "Producto importado",
            "description": None,
            "price": 1290,
            "cost": None,
            "stock": None,
            "format": None,
            "unit_of_measure": None,
            "category": None,
            "provider": None,
            "taxes": None,
            "is_available": None,
            "margin": None,
        }
    ]


def test_import_from_workbook_bytes_returns_rows_processed_summary() -> None:
    db_mock = MagicMock()
    service = ProductService(db_mock)

    with (
        patch.object(
            service,
            "load_import_rows_from_workbook_bytes",
            return_value=[{"name": "Uno"}, {"name": "Dos"}],
        ) as load_rows_mock,
        patch.object(
            service,
            "import_from_rows",
            return_value={"created": 2, "updated": 0, "errors": 0},
        ) as import_rows_mock,
    ):
        result = service.import_from_workbook_bytes(b"xlsx")

    assert result == {
        "rows_processed": 2,
        "created": 2,
        "updated": 0,
        "errors": 0,
    }
    load_rows_mock.assert_called_once_with(b"xlsx")
    import_rows_mock.assert_called_once_with([{"name": "Uno"}, {"name": "Dos"}])
