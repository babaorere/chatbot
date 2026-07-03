import pytest
from unittest.mock import AsyncMock
from infrastructure.channels.telegram_fsm import (
    TelegramConversationFSM,
    FSMStateStore,
    FSMState,
    RedisFSMStateStore,
)


@pytest.mark.asyncio
async def test_telegram_fsm_transitions():
    store = FSMStateStore()
    fsm = TelegramConversationFSM("user123", store)

    # Check default state
    state = await fsm.get_state()
    assert state == FSMState.IDLE

    # Transition: consultar stock
    new_state, context = await fsm.transition("menu:stock")
    assert new_state == FSMState.AWAITING_PRODUCT_NAME
    assert context["intent"] == "consultar_stock"

    # Ensure it's saved
    state = await fsm.get_state()
    assert state == FSMState.AWAITING_PRODUCT_NAME

    # Test reset
    await fsm.reset()
    state = await fsm.get_state()
    assert state == FSMState.IDLE


@pytest.mark.asyncio
async def test_telegram_fsm_menu_tracking_and_versioning():
    store = FSMStateStore()
    fsm = TelegramConversationFSM("user999", store)

    # El ID de menú activo inicial debe ser None
    active_menu = await fsm.get_active_menu_id()
    assert active_menu is None

    # Establecer y recuperar el ID de menú activo
    await fsm.set_active_menu_id(12345)
    active_menu = await fsm.get_active_menu_id()
    assert active_menu == 12345

    # La versión inicial del FSM debe ser 1
    version = await fsm.get_fsm_version()
    assert version == 1

    # Incrementar versión
    new_version = await fsm.increment_fsm_version()
    assert new_version == 2
    assert await fsm.get_fsm_version() == 2

    # Verificar que el ID del menú y la versión se guarden en el mismo estado sin solaparse
    state = await fsm.get_state()
    assert state == FSMState.IDLE  # No debe alterar el estado

    # Transición debe incrementar versión
    new_state, context = await fsm.transition("menu:stock")
    # Versión era 2, transición incrementa a 3
    assert await fsm.get_fsm_version() == 3
    # El ID de menú activo anterior debe persistir en el contexto
    assert await fsm.get_active_menu_id() == 12345


@pytest.mark.asyncio
async def test_telegram_fsm_persist_menu_metadata_single_write_shape():
    store = FSMStateStore()
    fsm = TelegramConversationFSM("user-menu", store)

    await fsm.persist_menu_metadata(
        version=4,
        options=["menu:categorias", "menu:promociones", "menu:mas_vendidos"],
        active_menu_id=777,
    )

    state, context = await fsm.get_state_and_context()
    assert state == FSMState.IDLE
    assert context["_fsm_version"] == 4
    assert context["_menu_options"] == [
        "menu:categorias",
        "menu:promociones",
        "menu:mas_vendidos",
    ]
    assert context["_active_menu_id"] == 777


@pytest.mark.asyncio
async def test_telegram_fsm_invalid_state_raises() -> None:
    store = FSMStateStore()
    store._store["user-bad"] = {"state": "bogus", "context": {}}
    fsm = TelegramConversationFSM("user-bad", store)

    with pytest.raises(ValueError, match="Invalid FSM state stored"):
        await fsm.get_state()


@pytest.mark.asyncio
async def test_redis_fsm_store_invalid_payload_raises() -> None:
    redis_mock = AsyncMock()
    redis_mock.get.return_value = "{invalid-json"
    store = RedisFSMStateStore(redis_client=redis_mock, namespace="ns")

    with pytest.raises(ValueError, match="Invalid FSM payload stored in Redis"):
        await store.get("user-1")


@pytest.mark.asyncio
async def test_telegram_fsm_invalid_context_type_raises_on_transition() -> None:
    store = FSMStateStore()
    store._store["user-bad-context"] = {
        "state": FSMState.IDLE.value,
        "context": "not-a-dict",
    }
    fsm = TelegramConversationFSM("user-bad-context", store)

    with pytest.raises(ValueError, match="Invalid FSM context stored"):
        await fsm.transition("menu:stock")


@pytest.mark.asyncio
async def test_telegram_fsm_invalid_context_type_raises_on_persist_menu_metadata() -> (
    None
):
    store = FSMStateStore()
    store._store["user-bad-context"] = {
        "state": FSMState.IDLE.value,
        "context": "not-a-dict",
    }
    fsm = TelegramConversationFSM("user-bad-context", store)

    with pytest.raises(ValueError, match="Invalid FSM context stored"):
        await fsm.persist_menu_metadata(
            version=2,
            options=["menu:stock"],
            active_menu_id=123,
        )
