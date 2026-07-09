from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)


class TelegramWebhookUseCase:
    def __init__(
        self,
        *,
        telegram_bot_token: str,
        get_redis_client: Callable[[], Any],
        answer_callback_query: Callable[..., Awaitable[Any]],
        process_update_background: Callable[..., Awaitable[None]],
        log_timing: Callable[..., None],
        local_locks: set[str],
    ) -> None:
        self._telegram_bot_token = telegram_bot_token
        self._get_redis_client = get_redis_client
        self._answer_callback_query = answer_callback_query
        self._process_update_background = process_update_background
        self._log_timing = log_timing
        self._local_locks = local_locks

    async def execute(
        self,
        *,
        token: str,
        request: Request,
        process_message_uc: Any,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        webhook_started_at = time.perf_counter()
        self._ensure_authorized_token(token)
        payload = await self._parse_payload(request)

        message_obj = payload.get("message") or payload.get("edited_message")
        callback_query = payload.get("callback_query")
        if not message_obj and not callback_query:
            return {"status": "ok", "detail": "no message or callback in payload"}

        chat_id, user_id, callback_query_id, msg_obj = self._extract_update_context(
            message_obj=message_obj,
            callback_query=callback_query,
        )
        if not user_id or not chat_id:
            return {"status": "ok", "detail": "invalid user_id or chat_id"}

        update_kind = "callback" if callback_query else "message"
        raw_update_id = payload.get("update_id")
        trace_id = (
            f"tg:{user_id}:{raw_update_id}"
            if raw_update_id is not None
            else f"tg:{user_id}:{int(time.time() * 1000)}"
        )
        self._log_timing(
            trace_id=trace_id,
            stage="webhook_parsed",
            started_at=webhook_started_at,
            user_id=user_id,
            extra=f"kind={update_kind}",
        )

        lock_key = f"lock:telegram:user:{user_id}"
        redis_client = self._get_redis_client()
        lock_acquired = await self._acquire_lock(
            redis_client=redis_client,
            lock_key=lock_key,
            user_id=user_id,
            callback_query=callback_query,
            callback_query_id=callback_query_id,
            background_tasks=background_tasks,
            token=token,
            trace_id=trace_id,
            webhook_started_at=webhook_started_at,
            update_kind=update_kind,
        )

        if lock_acquired is None:
            return {"status": "ok", "detail": "duplicate request blocked"}

        redis_client, lock_acquired = lock_acquired
        schedule_started_at = time.perf_counter()
        background_tasks.add_task(
            self._process_update_background,
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            message_obj=message_obj,
            callback_query=callback_query,
            callback_query_id=callback_query_id,
            msg_obj=msg_obj if callback_query else None,
            process_message_uc=process_message_uc,
            lock_key=lock_key,
            lock_acquired=lock_acquired,
            redis_client=redis_client,
            trace_id=trace_id,
            webhook_started_at=webhook_started_at,
        )
        self._log_timing(
            trace_id=trace_id,
            stage="background_task_scheduled",
            started_at=schedule_started_at,
            user_id=user_id,
            extra=f"kind={update_kind}",
        )
        self._log_timing(
            trace_id=trace_id,
            stage="webhook_scheduled",
            started_at=webhook_started_at,
            user_id=user_id,
            extra=f"lock_acquired={lock_acquired} kind={update_kind}",
        )
        self._log_timing(
            trace_id=trace_id,
            stage="webhook_response_ready",
            started_at=webhook_started_at,
            user_id=user_id,
            extra=f"detail=scheduled kind={update_kind}",
        )
        return {"status": "ok", "detail": "scheduled"}

    def _ensure_authorized_token(self, token: str) -> None:
        if token != self._telegram_bot_token:
            logger.warning("Unauthorized webhook request with token: %s", token)
            raise HTTPException(403, "Forbidden: Invalid Telegram bot token")

    async def _parse_payload(self, request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception as exc:
            logger.error("Failed to parse Telegram payload: %s", exc)
            raise HTTPException(400, "Invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise HTTPException(400, "Invalid JSON payload")
        return payload

    def _extract_update_context(
        self,
        *,
        message_obj: Any,
        callback_query: Any,
    ) -> tuple[Any, str | None, Any, Any]:
        chat_id = None
        user_id = None
        callback_query_id = None
        msg_obj = None

        if callback_query:
            from_obj = callback_query.get("from")
            msg_obj = callback_query.get("message")
            chat_id = msg_obj.get("chat", {}).get("id") if msg_obj else None
            user_id = str(from_obj.get("id")) if from_obj else str(chat_id)
            callback_query_id = callback_query.get("id")
        else:
            chat_obj = message_obj.get("chat")
            from_obj = message_obj.get("from")
            chat_id = chat_obj.get("id") if chat_obj else None
            user_id = str(from_obj.get("id") if from_obj else chat_id)

        return chat_id, user_id, callback_query_id, msg_obj

    async def _acquire_lock(
        self,
        *,
        redis_client: Any,
        lock_key: str,
        user_id: str,
        callback_query: Any,
        callback_query_id: Any,
        background_tasks: BackgroundTasks,
        token: str,
        trace_id: str,
        webhook_started_at: float,
        update_kind: str,
    ) -> tuple[Any, bool] | None:
        if redis_client is not None:
            lock_started_at = time.perf_counter()
            try:
                acquired = await redis_client.set(lock_key, "locked", ex=20, nx=True)
                self._log_timing(
                    trace_id=trace_id,
                    stage="redis_lock_checked",
                    started_at=lock_started_at,
                    user_id=user_id,
                    extra=f"acquired={bool(acquired)}",
                )
                if not acquired:
                    await self._handle_duplicate_request(
                        callback_query=callback_query,
                        callback_query_id=callback_query_id,
                        background_tasks=background_tasks,
                        token=token,
                        trace_id=trace_id,
                        webhook_started_at=webhook_started_at,
                        update_kind=update_kind,
                        user_id=user_id,
                    )
                    return None
                return redis_client, True
            except Exception:
                logger.exception(
                    "Redis concurrency lock error; falling back to local lock [user=%s]",
                    user_id,
                )
                self._log_timing(
                    trace_id=trace_id,
                    stage="redis_lock_fallback_to_local",
                    started_at=lock_started_at,
                    user_id=user_id,
                    extra="reason=redis_lock_error",
                )

        lock_started_at = time.perf_counter()
        if user_id in self._local_locks:
            await self._handle_duplicate_request(
                callback_query=callback_query,
                callback_query_id=callback_query_id,
                background_tasks=background_tasks,
                token=token,
                trace_id=trace_id,
                webhook_started_at=webhook_started_at,
                update_kind=update_kind,
                user_id=user_id,
            )
            return None

        self._local_locks.add(user_id)
        self._log_timing(
            trace_id=trace_id,
            stage="local_lock_checked",
            started_at=lock_started_at,
            user_id=user_id,
            extra="acquired=True",
        )
        return None, True

    async def _handle_duplicate_request(
        self,
        *,
        callback_query: Any,
        callback_query_id: Any,
        background_tasks: BackgroundTasks,
        token: str,
        trace_id: str,
        webhook_started_at: float,
        update_kind: str,
        user_id: str,
    ) -> None:
        warning_prefix = "Concurrency" if callback_query is not None else "Local concurrency"
        logger.warning(
            "%s warning: duplicate request from user %s blocked",
            warning_prefix,
            user_id,
        )
        if callback_query:
            callback_query_id = callback_query.get("id")
        if callback_query_id:
            background_tasks.add_task(
                self._answer_callback_query,
                bot_token=token,
                callback_query_id=callback_query_id,
                text="Procesando tu solicitud anterior, por favor espera...",
                trace_id=trace_id,
            )
            self._log_timing(
                trace_id=trace_id,
                stage="duplicate_callback_deferred",
                started_at=webhook_started_at,
                user_id=user_id,
            )
        self._log_timing(
            trace_id=trace_id,
            stage="webhook_response_ready",
            started_at=webhook_started_at,
            user_id=user_id,
            extra=f"detail=duplicate_request_blocked kind={update_kind}",
        )
