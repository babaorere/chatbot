from __future__ import annotations

from unittest.mock import MagicMock, patch

from controllers.business_config_controller import update_profile


def test_update_profile_refreshes_human_agent_cache() -> None:
    db_mock = MagicMock()
    config_mock = MagicMock()
    config_mock.human_agent_available = False

    with (
        patch(
            "controllers.business_config_controller.BusinessConfigService"
        ) as svc_mock,
        patch(
            "controllers.business_config_controller.prime_human_agent_cache"
        ) as prime_mock,
        patch(
            "controllers.business_config_controller.BusinessConfigResponse.model_validate",
            return_value={"ok": True},
        ),
    ):
        svc_instance = MagicMock()
        svc_instance.update_config.return_value = config_mock
        svc_mock.return_value = svc_instance

        result = update_profile(
            data=MagicMock(
                name=None,
                email=None,
                phone=None,
                address=None,
                city=None,
                website=None,
                logo_url=None,
                business_hours=None,
                promotions_config=None,
                best_sellers_config=None,
                favorites_config=None,
                estimated_attention_minutes=45,
                human_agent_available=False,
            ),
            db=db_mock,
        )

    prime_mock.assert_called_once_with(False)
    svc_instance.update_config.assert_called_once()
    update_kwargs = svc_instance.update_config.call_args.kwargs
    assert update_kwargs["promotions_config"] is None
    assert update_kwargs["best_sellers_config"] is None
    assert update_kwargs["favorites_config"] is None
    assert update_kwargs["estimated_attention_minutes"] == 45
    assert result == {"ok": True}
