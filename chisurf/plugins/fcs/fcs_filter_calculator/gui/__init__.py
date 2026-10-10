"""The emtk filter calculator window (``app.create_app``), its model and the RPC client."""

__all__ = ["FilterCalcClient"]


def __getattr__(name):
    if name == "FilterCalcClient":
        from .client import FilterCalcClient

        return FilterCalcClient
    raise AttributeError(name)
