"""Plugin-to-plugin hand-off: "open plugin X with payload P".

A tool that has something another tool works on (a trace for the HMM tool, a burst folder for
ndX) does not build that tool's window itself. It asks the *host* -- the window the tools live
in -- with :func:`hand_off`; the host opens the target as one of its docks and, once the
target's app exists, passes the payload to the target's receive hook.

The contract is declared by the **target**: its manifest lists the payload kinds it takes under
``"accepts"`` (:class:`~chisurf.core.plugin.manifest.HandoffSpec`): a ``name``, the
``receive`` hook ``module:function`` called as ``function(app, payload)``, and the payload keys
it ``required``. A request for a kind the target does not declare, or without a required key,
is refused before anything opens, so the requester can say why.

The host is installed with :func:`install_host` (the emtk shell installs itself; see
:meth:`chisurf.emtk.main_app.EmtkShellApp.hand_off`) and held weakly, so a closed shell is no
host. Without a host :func:`available` is ``False`` and a tool greys the buttons that would hand
off. This module imports no toolkit.
"""

from __future__ import annotations

import importlib
import logging
import weakref
from typing import Any, Callable, Protocol

from chisurf.core.plugin.manifest import HandoffSpec

_log = logging.getLogger(__name__)

__all__ = [
    "HandoffError",
    "HandoffHost",
    "accepted",
    "available",
    "check_payload",
    "deliver",
    "hand_off",
    "host",
    "install_host",
    "specs_of",
    "uninstall_host",
]


class HandoffError(LookupError):
    """A hand-off that cannot be made: no host, or the target does not take that payload."""


class HandoffHost(Protocol):
    """What a host offers: whether it can open a plugin, and the hand-off itself."""

    def accepts(self, plugin_id: str, kind: str) -> HandoffSpec | None:
        """The declaration of *kind* when the host can open *plugin_id* and it takes that kind."""
        ...

    def hand_off(
        self,
        plugin_id: str,
        kind: str,
        payload: dict,
        on_delivered: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Open *plugin_id*, deliver *payload* once its app exists, then call ``on_delivered(app)``."""
        ...


_HOST: weakref.ReferenceType | None = None


def install_host(new_host: HandoffHost | None) -> None:
    """Make *new_host* the host of this process (``None`` removes it); it is held weakly."""
    global _HOST
    _HOST = weakref.ref(new_host) if new_host is not None else None


def uninstall_host(owner: Any) -> None:
    """Remove the host if it is *owner* (a closing shell never removes another shell)."""
    global _HOST
    if _HOST is not None and _HOST() is owner:
        _HOST = None


def host() -> HandoffHost | None:
    """The installed host, or ``None`` (none installed, or it was closed)."""
    current = _HOST() if _HOST is not None else None
    if current is None or getattr(current, "_shell_closed", False):
        return None
    return current


def specs_of(manifest: dict | None) -> list[HandoffSpec]:
    """The payload kinds a raw manifest dict declares under ``"accepts"``."""
    return [
        HandoffSpec(
            name=str(item["name"]),
            receive=str(item["receive"]),
            summary=str(item.get("summary", "")),
            required=[str(k) for k in item.get("required", [])],
        )
        for item in (manifest or {}).get("accepts", [])
        if isinstance(item, dict) and item.get("name") and item.get("receive")
    ]


def accepted(plugin_id: str, kind: str, manifest: dict | None) -> HandoffSpec | None:
    """The declaration of *kind* in *plugin_id*'s raw *manifest*, or ``None`` when it takes no such payload."""
    return next((spec for spec in specs_of(manifest) if spec.name == kind), None)


def available(plugin_id: str, kind: str) -> bool:
    """Whether a hand-off of *kind* to *plugin_id* can be made now (a host is open and it is declared)."""
    current = host()
    return current is not None and current.accepts(plugin_id, kind) is not None


def check_payload(spec: HandoffSpec, payload: dict) -> None:
    """Raise :class:`HandoffError` when *payload* lacks a key *spec* requires."""
    missing = [key for key in spec.required if key not in payload]
    if missing:
        raise HandoffError(f"the {spec.name} payload needs {', '.join(missing)}")


def hand_off(
    plugin_id: str,
    kind: str,
    payload: dict,
    *,
    on_delivered: Callable[[Any], Any] | None = None,
) -> Any:
    """Ask the host to open *plugin_id* and give it *payload* of the declared *kind*.

    The target's app is built asynchronously, so what this returns is the host's record of
    the tool, not the app. A requester that has to act on the app itself (attach a hook to
    what it just opened) passes *on_delivered*: the host calls ``on_delivered(app)`` with the
    target's app right after its receive hook took the payload, on the draw thread -- at once
    when the tool is already open. It is not called when the receive hook fails.

    Returns
    -------
    object
        What the host returns for the opened tool (the shell: its hosted-plugin record).

    Raises
    ------
    HandoffError
        No host is open (raised here), or -- raised by the host -- it cannot open *plugin_id*,
        the target does not declare *kind*, or the payload lacks a required key. Nothing is
        opened then.
    """
    current = host()
    if current is None:
        raise HandoffError("no ChiSurf window is open to hand this to")
    if on_delivered is None:
        return current.hand_off(plugin_id, kind, dict(payload))
    return current.hand_off(plugin_id, kind, dict(payload), on_delivered=on_delivered)


def deliver(app: Any, spec: HandoffSpec, payload: dict) -> Any:
    """Call *spec*'s receive hook with the target's built *app* and *payload*."""
    module, _, name = spec.receive.partition(":")
    receive = getattr(importlib.import_module(module), name)
    _log.info("hand-off %s -> %s", spec.name, spec.receive)
    return receive(app, payload)
