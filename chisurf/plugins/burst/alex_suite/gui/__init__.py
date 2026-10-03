"""ALEX Suite GUI: the workflow shell and the two steps it adds itself."""


def __getattr__(name: str):
    if name == "ALEX_PANELS":
        from .tool import ALEX_PANELS

        return ALEX_PANELS
    if name == "AlexSuiteTool":
        from .tool import AlexSuiteTool

        return AlexSuiteTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ALEX_PANELS", "AlexSuiteTool"]
