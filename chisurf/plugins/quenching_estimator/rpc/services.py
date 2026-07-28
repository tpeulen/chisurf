"""Register QuEst's methods with ChiSurf's dispatcher.

**No handlers are written here.** `quest.rpc.services.register_services`
takes anything exposing ``register(name, handler)`` — it was built duck-typed
for exactly this — so the plugin hands it the host's dispatcher and QuEst's own
handlers serve both surfaces. Writing handlers here would create a second
implementation of every method, which is the failure `LAY-01` recorded when the
CLI, the web backend and the library each had their own `simulate_site`.

The import is inside the function: ChiSurf imports every plugin at startup, and
`quest.rpc.services` reaches `quest.core` and therefore IMP.
"""

from __future__ import annotations

from typing import Any


def register_services(dispatcher: Any) -> None:
    """Put QuEst's RPC methods on *dispatcher*.

    Parameters
    ----------
    dispatcher : object
        Anything with ``register(name, handler)`` — ChiSurf's
        ``ServiceDispatcher``, or QuEst's own.
    """

    from quest.rpc.services import register_services as _register

    _register(dispatcher)


def registered_method_names() -> tuple[str, ...]:
    """The names :func:`register_services` will add, without registering them."""

    from quest.rpc.services import METHODS

    return tuple(METHODS)
