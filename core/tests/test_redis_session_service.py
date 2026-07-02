from __future__ import annotations

import asyncio
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message="BaseAgentConfig is deprecated and will be removed in future versions\\.",
    )
    from google.adk.events import Event
    from google.adk.sessions.base_session_service import GetSessionConfig
    from google.adk.sessions import InMemorySessionService

from config.settings import Settings
from services.redis_session_service import RedisSessionService
from services.session_service_factory import create_session_service


class FakeRedisLock:
    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock
        self._acquired = False

    async def acquire(
        self,
        blocking: bool | None = None,
        blocking_timeout: int | float | None = None,
        token: str | bytes | None = None,
    ) -> bool:
        del blocking, blocking_timeout, token
        await self._lock.acquire()
        self._acquired = True
        return True

    async def release(self) -> None:
        if self._acquired:
            self._lock.release()
            self._acquired = False


class FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, name: str) -> str | None:
        return self._strings.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self._strings[name] = value
        if ex is not None:
            self.expirations[name] = ex
        return True

    async def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            if name in self._strings:
                del self._strings[name]
                deleted += 1
            self.expirations.pop(name, None)
        return deleted

    async def expire(self, name: str, time: int) -> bool:
        if name not in self._strings:
            return False
        self.expirations[name] = time
        return True

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self._hashes.get(name, {}))

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
        items: list[tuple[str, str]] | None = None,
    ) -> int:
        bucket = self._hashes.setdefault(name, {})
        written = 0
        if mapping:
            bucket.update(mapping)
            written += len(mapping)
        if items:
            for item_key, item_value in items:
                bucket[item_key] = item_value
                written += 1
        if key is not None and value is not None:
            bucket[key] = value
            written += 1
        return written

    def lock(
        self,
        name: str,
        timeout: float | None = None,
        sleep: float = 0.1,
        blocking: bool = True,
        blocking_timeout: int | float | None = None,
        thread_local: bool = True,
        raise_on_release_error: bool = True,
    ) -> FakeRedisLock:
        del timeout, sleep, blocking, blocking_timeout, thread_local
        del raise_on_release_error
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return FakeRedisLock(self._locks[name])

    async def scan_iter(self, match: str | None = None):
        prefix = None if match is None else match.rstrip("*")
        for key in sorted(self._strings.keys()):
            if prefix is None or key.startswith(prefix):
                yield key


def create_redis_session_service(fake_redis: FakeRedis) -> RedisSessionService:
    return RedisSessionService(
        fake_redis,
        namespace="chatbot:test:v1",
        session_ttl_seconds=3600,
        lock_timeout_seconds=5.0,
        lock_blocking_timeout_seconds=1.0,
    )


async def test_redis_session_service_create_and_merge_state() -> None:
    fake_redis = FakeRedis()
    service = create_redis_session_service(fake_redis)

    session = await service.create_session(
        app_name="chatbot",
        user_id="cliente-1",
        session_id="session-1",
        state={
            "app:currency": "CLP",
            "user:preferred_store": "el_buen_trago",
            "draft_order": {"items": 1},
        },
    )

    assert session.id == "session-1"
    assert session.state["app:currency"] == "CLP"
    assert session.state["user:preferred_store"] == "el_buen_trago"
    assert session.state["draft_order"] == {"items": 1}


async def test_redis_session_service_append_event_persists_session_and_state() -> None:
    fake_redis = FakeRedis()
    service = create_redis_session_service(fake_redis)

    session = await service.create_session(
        app_name="chatbot",
        user_id="cliente-1",
        session_id="session-append",
    )
    event = Event(
        author="assistant",
        invocation_id="invoke-1",
        state={
            "app:last_channel": "telegram",
            "user:last_product": "pisco",
            "cart_total": 12980,
        },
    )

    await service.append_event(session, event)
    stored = await service.get_session(
        app_name="chatbot",
        user_id="cliente-1",
        session_id="session-append",
    )

    assert stored is not None
    assert len(stored.events) == 1
    assert stored.events[0].author == "assistant"
    assert stored.state["app:last_channel"] == "telegram"
    assert stored.state["user:last_product"] == "pisco"
    assert stored.state["cart_total"] == 12980


async def test_redis_session_service_filters_recent_events() -> None:
    fake_redis = FakeRedis()
    service = create_redis_session_service(fake_redis)

    session = await service.create_session(
        app_name="chatbot",
        user_id="cliente-2",
        session_id="session-filter",
    )
    first = Event(author="user", invocation_id="invoke-1")
    second = Event(author="assistant", invocation_id="invoke-2")

    await service.append_event(session, first)
    await service.append_event(session, second)

    filtered = await service.get_session(
        app_name="chatbot",
        user_id="cliente-2",
        session_id="session-filter",
        config=GetSessionConfig(num_recent_events=1),
    )

    assert filtered is not None
    assert len(filtered.events) == 1
    assert filtered.events[0].author == "assistant"


async def test_redis_session_service_list_sessions_omits_events() -> None:
    fake_redis = FakeRedis()
    service = create_redis_session_service(fake_redis)

    session = await service.create_session(
        app_name="chatbot",
        user_id="cliente-3",
        session_id="session-list",
        state={"user:favorite": "vino"},
    )
    await service.append_event(
        session,
        Event(author="assistant", invocation_id="invoke-1"),
    )

    response = await service.list_sessions(
        app_name="chatbot",
        user_id="cliente-3",
    )

    assert len(response.sessions) == 1
    assert response.sessions[0].events == []
    assert response.sessions[0].state["user:favorite"] == "vino"


async def test_redis_session_service_delete_session_removes_it() -> None:
    fake_redis = FakeRedis()
    service = create_redis_session_service(fake_redis)

    await service.create_session(
        app_name="chatbot",
        user_id="cliente-4",
        session_id="session-delete",
    )
    await service.delete_session(
        app_name="chatbot",
        user_id="cliente-4",
        session_id="session-delete",
    )

    deleted = await service.get_session(
        app_name="chatbot",
        user_id="cliente-4",
        session_id="session-delete",
    )
    assert deleted is None


def test_session_service_factory_uses_inmemory_when_requested() -> None:
    service = create_session_service(
        config=Settings(
            session_backend="memory",
            redis_url="redis://localhost:6379/0",
        )
    )
    assert isinstance(service, InMemorySessionService)
