"""Native lifetime hub with lazy legacy window exports."""

__all__ = ["LifetimeAnalysisTool"]


def __getattr__(name):
    if name == "LifetimeAnalysisTool":
        from .tool import LifetimeAnalysisTool

        return LifetimeAnalysisTool
    raise AttributeError(name)
