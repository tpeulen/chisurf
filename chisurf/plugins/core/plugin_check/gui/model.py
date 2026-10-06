"""Plugin startup checks without Qt: what is installed, how it is wired, and a sweep that constructs each native app.

The list is what the Qt tool listed (``chisurf.plugins.iter_plugins``: built-in and user plugins, their dependency
maps, the dependency problems the resolver reports), joined with each plugin's manifest for the native entry point.
A sweep builds every native app in a fresh process on throw-away settings, one plugin at a time, and the results come
back through a queue that :meth:`PluginCheckModel.poll` drains once per frame, so the window never blocks.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

#: The longest an error is shown in the table before the details pane (the Qt tool cut at 50 characters).
ERROR_CELL = 50
#: Consecutive failures after which a plugin is blacklisted (skipped while "Skip blacklisted" is on).
BLACKLIST_AFTER = 5
#: How many plugins "Test safe plugins" checks (the first ones of the list), and its shorter startup timeout.
SAFE_COUNT = 10
SAFE_TIMEOUT = 5.0

#: The words the table shows for a result.
STATUS_WORDS = {
    "pass": "pass",
    "fail": "fail",
    "skipped": "skipped",
    "pending": "Qt only",
    "non_gui": "no GUI",
    "cancelled": "cancelled",
}
NOT_CHECKED = "pending"


def dependency_summary(requires: dict, optional: dict) -> str:
    """The "Depends on" cell: hard dependencies by name (they decide load order), optional ones counted."""
    parts = []
    if requires:
        parts.append(", ".join(sorted(requires)))
    if optional:
        parts.append(f"(+{len(optional)} optional)")
    return " ".join(parts)


def render_bounds(mapping: dict) -> str:
    """``name bound`` pairs; ``*`` (any version) is noise beside every name, so a bare name stands for it."""
    return ", ".join(
        name if str(bound).strip() in ("", "*") else f"{name} {bound}"
        for name, bound in sorted(mapping.items())
    )


def discover() -> tuple[dict[str, dict], Any]:
    """Every discovered plugin as ``{key: manifest-like dict}`` and the dependency resolver's report (or ``None``).

    Each entry is the plugin's manifest (its ``entrypoints`` are what a sweep constructs) with the discovery record's
    ``plugin_name`` (the menu path), ``source`` (built-in / user), ``module_path`` and dependency maps laid over it.
    """
    import chisurf.plugins as plugins
    from chisurf.emtk.plugins import manifests

    plugins.invalidate_plugin_cache()
    records = list(plugins.iter_plugins())
    try:
        manifest_by_id = manifests()
    except Exception:  # a broken manifest elsewhere must not hide the list
        manifest_by_id = {}
    catalog: dict[str, dict] = {}
    for record in records:
        key = record.get("manifest_id") or record.get("module_path")
        entry = dict(manifest_by_id.get(record.get("manifest_id") or "", {}))
        entry.update(
            id=key,
            plugin_name=record.get("plugin_name") or key,
            source=record.get("source", "built-in"),
            module_path=record.get("module_path", ""),
            version=entry.get("version") or record.get("manifest_version") or "",
            description=record.get("description") or entry.get("description", ""),
            requires=record.get("requires") or {},
            optional_requires=record.get("optional_requires") or {},
        )
        catalog[key] = entry
    report = None
    try:
        from chisurf.core.plugin.dependencies import resolve

        report = resolve(
            {
                "id": r.get("manifest_id") or "",
                "version": r.get("manifest_version") or "",
                "requires": r.get("requires") or {},
                "optional_requires": r.get("optional_requires") or {},
            }
            for r in records
        )
    except Exception:
        report = None
    return catalog, report


class PluginCheckModel:
    """The plugin list, the sweep, and what the window shows of them."""

    def __init__(self, catalog: dict | None = None, report: Any = None) -> None:
        if catalog is None:
            catalog, report = discover()
        self.catalog: dict[str, dict] = catalog
        self.report = report
        self.results: dict[str, dict] = {}
        self.blacklisted: set[str] = set()
        self.failures: dict[str, int] = {}
        self.skip_blacklisted = True
        self.delay = 0.5
        self.timeout = 30.0
        self.current = 0
        self.total = 0
        self.running = False
        self.selected_key = next(iter(self.catalog), "")
        self.message = self._ready_message()
        self._events: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    # -- the list ---------------------------------------------------------------- #
    def name_of(self, key: str) -> str:
        """The menu path the Qt tree showed in its first column."""
        manifest = self.catalog.get(key, {})
        return str(manifest.get("plugin_name") or manifest.get("display_name") or key)

    def problems(self) -> list[str]:
        """The dependency resolver's complaints (a missing or out-of-range requirement), whole list."""
        return list(self.report.problems()) if self.report is not None else []

    def _ready_message(self) -> str:
        found = len(self.catalog)
        problems = len(self.problems())
        if problems:
            return f"{found} plugin(s) found, {problems} dependency problem(s); select a plugin for details"
        return f"Ready: {found} plugin(s) found"

    def refresh(self) -> bool:
        """Rescan the plugin folders and clear the displayed results (not while a sweep runs)."""
        if self.running:
            return False
        try:
            self.catalog, self.report = discover()
        except Exception as exc:
            self.message = f"Error loading plugins: {exc}"
            return False
        self.results.clear()
        self.current = self.total = 0
        if self.selected_key not in self.catalog:
            self.selected_key = next(iter(self.catalog), "")
        self.message = self._ready_message()
        return True

    # -- what the window shows ----------------------------------------------------- #
    def status_of(self, key: str) -> str:
        """The word in the Status column."""
        result = self.results.get(key)
        return (
            STATUS_WORDS.get(result.get("status"), result.get("status", ""))
            if result
            else NOT_CHECKED
        )

    def check_rows(self) -> list[dict]:
        """One record per plugin for the table: Plugin, Status, Source, Depends on, Error."""
        rows = []
        for key in self.catalog:
            manifest = self.catalog[key]
            result = self.results.get(key, {})
            error = str(result.get("error") or "")
            first = error.splitlines()[0] if error else ""
            rows.append(
                {
                    "key": key,
                    "plugin": self.name_of(key),
                    "status": self.status_of(key),
                    "source": manifest.get("source", "built-in"),
                    "depends": dependency_summary(
                        manifest.get("requires") or {}, manifest.get("optional_requires") or {}
                    ),
                    "error": first if len(first) <= ERROR_CELL else first[:ERROR_CELL] + "...",
                    "tip": "\n".join(
                        part
                        for part in (self.name_of(key), error or self._depends_tip(manifest))
                        if part
                    ),
                    "muted": key not in self.results,
                }
            )
        return rows

    @staticmethod
    def _depends_tip(manifest: dict) -> str:
        parts = []
        if manifest.get("requires"):
            parts.append("Requires: " + render_bounds(manifest["requires"]))
        if manifest.get("optional_requires"):
            parts.append("Optional: " + render_bounds(manifest["optional_requires"]))
        return "\n".join(parts)

    def select_row(self, record: Any) -> None:
        """The table's ``selected_call``: a record, or ``None`` when the selection is cleared."""
        if isinstance(record, dict):
            self.selected_key = str(record.get("key", ""))

    @property
    def selected(self) -> dict:
        return self.catalog.get(self.selected_key, {})

    def details(self) -> list[tuple[str, str]]:
        """``(caption, text)`` blocks of the selected plugin: what the Qt details pane listed, plus the check result."""
        key = self.selected_key
        if key not in self.catalog:
            return []
        manifest = self.catalog[key]
        blocks = [
            ("Plugin", self.name_of(key)),
            ("Module", str(manifest.get("module_path") or "Unknown")),
            ("Source", str(manifest.get("source", "built-in"))),
            ("Version", str(manifest.get("version") or "")),
            ("Status", self.status_of(key)),
        ]
        if manifest.get("requires"):
            blocks.append(("Requires (load order)", render_bounds(manifest["requires"])))
        if manifest.get("optional_requires"):
            blocks.append(("Optional", render_bounds(manifest["optional_requires"])))
        mine = [
            line
            for line in self.problems()
            if manifest.get("id") and line.startswith(f"{manifest['id']}:")
        ]
        if mine:
            blocks.append(("Problems", "\n".join(mine)))
        if manifest.get("description"):
            blocks.append(("Description", str(manifest["description"]).strip()))
        entry = manifest.get("entrypoints") or {}
        if entry:
            blocks.append(("Entry points", "\n".join(f"{k}: {v}" for k, v in entry.items())))
        return blocks

    @property
    def error_text(self) -> str:
        """The selected plugin's whole error (and traceback): the Qt tool's error box, shown for a failed check."""
        result = self.results.get(self.selected_key, {})
        return "\n".join(
            part
            for part in (str(result.get("error") or ""), str(result.get("traceback") or ""))
            if part
        )

    @property
    def progress_fraction(self) -> float:
        return self.current / self.total if self.total else 0.0

    def progress_text(self) -> str:
        return f"{self.current}/{self.total}"

    def status_text(self) -> str:
        return self.message

    def enabled(self, action: str) -> bool:
        """Whether the action's button is live: the sweeps and Refresh wait for a running sweep, Stop needs one."""
        if action == "stop":
            return self.running
        return not self.running

    # -- actions (button rows call these with no arguments) ----------------------------- #
    def test_all(self) -> bool:
        return self.start()

    def test_safe(self) -> bool:
        return self.start(safe=True)

    def clear_blacklist(self) -> None:
        """Allow plugins blacklisted after repeated failures to be tested again."""
        self.blacklisted.clear()
        self.failures.clear()
        self.message = "Blacklist cleared"

    def stop(self) -> None:
        self._stop.set()

    # -- the sweep ------------------------------------------------------------------------ #
    def start(self, safe: bool = False) -> bool:
        if self.running:
            return False
        ids = list(self.catalog)
        if safe:
            ids = ids[:SAFE_COUNT]
        if not ids:
            self.message = "No plugins to test"
            return False
        self.running = True
        self._stop.clear()
        self.current, self.total = 0, len(ids)
        self.message = "Testing safe plugins (short timeouts)..." if safe else "Testing plugins..."
        snapshot = [(key, dict(self.catalog[key])) for key in ids]
        self._thread = threading.Thread(target=self._run, args=(snapshot, safe), daemon=True)
        self._thread.start()
        return True

    def _run(self, rows: list, safe: bool) -> None:
        try:
            for key, manifest in rows:
                if self._stop.is_set():
                    break
                entry = manifest.get("entrypoints", {}) or {}
                if self.skip_blacklisted and key in self.blacklisted:
                    result = {"status": "skipped", "error": "Blacklisted after repeated failures"}
                elif not entry.get("emtk"):
                    result = {
                        "status": "pending"
                        if entry.get("gui") or entry.get("script")
                        else "non_gui",
                        "error": "No native factory declared",
                    }
                else:
                    result = self._check(
                        entry["emtk"], min(self.timeout, SAFE_TIMEOUT) if safe else self.timeout
                    )
                self._events.put((key, result))
                if self._stop.wait(max(0.0, self.delay)):
                    break
        finally:
            self._events.put((None, {"status": "cancelled" if self._stop.is_set() else "complete"}))

    def _check(self, factory: str, timeout: float) -> dict:
        """Construct and draw *factory* in a fresh process on throw-away settings and a throw-away HOME."""
        with tempfile.TemporaryDirectory(prefix="chisurf-plugin-check-") as directory:
            home = Path(directory) / "home"
            home.mkdir()
            env = dict(
                os.environ,
                HOME=str(home),
                CHISURF_SETTINGS_DIR=directory,
                MMFDB_SETTINGS_DIR=directory,
                MMFDB_DATABASE_PATH=str(Path(directory) / "mmfdb.sqlite"),
                MMFDB_OBJECT_STORE_ROOT=str(Path(directory) / "objects"),
                NDXPLORER_SETTINGS_DIR=str(Path(directory) / "ndxplorer"),
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "chisurf.emtk.validation", "--factory", factory],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self._process = process
            started = time.monotonic()
            try:
                while True:
                    if self._stop.is_set():
                        return {"status": "cancelled"}
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        return {"status": "fail", "error": f"Startup timed out after {timeout:g}s"}
                    try:
                        stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                try:
                    return json.loads(stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    return {
                        "status": "fail",
                        "error": stderr or f"Child exited {process.returncode}",
                    }
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                self._process = None

    def poll(self) -> None:
        """Take what the worker has reported (once per frame)."""
        while True:
            try:
                key, result = self._events.get_nowait()
            except queue.Empty:
                break
            if key is None:
                self.running = False
                self.message = "Cancelled" if result["status"] == "cancelled" else self._summary()
            else:
                self.results[key] = result
                self.current += 1
                if result["status"] == "fail":
                    self.failures[key] = self.failures.get(key, 0) + 1
                    if self.failures[key] >= BLACKLIST_AFTER:
                        self.blacklisted.add(key)
                elif result["status"] == "pass":
                    self.failures.pop(key, None)
                    self.blacklisted.discard(key)
                self.message = f"Checked {self.current}/{self.total}: {self.name_of(key)}"

    def _summary(self) -> str:
        counts = {"pass": 0, "fail": 0, "skipped": 0}
        for result in self.results.values():
            if result.get("status") in counts:
                counts[result["status"]] += 1
        other = len(self.results) - sum(counts.values())
        return (
            f"Testing complete: {counts['pass']} pass, {counts['fail']} failed, {counts['skipped']} skipped"
            + (f", {other} without a native app" if other else "")
        )

    def close(self) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=3)
