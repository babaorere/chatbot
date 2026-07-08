from __future__ import annotations

from unittest.mock import MagicMock, patch

from controllers.admin_controller import (
    get_all_settings,
    get_system_admins,
    create_system_admin,
    update_system_admin,
    delete_system_admin,
)
from models.system_admin import SystemAdmin


def test_get_system_admins_returns_list():
    db_mock = MagicMock()
    admin_mock = MagicMock(spec=SystemAdmin)
    admin_mock.to_dict.return_value = {"id": 1, "name": "Admin Test"}
    db_mock.query.return_value.all.return_value = [admin_mock]

    result = get_system_admins(db=db_mock)
    assert len(result) == 1
    assert result[0]["name"] == "Admin Test"


def test_get_all_settings_injects_ui_language_default():
    db_mock = MagicMock()

    with patch("controllers.admin_controller.SysSettingRepo") as repo_mock:
        repo_instance = MagicMock()
        repo_instance.get_all_settings.return_value = {}
        repo_mock.return_value = repo_instance

        result = get_all_settings(db=db_mock)

    assert result["ui_language"] == "es-CL"


def test_create_system_admin_adds_to_db():
    db_mock = MagicMock()
    data = {
        "name": "New Admin",
        "email": "admin@test.com",
        "telegram_chat_id": "12345",
        "notify_telegram": True,
        "alert_types": ["error"],
    }

    # Simulate transactional block
    db_mock.begin.return_value.__enter__.return_value = MagicMock()

    result = create_system_admin(data=data, db=db_mock)
    assert db_mock.add.called
    assert result["name"] == "New Admin"
    assert result["alert_types"] == ["error"]


def test_update_system_admin_modifies_record():
    db_mock = MagicMock()
    admin_record = SystemAdmin(
        id=1,
        name="Old Name",
        email="old@test.com",
        telegram_chat_id="123",
        notify_telegram=True,
        alert_types=["latency"],
    )
    db_mock.query.return_value.filter.return_value.first.return_value = admin_record

    data = {
        "name": "Updated Name",
        "alert_types": ["error", "latency"],
    }

    db_mock.begin.return_value.__enter__.return_value = MagicMock()

    result = update_system_admin(admin_id=1, data=data, db=db_mock)
    assert admin_record.name == "Updated Name"
    assert admin_record.alert_types == ["error", "latency"]
    assert result["name"] == "Updated Name"


def test_delete_system_admin_removes_record():
    db_mock = MagicMock()
    admin_record = SystemAdmin(id=1, name="To Delete")
    db_mock.query.return_value.filter.return_value.first.return_value = admin_record

    db_mock.begin.return_value.__enter__.return_value = MagicMock()

    result = delete_system_admin(admin_id=1, db=db_mock)
    assert db_mock.delete.called
    assert result["status"] == "success"
