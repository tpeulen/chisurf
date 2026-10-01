"""F-test native factory with lazy legacy Qt compatibility exports."""

__all__ = ["FTestTool", "FTestWidget"]


def __getattr__(name: str):
    if name in __all__:
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
