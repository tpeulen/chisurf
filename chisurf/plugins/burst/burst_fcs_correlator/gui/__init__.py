"""Lazy GUI compatibility exports preserve toolkit-free app imports."""


def __getattr__(name):
    if name == "BurstFcsClient":
        from .client import BurstFcsClient

        return BurstFcsClient
    if name == "BurstFcsTool":
        from .tool import BurstFcsTool

        return BurstFcsTool
    raise AttributeError(name)
