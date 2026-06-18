import pytest
from infrastructure.channels.telegram_fsm import (
    TelegramConversationFSM,
    FSMStateStore,
    FSMState,
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
