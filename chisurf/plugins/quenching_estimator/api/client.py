"""A client for host code that wants to call QuEst in-process.

Thin on purpose: `quest.api` is already the facade, and wrapping it again would
add a second place for a method name to be spelled.
"""

from __future__ import annotations

from typing import Any


class QuEstClient:
    """Call QuEst's RPC methods, locally or through a configured transport."""

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from quest.api import client

        return client().call(method, params)

    def result(self, method: str, params: dict[str, Any] | None = None) -> Any:
        from quest.api import client

        return client().result(method, params)

    def describe(self) -> dict[str, Any]:
        from .contract import contract_descriptor

        return contract_descriptor()
