from __future__ import annotations

import pytest

from app.security import decode_signed_token
from models.tenant_auth import TenantPortalSession
from services.tenant_auth_service import TenantAuthService


def _bootstrap_tenant_user(db_session):
    service = TenantAuthService(db_session)
    with db_session.begin():
        _invite, raw_token = service.create_invite(
            email="equipo@negocio.cl",
            full_name="Equipo Negocio",
            role="manager",
        )
    with db_session.begin():
        user, invite, access_token, refresh_token = service.claim_invite(
            token=raw_token,
            full_name="Equipo Negocio",
            password="ClaveSegura#2026",
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
    return service, user, invite, access_token, refresh_token


def test_tenant_auth_claim_invite_creates_user_and_consumes_invitation(db_session):
    service = TenantAuthService(db_session)

    with db_session.begin():
        invite, raw_token = service.create_invite(
            email="equipo@negocio.cl",
            full_name="Equipo Negocio",
            role="manager",
        )

    with db_session.begin():
        user, consumed_invite, access_token, refresh_token = service.claim_invite(
            token=raw_token,
            full_name="Equipo Negocio",
            password="ClaveSegura#2026",
            user_agent="pytest",
            ip_address="127.0.0.1",
        )

    payload = decode_signed_token(access_token, expected_type="access")
    sessions = db_session.query(TenantPortalSession).filter_by(user_id=user.id).all()

    assert invite.email == "equipo@negocio.cl"
    assert user.email == "equipo@negocio.cl"
    assert user.password_hash is not None
    assert consumed_invite.used_at is not None
    assert refresh_token
    assert payload["sub"] == str(user.id)
    assert len(sessions) == 1


def test_tenant_auth_authenticate_wrong_password_raises(db_session):
    service, _, _, _, _ = _bootstrap_tenant_user(db_session)

    with pytest.raises(ValueError) as exc_info:
        with db_session.begin():
            service.authenticate(
                email="equipo@negocio.cl",
                password="ClaveIncorrecta#2026",
                user_agent="pytest",
                ip_address="127.0.0.1",
            )

    assert "Credenciales invalidas" in str(exc_info.value)


def test_tenant_auth_rotate_session_revokes_previous_refresh_token(db_session):
    service, user, _, _, refresh_token = _bootstrap_tenant_user(db_session)

    with db_session.begin():
        _, _access_token_2, refresh_token_2 = service.rotate_session(
            refresh_token=refresh_token,
            user_agent="pytest-rotate",
            ip_address="127.0.0.2",
        )

    sessions = (
        db_session.query(TenantPortalSession)
        .filter(TenantPortalSession.user_id == user.id)
        .order_by(TenantPortalSession.issued_at.asc())
        .all()
    )

    assert len(sessions) == 2
    assert sessions[0].revoked_at is not None
    assert sessions[1].revoked_at is None
    assert refresh_token != refresh_token_2


def test_tenant_auth_disable_user_revokes_active_sessions(db_session):
    service, user, _, _, _ = _bootstrap_tenant_user(db_session)

    with db_session.begin():
        updated_user = service.disable_user(user.id, disabled=True)

    sessions = db_session.query(TenantPortalSession).filter_by(user_id=user.id).all()

    assert updated_user.status == "disabled"
    assert updated_user.disabled_at is not None
    assert all(session.revoked_at is not None for session in sessions)
