"""RPC services of the ebFRET plugin: a session per window, run on the backend.

The GUI never holds the data. It opens a session here, sends it what the user
did (the menu entry, the button, the values a dialog returned) and asks for
what to draw. The empirical-Bayes loop runs in a backend thread, so the window
redraws while it runs -- what ebFRET did with ``drawnow`` between batches.

Every handler takes JSON-able parameters and returns the standard envelope
``{"ok": True, "result": ...}`` / ``{"ok": False, "error": ...}``.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any

import numpy as np

from ..api.models import EbfretSettings, FretTraceSet
from ..core import views
from ..core.analysis import EbfretAnalysis, analyse
from ..core.session import Session

METHOD_COMPUTE = "burst_ebfret.jobs.compute"
PREFIX = "burst_ebfret.session."

__all__ = ["register_services", "list_methods", "SessionStore", "STORE", "compute_handler"]


class SessionStore:
    """The open sessions and their analysis threads."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.errors: dict[str, str] = {}
        self._lock = threading.Lock()

    def open(self, seed: int | None = None) -> str:
        """Create a session and return its id."""
        sid = uuid.uuid4().hex
        with self._lock:
            self.sessions[sid] = Session(seed=seed)
        return sid

    def get(self, sid: str) -> Session:
        """The session *sid*; ``KeyError`` when it is not open."""
        return self.sessions[sid]

    def close(self, sid: str) -> None:
        """Stop a running analysis and forget the session."""
        session = self.sessions.get(sid)
        if session is not None:
            session.controls.run_analysis = False
            thread = self.threads.get(sid)
            if thread is not None:
                thread.join(timeout=5.0)
        with self._lock:
            self.sessions.pop(sid, None)
            self.threads.pop(sid, None)
            self.errors.pop(sid, None)

    def running(self, sid: str) -> bool:
        """Whether the analysis thread of *sid* is alive."""
        thread = self.threads.get(sid)
        return thread is not None and thread.is_alive()

    def run(self, sid: str) -> bool:
        """Start ``run_ebayes`` in a thread (the *Run* button).

        Returns
        -------
        bool
            ``False`` when it was already running or there is no data.
        """
        session = self.get(sid)
        if self.running(sid) or not session.series:
            return False
        session.controls.run_analysis = True
        self.errors.pop(sid, None)

        def work() -> None:
            try:
                for _event in session.run_ebayes():
                    pass
            except Exception:  # reported through status, the thread must not die silently
                self.errors[sid] = traceback.format_exc()
                session.controls.run_analysis = False
                session.touch()

        thread = threading.Thread(target=work, name=f"ebfret-{sid[:8]}", daemon=True)
        self.threads[sid] = thread
        thread.start()
        return True


#: The process-wide store the registered handlers use.
STORE = SessionStore()


def _ok(result: Any = None) -> dict:
    return {"ok": True, "result": result}


def _session_handler(fn):
    """Wrap a ``(session, params) -> result`` function as an RPC handler."""

    def handler(params: dict | None) -> dict:
        params = dict(params or {})
        try:
            session = STORE.get(params.pop("session_id"))
            return _ok(fn(session, params))
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return handler


def _status(session: Session, params: dict) -> dict:
    sid = next((k for k, v in STORE.sessions.items() if v is session), "")
    return {
        "revision": session.revision,
        "running": STORE.running(sid),
        "error": STORE.errors.get(sid, ""),
        "message": session.message,
        "log": session.log[-20:],
        "controls": session.controls_dict(),
        "n_series": len(session.series),
        "groups": session.groups(),
        "analyses": sorted(k for k, a in session.analysis.items() if a.prior is not None),
    }


def _load(session: Session, params: dict) -> dict:
    channels = params.get("smd_channels")
    message = session.load_data(
        list(params["files"]),
        int(params["ftype"]),
        append=bool(params.get("append", False)),
        smd_channels=channels,
    )
    return {"message": message, "n_series": len(session.series)}


def _smd_columns(session: Session, params: dict) -> list:
    from .. import io as ebio

    return [list(ebio.load_smd(path)["columns"]) for path in params["files"]]


def _set(session: Session, params: dict) -> dict:
    name, value = params["name"], params.get("value")
    with session.lock:
        if name == "series":
            session.set_series(value=value)
        elif name == "ensemble":
            session.set_ensemble(value=value)
        elif name == "min_states":
            session.set_min_states(value)
        elif name == "max_states":
            session.set_max_states(value)
        elif name == "crop_min":
            session.set_crop(crop_min=value)
        elif name == "crop_max":
            session.set_crop(crop_max=value)
        elif name == "exclude":
            session.set_exclude(bool(value))
        else:
            session.set_controls(**{name: value})
    return session.controls_dict()


def _view(session: Session, params: dict) -> dict:
    acquired = session.lock.acquire(timeout=float(params.get("timeout", 0.5)))
    if not acquired:
        return {"busy": True, "revision": session.revision}
    try:
        return dict(views.session_view(session), busy=False, revision=session.revision)
    finally:
        session.lock.release()


def _series_table(session: Session, params: dict) -> list:
    with session.lock:
        return [
            {
                "label": s.label,
                "file": s.file,
                "group": s.group,
                "length": s.length,
                "crop_min": s.crop_min,
                "crop_max": s.crop_max,
                "exclude": s.exclude,
            }
            for s in session.series
        ]


def register_services(dispatcher: Any) -> None:
    """Register every ebFRET handler with a ServiceDispatcher.

    Parameters
    ----------
    dispatcher : ServiceDispatcher
        Anything with ``register(name, handler)``.
    """
    dispatcher.register(METHOD_COMPUTE, lambda params: compute_handler(**(params or {})))

    def open_handler(params: dict | None) -> dict:
        return _ok({"session_id": STORE.open((params or {}).get("seed"))})

    def close_handler(params: dict | None) -> dict:
        STORE.close((params or {}).get("session_id", ""))
        return _ok(None)

    def run_handler(params: dict | None) -> dict:
        try:
            return _ok({"started": STORE.run((params or {})["session_id"])})
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def stop_handler(params: dict | None) -> dict:
        session = STORE.sessions.get((params or {}).get("session_id", ""))
        if session is not None:
            session.controls.run_analysis = False
            session.touch()
        return _ok(None)

    handlers = {
        "open": open_handler,
        "close": close_handler,
        "run": run_handler,
        "stop": stop_handler,
        "status": _session_handler(_status),
        "view": _session_handler(_view),
        "series_table": _session_handler(_series_table),
        "load": _session_handler(_load),
        "smd_columns": _session_handler(_smd_columns),
        "save": _session_handler(lambda s, p: s.save_data(p["path"])),
        "set": _session_handler(_set),
        "reset": _session_handler(lambda s, p: s.reset()),
        "remove_bleaching": _session_handler(
            lambda s, p: s.remove_bleaching(int(p["method"]), p.get("thresholds"))
        ),
        "clip_outliers": _session_handler(
            lambda s, p: s.clip_outliers(tuple(p["x_lim"]), int(p["max_outliers"]))
        ),
        "update_priors": _session_handler(lambda s, p: s.update_priors(p["choice"])),
        "init_priors": _session_handler(
            lambda s, p: s.init_priors(p["theta"], p["counts"], int(p["status"]))
        ),
        "export_summary": _session_handler(lambda s, p: s.export_summary(p["path"])),
        "export_traces": _session_handler(
            lambda s, p: s.export_traces(
                p["path"], p["channels"], int(p["states"]), p.get("group", "all"), p.get("fmt")
            )
        ),
        "export_smd": _session_handler(
            lambda s, p: s.export_smd(
                p["path"], int(p["states"]), p.get("group", "all"), p.get("fmt")
            )
        ),
    }
    for name, handler in handlers.items():
        dispatcher.register(PREFIX + name, handler)


def list_methods() -> dict[str, str]:
    """Return the ebFRET RPC method descriptions."""
    return {
        METHOD_COMPUTE: "Fit an empirical-Bayes Gaussian HMM over binned FRET traces.",
        PREFIX + "*": "One ebFRET main-window session: load, set controls, run, export.",
    }


def run_analysis(
    traces: FretTraceSet | list[np.ndarray], settings: EbfretSettings
) -> EbfretAnalysis:
    """Run the headless ebFRET analysis for a trace set under the given settings.

    Parameters
    ----------
    traces : FretTraceSet or list of numpy.ndarray
        Binned FRET-efficiency traces.
    settings : EbfretSettings
        Analysis settings.

    Returns
    -------
    EbfretAnalysis
    """
    items = traces.traces if isinstance(traces, FretTraceSet) else list(traces)
    return analyse(items, **settings.analyse_kwargs())


def _analysis_to_jsonable(analysis: EbfretAnalysis) -> dict[str, Any]:
    """Convert an :class:`EbfretAnalysis` into a JSON-serialisable dict."""
    return {
        "n_states": analysis.n_states,
        "evidence": analysis.evidence,
        "scan": {str(k): v for k, v in analysis.scan.items()},
        "states": [
            {
                "index": s.index,
                "mean": s.mean,
                "precision": s.precision,
                "std": s.std,
                "occupancy": s.occupancy,
            }
            for s in analysis.states
        ],
        "transition_counts": analysis.transition_counts.tolist(),
        "n_dwells": len(analysis.dwells),
    }


def compute_handler(
    traces: list[list[float]] | None = None,
    settings: dict[str, Any] | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """RPC handler: fit an ebFRET model from JSON-transported traces.

    Parameters
    ----------
    traces : list of list of float
        Binned FRET-efficiency traces.
    settings : dict, optional
        Fields of :class:`EbfretSettings`.

    Returns
    -------
    dict
        JSON-serialisable analysis summary.
    """
    trace_arrays = [np.asarray(t, dtype=float) for t in (traces or [])]
    cfg = EbfretSettings(**(settings or {}))
    analysis = run_analysis(trace_arrays, cfg)
    return {"ok": True, "result": _analysis_to_jsonable(analysis)}
