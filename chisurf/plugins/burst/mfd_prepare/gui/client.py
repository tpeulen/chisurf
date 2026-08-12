"""RPC client for the MFD preparation plugin."""

from __future__ import annotations

from typing import Any


class MfdPrepareClient:
    """Thin RPC client wrapping ``mfd_prepare.*`` methods."""

    def __init__(self, rpc_client: Any = None):
        self._rpc = rpc_client

    def prepare(
        self,
        folder: str,
        *,
        with_photons: bool = True,
    ) -> dict[str, Any]:
        """Prepare a burst folder and return the result dict."""
        if self._rpc is None:
            raise RuntimeError("No RPC client connected")
        return self._rpc.call(
            "mfd_prepare.prepare",
            {"folder": folder, "with_photons": with_photons},
        )

    def describe(self) -> dict[str, Any]:
        """Return the plugin contract descriptor."""
        if self._rpc is None:
            raise RuntimeError("No RPC client connected")
        return self._rpc.call("mfd_prepare.describe", {})
