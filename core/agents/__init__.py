from .constants import GADK_APP_NAME, GADK_INSTRUCTION, GADK_MODEL, GADK_MODEL_DISPLAY

__all__ = [
    "get_agent",
    "get_runner",
    "GADK_APP_NAME",
    "GADK_INSTRUCTION",
    "GADK_MODEL",
    "GADK_MODEL_DISPLAY",
]


def __getattr__(name: str):
    if name in {"get_agent", "get_runner"}:
        from .root_agent import get_agent, get_runner

        return {"get_agent": get_agent, "get_runner": get_runner}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
