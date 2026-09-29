"""Build an in-process ChiSurf RPC client for ndX.

In the GUI, ndX runs in-process with ChiSurf, so it does not need a socket: it can
be handed an :class:`~chisurf.core.plugin.client.InProcessClient` wired to a
``ServiceDispatcher`` that has ChiSurf's services registered. That client satisfies
ndX's chisurf-free ``RpcClient`` contract (``call(method, params)``), so the app
(``app.chisurf_rpc``, set by :func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`)
gains ChiSurf's RPC methods with no server process and no configuration.

The dispatcher is built with the **core manifest** (``fit.*``, ``dataset.*``,
``pda.from_bursts``, …) *plus* the plugin services below, so ndX gets the
analysis **bridges** — routing a gated burst selection into PDA
(``pda.from_bursts``), burst correlation (``burst_fcs.*``) or lifetime MLE
(``burst_mle.*``), via :class:`ndxplorer.analysis.burst_bridge.BurstAnalysisBridge`.
Phasor geometry is not among them: ndX draws it itself, as overlay curves and
equations (the universal circle, lifetime points, FRET trajectories; τφ, τM).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Plugin service entrypoints to register on the in-process dispatcher (on top of
#: the core manifest): the burst analysis targets the bridges dispatch to.
_SERVICE_REGISTRARS = (
    "chisurf.plugins.burst.burst_fcs_correlator.backend.services:register_services",
    "chisurf.plugins.burst.burst_mle_analysis.backend.services:register_services",
)


def _load(path: str):
    module_name, attr = path.split(":", 1)
    import importlib

    return getattr(importlib.import_module(module_name), attr)


def make_inprocess_chisurf_client() -> Any | None:
    """Return an ``InProcessClient`` exposing ChiSurf's RPC methods to ndX.

    Best-effort: returns ``None`` if the RPC/plugin machinery is unavailable, so callers
    can degrade gracefully (ndX then runs without ChiSurf features).
    """
    try:
        from chisurf.core.plugin.client import InProcessClient
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.session import SessionState
    except Exception as exc:  # pragma: no cover - optional server stack
        logger.warning("ChiSurf RPC stack unavailable: %s", exc)
        return None

    dispatcher = ServiceDispatcher(SessionState())
    try:
        dispatcher._build_default_registry()  # core manifest: fit/dataset/pda/…
    except Exception:
        logger.warning("Could not build the core RPC registry", exc_info=True)
    for path in _SERVICE_REGISTRARS:
        try:
            _load(path)(dispatcher)
        except Exception:
            logger.warning("Could not register services %s", path, exc_info=True)
    return InProcessClient(dispatcher)
