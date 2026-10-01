"""Lazy Qt export for the Games hub."""

__all__ = ["GamesWidget"]


def __getattr__(name):
    if name == "GamesWidget":
        from .tool import GamesWidget
        return GamesWidget
    raise AttributeError(name)
