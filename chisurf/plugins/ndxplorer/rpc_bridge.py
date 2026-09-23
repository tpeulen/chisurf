"""Build an in-process ChiSurf RPC client for ndX (PRD-56).

In the GUI, ndX runs in-process with ChiSurf, so it does not need a socket: it can
be handed an :class:`~chisurf.core.plugin.client.InProcessClient` wired to a
``ServiceDispatcher`` that has ChiSurf's services registered. That client satisfies
ndX's chisurf-free ``RpcClient`` contract (``call(method, params)``), so
``NDXplorer(chisurf_rpc=...)`` gains ChiSurf's RPC methods with no server process and no
configuration.

The dispatcher is built with the **core manifest** (``fit.*``, ``dataset.*``,
``pda.from_bursts``, …) *plus* the plugin services below, so ndX gets both the
phasor / FRET-line overlays and the analysis **bridges** — routing a gated burst
selection into PDA (``pda.from_bursts``), burst correlation (``burst_fcs.*``) or
lifetime MLE (``burst_mle.*``), via
:class:`ndxplorer.analysis.burst_bridge.BurstAnalysisBridge`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Plugin service entrypoints to register on the in-process dispatcher (on top of
#: the core manifest). These add the phasor / FRET-line overlays and the burst
#: analysis targets the bridges dispatch to.
_SERVICE_REGISTRARS = (
    "chisurf.plugins.microscopy.img_pixel_phasor.backend.services:register_services",
    "chisurf.plugins.fret_line.backend.services:register_services",
    "chisurf.plugins.burst.burst_fcs_correlator.backend.services:register_services",
    "chisurf.plugins.burst.burst_mle_analysis.backend.services:register_services",
)


def _load(path: str):
    module_name, attr = path.split(":", 1)
    import importlib

    return getattr(importlib.import_module(module_name), attr)


def make_inprocess_chisurf_client() -> Any | None:
    """Return an ``InProcessClient`` exposing the phasor + FRET-line RPC methods.

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


def make_ndxplorer(**kwargs: Any):
    """Construct an ``NDXplorer`` with the in-process ChiSurf client injected.

    The entry point every in-GUI launcher should use so the window always
    gets the phasor / FRET-line features (the "ChiSurf Phasor" toolbar). ChiSurf's
    own ndX window (menu and ribbon) is
    :func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`, which adds
    the Accurate FRET and MMFDB toolbars and the Global View binding. Any
    caller-supplied ``chisurf_rpc`` is respected; otherwise an in-process client is
    built and injected. Falls back to a plain ``NDXplorer`` if the client cannot be
    built, so ndX still opens when the RPC stack is unavailable.
    """
    import ndxplorer

    if kwargs.get("chisurf_rpc") is None:
        client = make_inprocess_chisurf_client()
        if client is not None:
            kwargs["chisurf_rpc"] = client
    return _measurement_aware(ndxplorer.NDXplorer)(**kwargs)


def _measurement_aware(base):
    """Subclass *base* so that opening a measurement restores its calibration.

    A calibration belongs to the measurement it was determined on, and the
    Accurate FRET step already writes it into the container. Nothing read it
    back, so opening a container gave a window still holding the *previous*
    measurement's constants — numbers that look determined, belong to another
    file, and correct every burst by the wrong amounts. There is no signal for
    "a load finished", but there is one place every load ends: the assignment to
    ``data_source``. Hooking the property is therefore the whole of it.

    Built lazily and cached so the class is created once, after ``ndxplorer``
    has been imported.
    """
    cached = getattr(_measurement_aware, "_cache", None)
    if cached is not None and cached.__bases__[0] is base:
        return cached

    class MeasurementAwareNDXplorer(base):
        """An ndX window that adopts the calibration stored with its data."""

        @property
        def data_source(self):
            """The loaded data (unchanged; only the setter does more)."""
            return base.data_source.fget(self)

        @data_source.setter
        def data_source(self, value):
            base.data_source.fset(self, value)
            self._restore_stored_calibration()

        def _restore_stored_calibration(self, _attempt: int = 0) -> None:
            """Adopt what the freshly loaded measurement carries.

            Deferred while the window has no ``parameter_control``. That is not
            an optimisation: the values have to reach the parameter *table*, and
            ndX's recompute throttle resets ``constants`` from that table on the
            next parameter event -- so a restore applied before the table exists
            is correct only until the event loop turns. The table is built in
            ``_deferred_init``, which runs on first show, and a measurement can
            easily be handed over before that.

            Never fatal: a window that cannot restore is a window with the
            constants it already had, which is where it was before this existed.
            """
            from qtpy import QtCore

            try:
                if getattr(self, "parameter_control", None) is None and _attempt < 50:
                    QtCore.QTimer.singleShot(
                        20, lambda: self._restore_stored_calibration(_attempt + 1)
                    )
                    return
                from chisurf.plugins.ndxplorer.calibration_bridge import (
                    restore_calibration_from_container,
                )

                restore_calibration_from_container(self)
            except Exception:
                logging.debug("could not restore a stored calibration", exc_info=True)

    _measurement_aware._cache = MeasurementAwareNDXplorer
    return MeasurementAwareNDXplorer
