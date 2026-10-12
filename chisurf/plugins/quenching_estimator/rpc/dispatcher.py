"""A minimal RPC dispatcher and in-process client.

QuEst exposes its capabilities as named methods so that every surface — the
CLI, the web backend, the desktop GUI, and a host application that loads QuEst
as a plugin — calls the *same* operation under the *same* name with the same
result shape.

This module is deliberately small: it exists so QuEst works standalone. When a
host application provides its own dispatcher, pass that one to
:func:`quest.rpc.services.register_services` instead — the registration only
needs a ``register(name, handler)`` method, so the two interoperate without
QuEst depending on the host.

The envelope every handler returns::

    {"ok": True,  "result": <plain serialisable data>}
    {"ok": False, "error": "<message>"}

Callers distinguish success from failure by ``ok``, never by sniffing for the
presence of a field.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

__all__ = ["ServiceDispatcher", "InProcessClient", "RemoteError", "ok", "fail"]

Handler = Callable[[Dict[str, Any]], Dict[str, Any]]


class RemoteError(RuntimeError):
    """Raised by a client when a call fails.

    Carries the envelope's ``error_code`` and ``exception_type`` so a caller can
    branch on the condition rather than on the wording of a message. The field
    names match ChiSurf's own ``RemoteError``.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        exception_type: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.exception_type = exception_type
        self.details = details


def ok(result: Any) -> dict[str, Any]:
    """Wrap *result* in a success envelope."""

    return {"ok": True, "result": result}


def fail(error: str, error_code: str = "operation_failed") -> dict[str, Any]:
    """Wrap *error* in a failure envelope.

    Thin wrapper over :func:`quest.rpc.contract.service_error`, kept because
    handlers read better with a short name. Use the contract directly when you
    want to attach an exception type or details.
    """

    from chisurf.plugins.quenching_estimator.rpc.contract import service_error

    return service_error(error, error_code)


class ServiceDispatcher:
    """Maps method names to handlers.

    A handler takes a single params mapping and returns an envelope. Handlers
    are not expected to raise: :meth:`dispatch` converts an escaped exception
    into a failure envelope so a caller never has to handle both styles.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        """Register *handler* under *name*.

        Raises
        ------
        ValueError
            If *name* is already registered. One operation, one name: a silent
            overwrite would make which implementation runs depend on import
            order.
        """

        if name in self._handlers:
            raise ValueError(f"RPC method already registered: {name}")
        self._handlers[name] = handler

    @property
    def methods(self) -> list[str]:
        """The registered method names, sorted."""

        return sorted(self._handlers)

    def dispatch(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Call *method* with *params* and return its envelope."""

        from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for, service_error

        handler = self._handlers.get(method)
        if handler is None:
            return service_error(f"Unknown method: {method}", "unknown_method")
        try:
            return handler(params or {})
        except Exception as exc:  # handlers should not raise; be safe anyway
            # The exception *type* is preserved rather than flattened into the
            # message. A host that can only string-match breaks the first time
            # a message is improved.
            return service_error(
                f"{type(exc).__name__}: {exc}",
                error_code_for(exc),
                type(exc).__name__,
            )


class InProcessClient:
    """Client that calls a dispatcher directly, with no transport in between.

    Presentation code holds a client, not a dispatcher, so that swapping in a
    remote transport later changes nothing at the call sites.
    """

    def __init__(self, dispatcher: ServiceDispatcher) -> None:
        self._dispatcher = dispatcher

    def call(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Execute *method* and return the response envelope."""

        return self._dispatcher.dispatch(method, params)

    def result(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute *method* and return its result, raising on failure.

        Raises
        ------
        RemoteError
            If the call returned a failure envelope.
        """

        response = self.call(method, params)
        if not response.get("ok"):
            raise RemoteError(
                response.get("error", "unknown error"),
                response.get("error_code"),
                response.get("exception_type"),
                response.get("details"),
            )
        return response.get("result")
