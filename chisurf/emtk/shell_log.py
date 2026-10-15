"""The emtk shell's Log dock: the log, the server's calls and the undo history, as the Qt *Logging* dock has them.

The Qt dock (``dockWidgetHistory``) holds three things: the log list with a *Filter* field and a *hide* switch
(non-matching rows are hidden, else only dimmed), the *RPC Monitor* (every call the server answered, with *Clear*
and *Pause*), and the *History* browser (the science's undo steps; a click goes to that step, *Clear* forgets
them). Here they are the three tabs of one ``view.json`` (``views/log.view.json``) over :class:`ShellLog`; the
tables are the spec's ``table`` sections. The log also has a *Level* choice: records below it are not shown.

Records arrive on any thread (a logging handler, the server's dispatcher monitor); they are kept in bounded
deques under a lock and turned into rows on the frame thread.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

_log = logging.getLogger("chisurf.emtk.shell")

#: How many log records and server calls the dock keeps.
LOG_LINES = 2000
RPC_LINES = 2000
#: The level choice's values, low to high.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
VIEW = Path(__file__).with_name("views") / "log.view.json"


class _Rows(list):
    """Rows with a ``revision`` the table compares, so a refresh rebinds it once."""

    revision = 0


class LogRecords(logging.Handler):
    """Keep the last *lines* log records (time, level, logger, message) for the Log dock."""

    def __init__(self, lines: int = LOG_LINES) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: deque[dict] = deque(maxlen=lines)
        self.lock_rows = threading.Lock()
        self.revision = 0

    @property
    def lines(self) -> list[str]:
        """The records as text lines, oldest first."""
        with self.lock_rows:
            return [f"{r['level']} {r['origin']}: {r['message']}" for r in self.records]

    def emit(self, record: logging.LogRecord) -> None:
        try:
            row = {
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "levelno": record.levelno,
                "origin": record.name,
                "message": record.getMessage(),
            }
            with self.lock_rows:
                self.records.append(row)
                self.revision += 1
        except Exception:  # noqa: BLE001 - a log handler must never raise into the caller
            self.handleError(record)

    def clear(self) -> None:
        with self.lock_rows:
            self.records.clear()
            self.revision += 1


class RpcCalls:
    """The server's answered calls (:meth:`chisurf.server.dispatcher.ServiceDispatcher.add_monitor`)."""

    def __init__(self, lines: int = RPC_LINES) -> None:
        self.calls: deque[dict] = deque(maxlen=lines)
        self.lock = threading.Lock()
        self.revision = 0
        self.paused = False
        self._registered = False

    def register(self) -> None:
        from chisurf.server.dispatcher import ServiceDispatcher

        if not self._registered:
            ServiceDispatcher.add_monitor(self.record)
            self._registered = True

    def unregister(self) -> None:
        if self._registered:
            from chisurf.server.dispatcher import ServiceDispatcher

            ServiceDispatcher.remove_monitor(self.record)
            self._registered = False

    def record(self, method: str, params: dict, result: dict, elapsed: float) -> None:
        """The dispatcher's monitor callback (its thread): one answered call."""
        if self.paused:
            return
        result = result if isinstance(result, dict) else {}
        ok = bool(result.get("ok", True))
        origin, target, what = _split_method(str(method))
        row = {
            "time": time.strftime("%H:%M:%S", time.localtime()),
            "origin": origin,
            "target": target,
            "what": what,
            "duration": f"{float(elapsed) * 1000.0:.1f} ms",
            "status": "OK" if ok else f"ERR({result.get('error_code', '?')})",
            "params": _summary(params),
        }
        with self.lock:
            self.calls.append(row)
            self.revision += 1

    def clear(self) -> None:
        with self.lock:
            self.calls.clear()
            self.revision += 1


def _split_method(method: str) -> tuple[str, str, str]:
    """``("", "fit.run", "run")`` from ``"fit.run"``: as the Qt RPC monitor splits a method name."""
    parts = method.split(".")
    if len(parts) == 2:
        return parts[0], method, parts[1]
    if len(parts) <= 1:
        return "", method, method
    return ".".join(parts[:-2][-2:]), ".".join(parts[-2:]), parts[-1]


def _summary(params: Any, limit: int = 80) -> str:
    if not isinstance(params, dict) or not params:
        return ""
    keys = list(params)
    if len(keys) <= 2:
        text = ", ".join(f"{key}={str(params[key])[:40]}" for key in keys)
    else:
        text = f"{len(keys)} keys: {', '.join(keys[:3])}…"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _matches(row: dict, needle: str, keys) -> bool:
    if not needle:
        return True
    return needle in " ".join(str(row.get(key, "")) for key in keys).casefold()


class ShellLog:
    """The Log dock's model: what ``views/log.view.json`` reads and calls.

    Parameters
    ----------
    project : chisurf.emtk.shell_session.ShellProject
        Owns the undo history the *History* tab shows and navigates.
    """

    def __init__(self, project: Any) -> None:
        self.project = project
        self.records = LogRecords()
        self.rpc = RpcCalls()
        self.form = FormState()
        self.spec = json.loads(VIEW.read_text(encoding="utf-8"))
        #: The log's filter text, the level shown at least, and whether non-matching rows are hidden.
        self.log_filter = ""
        self.log_level = "INFO"
        self.log_hide = False
        self.rpc_filter = ""
        self.history_filter = ""
        self.details = ""
        self._cache: dict[str, tuple[Any, _Rows]] = {}
        self._history_events: list[dict] = []

    # -- wiring -------------------------------------------------------------- #
    def install(self) -> None:
        """Start collecting the ``chisurf`` log and the server's calls."""
        logging.getLogger("chisurf").addHandler(self.records)
        self.rpc.register()

    def close(self) -> None:
        logging.getLogger("chisurf").removeHandler(self.records)
        self.rpc.unregister()

    def draw(self, box) -> None:
        """The dock's content."""
        draw_form(self.spec, self, self.form)

    # -- the spec's bindings --------------------------------------------------- #
    @property
    def rpc_paused(self) -> bool:
        """*Pause*: no new calls are recorded while it is on."""
        return self.rpc.paused

    @rpc_paused.setter
    def rpc_paused(self, value: bool) -> None:
        self.rpc.paused = bool(value)

    def level_names(self) -> list[str]:
        return list(LEVELS)

    def _rows(self, name: str, key: Any, build) -> _Rows:
        cached = self._cache.get(name)
        if cached is not None and cached[0] == key:
            return cached[1]
        rows = _Rows(build())
        rows.revision = (cached[1].revision + 1) if cached is not None else 1
        self._cache[name] = (key, rows)
        return rows

    def log_rows(self) -> _Rows:
        """The log, at or above the level; rows the filter misses are hidden or dimmed."""
        needle = self.log_filter.strip().casefold()
        floor = logging.getLevelName(self.log_level) if self.log_level in LEVELS else logging.INFO

        def build():
            with self.records.lock_rows:
                rows = list(self.records.records)
            out = []
            for index, row in enumerate(rows):
                if row["levelno"] < floor:
                    continue
                hit = _matches(row, needle, ("time", "level", "origin", "message"))
                if not hit and self.log_hide:
                    continue
                out.append(dict(row, index=index, muted=bool(needle) and not hit))
            return out

        key = (self.records.revision, needle, floor, self.log_hide)
        return self._rows("log", key, build)

    def rpc_rows(self) -> _Rows:
        needle = self.rpc_filter.strip().casefold()

        def build():
            with self.rpc.lock:
                calls = list(self.rpc.calls)
            keys = ("time", "origin", "target", "what", "status", "params")
            return [
                dict(row, index=i) for i, row in enumerate(calls) if _matches(row, needle, keys)
            ]

        return self._rows("rpc", (self.rpc.revision, needle), build)

    def history_rows(self) -> _Rows:
        """The undo history's steps; the current one is marked ▶."""
        history = getattr(self.project, "history", None)
        events = history.list_events() if history is not None else []
        cursor = history.cursor_index() if history is not None else -1
        self._history_events = events
        needle = self.history_filter.strip().casefold()

        def build():
            out = []
            for index, event in enumerate(events):
                row = {
                    "index": index,
                    "current": "▶" if index == cursor else "",
                    "time": str(event.get("timestamp", ""))[11:19],
                    "action": str(event.get("action_type", "")),
                    "summary": str(event.get("summary", "")),
                }
                if _matches(row, needle, ("time", "action", "summary")):
                    out.append(row)
            return out

        key = (len(events), cursor, events[-1].get("event_id") if events else None, needle)
        return self._rows("history", key, build)

    def history_selected(self, record: Any) -> None:
        """A click on a step: show its details and go to it (the science of that step)."""
        if not isinstance(record, dict):
            return
        index = int(record.get("index", -1))
        if 0 <= index < len(self._history_events):
            try:
                self.details = json.dumps(
                    self._history_events[index], indent=2, sort_keys=True, default=str
                )
            except Exception:  # noqa: BLE001 - details are a convenience
                self.details = str(self._history_events[index])
        go = getattr(self.project, "go_to_history", None)
        if callable(go):
            go(index)

    def history_details(self) -> str:
        return self.details or tr("Select a step to see its details and go back to it.")

    def clear_log(self) -> None:
        """*Clear* (Logging): forget the records shown."""
        self.records.clear()

    def clear_rpc(self) -> None:
        """*Clear* (RPC Monitor): forget the calls shown."""
        self.rpc.clear()

    def clear_history(self) -> None:
        """*Clear* (History): forget the undo steps; the science stays as it is."""
        clear = getattr(self.project, "clear_history", None)
        if callable(clear):
            clear()
        self.details = ""

    def copy_log_message(self, record: Any = None) -> None:
        """Copy the message text of *record* to the clipboard."""
        if isinstance(record, dict):
            from emtk import clipboard

            clipboard.copy(str(record.get("message", "")))

    def copy_log_row(self, record: Any = None) -> None:
        """Copy the formatted log row [time] [level] origin: message to the clipboard."""
        if isinstance(record, dict):
            from emtk import clipboard

            clipboard.copy(
                f"[{record.get('time', '')}] [{record.get('level', '')}] "
                f"{record.get('origin', '')}: {record.get('message', '')}"
            )

    def copy_all_logs(self, record: Any = None) -> None:
        """Copy all visible (filtered) log lines to the clipboard."""
        from emtk import clipboard

        rows = self.log_rows()
        lines = [
            f"[{r.get('time', '')}] [{r.get('level', '')}] {r.get('origin', '')}: {r.get('message', '')}"
            for r in rows
            if not r.get("muted")
        ]
        clipboard.copy("\n".join(lines))

    def copy_rpc_row(self, record: Any = None) -> None:
        """Copy the formatted RPC row to the clipboard."""
        if isinstance(record, dict):
            from emtk import clipboard

            clipboard.copy(
                f"[{record.get('time', '')}] {record.get('origin', '')} "
                f"{record.get('target', '')} ({record.get('status', '')}, "
                f"{record.get('duration', '')}) {record.get('params', '')}"
            )

    def copy_rpc_params(self, record: Any = None) -> None:
        """Copy the parameters of the RPC call to the clipboard."""
        if isinstance(record, dict):
            from emtk import clipboard

            clipboard.copy(str(record.get("params", "")))

    def copy_all_rpc(self, record: Any = None) -> None:
        """Copy all visible RPC calls to the clipboard."""
        from emtk import clipboard

        rows = self.rpc_rows()
        lines = [
            f"[{r.get('time', '')}] {r.get('origin', '')} {r.get('target', '')} "
            f"({r.get('status', '')}, {r.get('duration', '')}) {r.get('params', '')}"
            for r in rows
        ]
        clipboard.copy("\n".join(lines))

    def enabled(self, name: str) -> bool:
        if name == "clear_history":
            return bool(getattr(self.project, "history_ready", False)) and not getattr(
                self.project, "busy", False
            )
        return True


__all__ = ["LEVELS", "LogRecords", "RpcCalls", "ShellLog"]
