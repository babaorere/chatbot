from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.security import create_access_token
from config.settings import settings
from dtos.request.tenant_auth_request import TenantAuthContext
from models.tenant_auth import (
    TenantPortalInvite,
    TenantPortalSession,
    TenantPortalUser,
)


class TenantAuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _hash_secret(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _encode_password_hash(iterations: int, salt: bytes, digest: bytes) -> str:
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"

    @classmethod
    def _decode_password_hash(cls, value: str) -> tuple[int, bytes, bytes]:
        algorithm, raw_iterations, salt_b64, digest_b64 = value.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            raise ValueError("Unsupported password hash algorithm")
        return (
            int(raw_iterations),
            base64.b64decode(salt_b64.encode("ascii")),
            base64.b64decode(digest_b64.encode("ascii")),
        )

    @staticmethod
    def _validate_password_strength(password: str) -> None:
        if len(password) < 12:
            raise ValueError("La contrasena debe tener al menos 12 caracteres.")
        if password.strip() != password:
            raise ValueError("La contrasena no puede comenzar ni terminar con espacios.")
        checks = [
            any(ch.islower() for ch in password),
            any(ch.isupper() for ch in password),
            any(ch.isdigit() for ch in password),
            any(not ch.isalnum() for ch in password),
        ]
        if not all(checks):
            raise ValueError(
                "La contrasena debe incluir mayusculas, minusculas, numeros y simbolos."
            )

    @classmethod
    def hash_password(cls, password: str) -> str:
        cls._validate_password_strength(password)
        iterations = 600_000
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return cls._encode_password_hash(iterations, salt, digest)

    @classmethod
    def verify_password(cls, password: str, encoded_hash: str | None) -> bool:
        if not encoded_hash:
            return False
        try:
            iterations, salt, expected_digest = cls._decode_password_hash(encoded_hash)
        except (ValueError, TypeError):
            return False
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual_digest, expected_digest)

    def _build_context(
        self, user_agent: str | None = None, ip_address: str | None = None
    ) -> TenantAuthContext:
        return TenantAuthContext(user_agent=user_agent, ip_address=ip_address)

    def _get_active_user(self, user_id: int) -> TenantPortalUser | None:
        user = (
            self.db.query(TenantPortalUser)
            .filter(TenantPortalUser.id == user_id)
            .first()
        )
        if not user:
            return None
        if user.disabled_at is not None or user.status != "active":
            return None
        return user

    def _create_session(
        self,
        user: TenantPortalUser,
        context: TenantAuthContext,
        *,
        now: datetime,
        rotated_from_session_id: str | None = None,
    ) -> tuple[TenantPortalSession, str, str]:
        refresh_token = secrets.token_urlsafe(48)
        refresh_hash = self._hash_secret(refresh_token)
        session = TenantPortalSession(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            user_agent=context.user_agent,
            ip_address=context.ip_address,
            expires_at=now + timedelta(days=settings.tenant_refresh_token_ttl_days),
            rotated_from_session_id=rotated_from_session_id,
        )
        self.db.add(session)
        self.db.flush()

        access_token = create_access_token(
            subject=str(user.id),
            role=user.role,
            auth_version=user.auth_version,
            expires_in=timedelta(minutes=settings.tenant_access_token_ttl_minutes),
            issued_at=now,
        )
        return session, access_token, refresh_token

    def create_invite(
        self,
        *,
        email: str,
        full_name: str | None,
        role: str,
        created_by_admin_id: int | None = None,
    ) -> tuple[TenantPortalInvite, str]:
        normalized_email = self._normalize_email(email)
        now = self._now()

        for active_invite in (
            self.db.query(TenantPortalInvite)
            .filter(
                TenantPortalInvite.email == normalized_email,
                TenantPortalInvite.used_at.is_(None),
                TenantPortalInvite.revoked_at.is_(None),
            )
            .all()
        ):
            active_invite.revoked_at = now

        raw_token = secrets.token_urlsafe(48)
        invite = TenantPortalInvite(
            email=normalized_email,
            full_name=full_name.strip() if full_name else None,
            role=role,
            token_hash=self._hash_secret(raw_token),
            expires_at=now + timedelta(hours=settings.tenant_invite_ttl_hours),
            created_by_admin_id=created_by_admin_id,
        )
        self.db.add(invite)
        self.db.flush()
        self.db.refresh(invite)
        return invite, raw_token

    def list_invites(self, *, limit: int = 50) -> list[TenantPortalInvite]:
        return (
            self.db.query(TenantPortalInvite)
            .order_by(TenantPortalInvite.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_users(self, *, limit: int = 100) -> list[TenantPortalUser]:
        return (
            self.db.query(TenantPortalUser)
            .order_by(TenantPortalUser.created_at.desc())
            .limit(limit)
            .all()
        )

    def revoke_invite(self, invite_id: str) -> TenantPortalInvite:
        invite = (
            self.db.query(TenantPortalInvite)
            .filter(TenantPortalInvite.id == invite_id)
            .first()
        )
        if not invite:
            raise ValueError("Invitacion no encontrada.")
        if invite.used_at is not None:
            raise ValueError("La invitacion ya fue utilizada.")
        invite.revoked_at = self._now()
        self.db.flush()
        return invite

    def disable_user(self, user_id: int, *, disabled: bool) -> TenantPortalUser:
        user = (
            self.db.query(TenantPortalUser)
            .filter(TenantPortalUser.id == user_id)
            .first()
        )
        if not user:
            raise ValueError("Usuario tenant no encontrado.")

        now = self._now()
        if disabled:
            user.status = "disabled"
            user.disabled_at = now
            user.auth_version += 1
            for session in (
                self.db.query(TenantPortalSession)
                .filter(
                    TenantPortalSession.user_id == user.id,
                    TenantPortalSession.revoked_at.is_(None),
                )
                .all()
            ):
                session.revoked_at = now
        else:
            user.status = "active"
            user.disabled_at = None
            user.auth_version += 1

        self.db.flush()
        return user

    def claim_invite(
        self,
        *,
        token: str,
        full_name: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[TenantPortalUser, TenantPortalInvite, str, str]:
        self._validate_password_strength(password)

        invite = (
            self.db.query(TenantPortalInvite)
            .filter(TenantPortalInvite.token_hash == self._hash_secret(token))
            .first()
        )
        now = self._now()
        if not invite:
            raise ValueError("La invitacion no es valida o ya expiro.")
        if invite.revoked_at is not None:
            raise ValueError("La invitacion fue revocada por un administrador.")
        if invite.used_at is not None:
            raise ValueError("La invitacion ya fue utilizada.")
        if invite.expires_at < now:
            raise ValueError("La invitacion expiro. Solicite una nueva.")
        if invite.attempt_count >= invite.max_attempts:
            raise ValueError("La invitacion fue bloqueada por demasiados intentos.")

        invite.attempt_count += 1

        normalized_email = self._normalize_email(invite.email)
        user = (
            self.db.query(TenantPortalUser)
            .filter(TenantPortalUser.email == normalized_email)
            .first()
        )
        if not user:
            user = TenantPortalUser(
                email=normalized_email,
                full_name=full_name.strip(),
                role=invite.role,
                status="active",
                password_hash=self.hash_password(password),
                password_set_at=now,
                last_login_at=now,
            )
            self.db.add(user)
            self.db.flush()
        else:
            user.full_name = full_name.strip()
            user.role = invite.role
            user.status = "active"
            user.disabled_at = None
            user.password_hash = self.hash_password(password)
            user.password_set_at = now
            user.last_login_at = now
            user.auth_version += 1
            self.db.flush()

        invite.used_at = now
        context = self._build_context(user_agent=user_agent, ip_address=ip_address)
        _, access_token, refresh_token = self._create_session(
            user,
            context,
            now=now,
        )
        self.db.flush()
        self.db.refresh(user)
        self.db.refresh(invite)
        return user, invite, access_token, refresh_token

    def authenticate(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[TenantPortalUser, str, str]:
        normalized_email = self._normalize_email(email)
        user = (
            self.db.query(TenantPortalUser)
            .filter(TenantPortalUser.email == normalized_email)
            .first()
        )
        if (
            not user
            or user.disabled_at is not None
            or user.status != "active"
            or not self.verify_password(password, user.password_hash)
        ):
            raise ValueError("Credenciales invalidas.")

        now = self._now()
        user.last_login_at = now
        context = self._build_context(user_agent=user_agent, ip_address=ip_address)
        _, access_token, refresh_token = self._create_session(
            user,
            context,
            now=now,
        )
        self.db.flush()
        return user, access_token, refresh_token

    def rotate_session(
        self,
        *,
        refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[TenantPortalUser, str, str]:
        now = self._now()
        session = (
            self.db.query(TenantPortalSession)
            .filter(
                TenantPortalSession.refresh_token_hash
                == self._hash_secret(refresh_token),
                TenantPortalSession.revoked_at.is_(None),
            )
            .first()
        )
        if not session or session.expires_at < now:
            raise ValueError("La sesion expiro. Vuelva a ingresar.")

        user = self._get_active_user(session.user_id)
        if not user:
            session.revoked_at = now
            self.db.flush()
            raise ValueError("La sesion ya no es valida.")

        session.revoked_at = now
        session.last_seen_at = now
        user.last_login_at = now

        context = self._build_context(user_agent=user_agent, ip_address=ip_address)
        _, access_token, new_refresh_token = self._create_session(
            user,
            context,
            now=now,
            rotated_from_session_id=session.id,
        )
        self.db.flush()
        return user, access_token, new_refresh_token

    def revoke_refresh_session(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        session = (
            self.db.query(TenantPortalSession)
            .filter(
                TenantPortalSession.refresh_token_hash
                == self._hash_secret(refresh_token),
                TenantPortalSession.revoked_at.is_(None),
            )
            .first()
        )
        if not session:
            return
        session.revoked_at = self._now()
        self.db.flush()

    def get_active_user_by_id(self, user_id: int) -> TenantPortalUser | None:
        return self._get_active_user(user_id)

    def change_password(
        self,
        *,
        user: TenantPortalUser,
        current_password: str,
        new_password: str,
    ) -> TenantPortalUser:
        if not self.verify_password(current_password, user.password_hash):
            raise ValueError("La contrasena actual no coincide.")

        now = self._now()
        user.password_hash = self.hash_password(new_password)
        user.password_set_at = now
        user.auth_version += 1

        for session in (
            self.db.query(TenantPortalSession)
            .filter(
                TenantPortalSession.user_id == user.id,
                TenantPortalSession.revoked_at.is_(None),
            )
            .all()
        ):
            session.revoked_at = now

        self.db.flush()
        return user

    @staticmethod
    def build_invite_url(raw_token: str) -> str:
        return f"/tenant/?invite={raw_token}"
