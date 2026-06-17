from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Protocol
from urllib.parse import quote

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.events.event import Event
from google.adk.platform import time as platform_time
from google.adk.platform import uuid as platform_uuid
from google.adk.sessions import Session
from google.adk.sessions import _session_util
from google.adk.sessions.base_session_service import BaseSessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.adk.sessions.base_session_service import ListSessionsResponse
from google.adk.sessions.state import State
from redis.exceptions import LockError

logger = logging.getLogger(__name__)


class AsyncRedisLockProtocol(Protocol):
    async def acquire(
        self,
        blocking: bool | None = None,
        blocking_timeout: int | float | None = None,
        token: str | bytes | None = None,
    ) -> bool: ...

    async def release(self) -> None: ...


class AsyncRedisClientProtocol(Protocol):
    async def get(self, name: str) -> str | None: ...

    async def set(
        self, name: str, value: str, ex: int | None = None
    ) -> bool | None: ...

    async def delete(self, *names: str) -> int: ...

    async def expire(self, name: str, time: int) -> bool: ...

    async def hgetall(self, name: str) -> dict[str, str]: ...

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
        items: list[tuple[str, str]] | None = None,
    ) -> int: ...

    def lock(
        self,
        name: str,
        timeout: float | None = None,
        sleep: float = 0.1,
        blocking: bool = True,
        blocking_timeout: int | float | None = None,
        thread_local: bool = True,
        raise_on_release_error: bool = True,
    ) -> AsyncRedisLockProtocol: ...

    def scan_iter(self, match: str | None = None) -> AsyncIterator[str]: ...


class RedisSessionService(BaseSessionService):
    """Persist ADK sessions in Redis for multi-worker production deployments."""

    def __init__(
        self,
        redis_client: AsyncRedisClientProtocol,
        *,
        namespace: str,
        session_ttl_seconds: int,
        lock_timeout_seconds: float,
        lock_blocking_timeout_seconds: float,
    ) -> None:
        self._redis = redis_client
        self._namespace = namespace.rstrip(":")
        self._session_ttl_seconds = session_ttl_seconds
        self._lock_timeout_seconds = lock_timeout_seconds
        self._lock_blocking_timeout_seconds = lock_blocking_timeout_seconds

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        async with self._session_lock(
            app_name=app_name,
            user_id=user_id,
            session_id=normalized_session_id,
        ):
            existing = await self._load_storage_session(
                app_name=app_name,
                user_id=user_id,
                session_id=normalized_session_id,
            )
            if existing is not None:
                raise AlreadyExistsError(
                    f"Session with id {normalized_session_id} already exists."
                )

            state_deltas = _session_util.extract_state_delta(state or {})
            if state_deltas["app"]:
                await self._merge_state_hash(
                    key=self._app_state_key(app_name),
                    delta=state_deltas["app"],
                )
            if state_deltas["user"]:
                await self._merge_state_hash(
                    key=self._user_state_key(app_name, user_id),
                    delta=state_deltas["user"],
                )

            session = Session(
                app_name=app_name,
                user_id=user_id,
                id=normalized_session_id,
                state=state_deltas["session"],
                last_update_time=platform_time.get_time(),
            )
            await self._store_storage_session(session)
            return await self._build_merged_session(session)

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        storage_session = await self._load_storage_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if storage_session is None:
            return None

        await self._touch_session_ttl(app_name, user_id, session_id)
        copied_session = storage_session.model_copy(deep=True)
        self._apply_session_filters(copied_session, config)
        return await self._build_merged_session(copied_session)

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str | None = None,
    ) -> ListSessionsResponse:
        pattern = self._session_pattern(app_name=app_name, user_id=user_id)
        sessions: list[Session] = []
        async for session_key in self._redis.scan_iter(match=pattern):
            payload = await self._redis.get(session_key)
            if payload is None:
                continue

            storage_session = Session.model_validate_json(payload)
            storage_session.events = []
            sessions.append(await self._build_merged_session(storage_session))
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        async with self._session_lock(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        ):
            await self._redis.delete(self._session_key(app_name, user_id, session_id))

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event

        app_name = session.app_name
        user_id = session.user_id
        session_id = session.id

        await super().append_event(session=session, event=event)
        session.last_update_time = event.timestamp

        async with self._session_lock(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        ):
            storage_session = await self._load_storage_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if storage_session is None:
                logger.warning(
                    "Failed to append event to missing Redis session %s",
                    session_id,
                )
                return event

            storage_session.events.append(event)
            storage_session.last_update_time = event.timestamp

            if event.actions.state_delta:
                state_deltas = _session_util.extract_state_delta(
                    event.actions.state_delta
                )
                if state_deltas["app"]:
                    await self._merge_state_hash(
                        key=self._app_state_key(app_name),
                        delta=state_deltas["app"],
                    )
                if state_deltas["user"]:
                    await self._merge_state_hash(
                        key=self._user_state_key(app_name, user_id),
                        delta=state_deltas["user"],
                    )
                if state_deltas["session"]:
                    storage_session.state.update(state_deltas["session"])

            await self._store_storage_session(storage_session)
        return event

    async def flush(self) -> None:
        return None

    @asynccontextmanager
    async def _session_lock(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> AsyncIterator[None]:
        lock = self._redis.lock(
            self._session_lock_key(app_name, user_id, session_id),
            timeout=self._lock_timeout_seconds,
            blocking_timeout=self._lock_blocking_timeout_seconds,
            sleep=0.05,
        )
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError(
                f"Timed out acquiring Redis session lock for {app_name}/{user_id}/{session_id}"
            )
        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError:
                logger.warning(
                    "Redis session lock already released for %s/%s/%s",
                    app_name,
                    user_id,
                    session_id,
                )

    async def _load_storage_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        payload = await self._redis.get(
            self._session_key(app_name, user_id, session_id)
        )
        if payload is None:
            return None
        return Session.model_validate_json(payload)

    async def _store_storage_session(self, session: Session) -> None:
        await self._redis.set(
            self._session_key(session.app_name, session.user_id, session.id),
            session.model_dump_json(by_alias=True),
            ex=self._session_ttl_seconds,
        )

    async def _touch_session_ttl(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        await self._redis.expire(
            self._session_key(app_name, user_id, session_id),
            self._session_ttl_seconds,
        )

    async def _build_merged_session(self, session: Session) -> Session:
        copied_session = session.model_copy(deep=True)
        app_state = await self._read_state_hash(self._app_state_key(session.app_name))
        for key, value in app_state.items():
            copied_session.state[f"{State.APP_PREFIX}{key}"] = value

        user_state = await self._read_state_hash(
            self._user_state_key(session.app_name, session.user_id)
        )
        for key, value in user_state.items():
            copied_session.state[f"{State.USER_PREFIX}{key}"] = value
        return copied_session

    async def _read_state_hash(self, key: str) -> dict[str, Any]:
        payload = await self._redis.hgetall(key)
        return {field: json.loads(value) for field, value in payload.items()}

    async def _merge_state_hash(self, key: str, delta: dict[str, Any]) -> None:
        if not delta:
            return
        await self._redis.hset(
            key,
            mapping={field: json.dumps(value) for field, value in delta.items()},
        )

    def _apply_session_filters(
        self,
        session: Session,
        config: GetSessionConfig | None,
    ) -> None:
        if config is None:
            return
        if config.num_recent_events is not None:
            if config.num_recent_events == 0:
                session.events = []
            else:
                session.events = session.events[-config.num_recent_events :]
        if config.after_timestamp is not None:
            index = len(session.events) - 1
            while index >= 0:
                if session.events[index].timestamp < config.after_timestamp:
                    break
                index -= 1
            if index >= 0:
                session.events = session.events[index + 1 :]

    def _session_pattern(self, *, app_name: str, user_id: str | None) -> str:
        app_token = self._token(app_name)
        if user_id is None:
            return f"{self._namespace}:session:{app_token}:*"
        return f"{self._namespace}:session:{app_token}:{self._token(user_id)}:*"

    def _session_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return (
            f"{self._namespace}:session:{self._token(app_name)}:"
            f"{self._token(user_id)}:{self._token(session_id)}"
        )

    def _session_lock_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return (
            f"{self._namespace}:lock:session:{self._token(app_name)}:"
            f"{self._token(user_id)}:{self._token(session_id)}"
        )

    def _user_state_key(self, app_name: str, user_id: str) -> str:
        return (
            f"{self._namespace}:user_state:{self._token(app_name)}:"
            f"{self._token(user_id)}"
        )

    def _app_state_key(self, app_name: str) -> str:
        return f"{self._namespace}:app_state:{self._token(app_name)}"

    def _normalize_session_id(self, session_id: str | None) -> str:
        if session_id and session_id.strip():
            return session_id.strip()
        return platform_uuid.new_uuid()

    def _token(self, value: str) -> str:
        return quote(value, safe="")
