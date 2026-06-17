from services.agent_factory import AgentFactory, AgentContext


def test_factory_creates_unique_instances():
    ctx1 = AgentContext(user_id=1, session_id="s1", platform="telegram")
    ctx2 = AgentContext(user_id=2, session_id="s2", platform="whatsapp")

    agent1 = AgentFactory.get_or_create(ctx1)
    agent2 = AgentFactory.get_or_create(ctx2)

    assert agent1["user_id"] == 1
    assert agent2["user_id"] == 2
    assert agent1 is not agent2


def test_factory_returns_cached_instance():
    ctx = AgentContext(user_id=99, session_id="cached", platform="web")
    a1 = AgentFactory.get_or_create(ctx)
    a2 = AgentFactory.get_or_create(ctx)
    assert a1 is a2
