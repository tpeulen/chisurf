"""Lazy GUI exports so the native factory does not import Qt."""

__all__ = ["NumberQuestWidget"]


def __getattr__(name):
    if name == "NumberQuestWidget":
        from .tool import NumberQuestWidget

        return NumberQuestWidget
    raise AttributeError(name)
