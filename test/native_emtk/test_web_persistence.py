"""The web page's kept settings (``chisurf.web``): localStorage across reloads.

Four gates:

* the *store* -- one JSON payload under :data:`chisurf.web.SETTINGS_KEY`, read
  and written through a ``localStorage`` stand-in (the page itself reaches the
  real one through Pyodide's ``js`` bridge): roundtrip, a fresh store reading
  what a previous "page" wrote, a corrupt payload dropped, a full quota
  degrading to the session, no storage at all staying session-only;
* the *shell's sink* -- open/close reach the ``settings_sink``, which debounces
  a save, and a page without threads (Pyodide's shape) saves right away;
* the *restore* -- a stored payload put back on a fresh shell reopens the
  plugins it lists, with their dock layouts applied first;
* the *factory* -- ``chisurf.web.make_app`` in the Pyodide shape (no Qt, no
  sockets) boots with a stored payload and reopens the plugin it names, then
  writes the changed shape back.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp

ROOT = Path(__file__).resolve().parents[2]


# -- stand-ins ----------------------------------------------------------------- #

class FakeLocalStorage:
    """The part of ``localStorage`` the store uses, as a dict."""

    def __init__(self):
        self.data: dict[str, str] = {}

    def getItem(self, key):
        return self.data.get(str(key))

    def setItem(self, key, value):
        self.data[str(key)] = str(value)

    def removeItem(self, key):
        self.data.pop(str(key), None)


class FullLocalStorage(FakeLocalStorage):
    """``localStorage`` past its quota: every write raises."""

    def setItem(self, key, value):
        raise RuntimeError("QuotaExceededError (simulated)")


class StubShell:
    """Just what :func:`chisurf.web.capture_settings` reads."""

    def export_settings(self) -> dict:
        return {"open": ["stub"], "ribbon": {"pinned": True}}

    native_layouts: dict = {}


CATALOG = {
    "probe": {"display_name": "Tools:Probe", "entrypoints": {"emtk": "x:y"}},
    "second": {"display_name": "Tools:Second", "entrypoints": {"emtk": "x:y"}},
}


def _loader(plugin_id: str) -> ImApp:
    return ImApp(lambda: None)


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    """Preferences go to a scratch folder; the language is put back after the test."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def _shell(settings_sink=None):
    from chisurf.emtk import i18n
    from chisurf.emtk.main_app import EmtkShellApp

    i18n.install("en")
    return EmtkShellApp(CATALOG, loader=_loader, settings_sink=settings_sink)


# -- the store ----------------------------------------------------------------- #

def test_store_roundtrips_and_a_fresh_store_reads_a_previous_page():
    from chisurf.web import SETTINGS_KEY, WebSettingsStore

    storage = FakeLocalStorage()
    payload = {"version": 1, "shell": {"open": ["pch"]}, "docks": {}}

    first = WebSettingsStore(storage)
    assert first.persistent
    assert first.get() is None
    assert first.set(SETTINGS_KEY, payload) is True

    # The reload: a new page, a new store, the same browser storage.
    second = WebSettingsStore(storage)
    assert second.get() == payload

    second.delete(SETTINGS_KEY)
    assert WebSettingsStore(storage).get() is None
    assert storage.data == {}


def test_store_drops_a_corrupt_payload_and_boots_fresh():
    from chisurf.web import SETTINGS_KEY, WebSettingsStore

    storage = FakeLocalStorage()
    storage.data[SETTINGS_KEY] = '{"version": 1, "shell": '  # a half-write
    store = WebSettingsStore(storage)
    assert store.get() is None
    assert SETTINGS_KEY not in storage.data, "the corrupt payload must not be served again"

    storage.data[SETTINGS_KEY] = "[1, 2]"  # valid JSON, not a settings object
    assert store.get() is None


def test_a_full_quota_degrades_to_the_session_and_says_so_once():
    from chisurf.web import SETTINGS_KEY, WebSettingsSaver, WebSettingsStore

    store = WebSettingsStore(FullLocalStorage())
    saver = WebSettingsSaver(StubShell(), store)

    assert store.set(SETTINGS_KEY, {"version": 1}) is False
    assert store.get() is None
    assert saver.flush() is False and saver.refused == 1 and saver.written == 0
    assert store._warned, "the refusal must be said (once) -- settings last for the session"

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logging.getLogger("chisurf.web").addHandler(handler)
    try:
        store.failed(RuntimeError("again"))
    finally:
        logging.getLogger("chisurf.web").removeHandler(handler)
    assert not [r for r in records if "not persisted" in r.getMessage()], (
        "said once, not on every write")


def test_no_local_storage_is_session_only():
    from chisurf.web import WebSettingsStore

    store = WebSettingsStore(storage=False)  # falsy: not a page, no browser storage
    assert not store.persistent
    assert store.set(payload={"version": 1}) is True
    assert store.get() == {"version": 1}
    # Another "page" (a fresh store) starts empty: nothing was persisted.
    assert WebSettingsStore(storage=False).get() is None


# -- the shell's sink ------------------------------------------------------------ #

def test_open_and_close_reach_the_sink_which_debounces_the_save():
    from chisurf.web import WebSettingsSaver, WebSettingsStore

    store = WebSettingsStore(storage=False)
    saver = WebSettingsSaver(None, store, debounce=60)  # nothing fires on its own
    shell = _shell(settings_sink=saver)
    saver.app = shell
    try:
        shell.open_plugin("probe")
        assert saver._timer is not None, "the sink must have scheduled a debounced save"
        assert store.get() is None, "debounced: the change alone must not write yet"

        assert saver.flush() is True
        payload = store.get()
        assert payload is not None
        assert payload["version"] == 1
        assert payload["shell"]["open"] == ["probe"]
        assert set(payload["docks"]) == {"shell", "workspace"}, (
            "both dock layouts ride in the payload")
        assert payload["saved_at"] > 0

        shell.close_plugin("probe")
        assert saver.flush() is True
        assert store.get()["shell"]["open"] == []
    finally:
        saver.cancel()
        shell.close()


def test_the_desktop_shell_passes_no_sink_and_is_unchanged():
    shell = _shell()
    try:
        assert shell._settings_sink is None
        shell.open_plugin("probe")  # no sink to hear it; opening works as before
        assert "probe" in shell.hosted
    finally:
        shell.close()


def test_a_scheduled_save_fires_once_the_debounce_is_over():
    from chisurf.web import WebSettingsSaver, WebSettingsStore

    store = WebSettingsStore(storage=False)
    saver = WebSettingsSaver(StubShell(), store, debounce=0.05)
    try:
        saver({})  # the sink's shape: schedule, then the timer writes
        deadline = time.monotonic() + 2.0
        while store.get() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert store.get() is not None and saver.written == 1
    finally:
        saver.cancel()


def test_a_cancelled_save_never_fires():
    from chisurf.web import WebSettingsSaver, WebSettingsStore

    store = WebSettingsStore(storage=False)
    saver = WebSettingsSaver(StubShell(), store, debounce=0.3)
    try:
        saver({})
        saver.cancel()
        time.sleep(0.5)
        assert store.get() is None and saver.written == 0
    finally:
        saver.cancel()


def test_a_page_without_threads_saves_right_away(monkeypatch):
    """Pyodide's shape: ``Thread.start`` raises, so the debounced save runs inline."""
    from chisurf.web import WebSettingsSaver, WebSettingsStore

    def refuse(self, *args, **kwargs):
        raise RuntimeError("Pyodide simulated: cannot start a thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    store = WebSettingsStore(storage=False)
    saver = WebSettingsSaver(StubShell(), store, debounce=5)
    saver({})
    assert saver.written == 1 and store.get() is not None, (
        "no threads and no js timer: the save must not be lost")


def test_listening_to_the_page_needs_one():
    from chisurf.web import WebSettingsSaver, WebSettingsStore

    saver = WebSettingsSaver(None, WebSettingsStore(storage=False))
    assert saver.listen_to_page() is False, "off a page there is nothing to listen to"


# -- the restore ----------------------------------------------------------------- #

def test_a_stored_payload_reopens_its_plugins_on_a_fresh_shell():
    from chisurf.web import apply_settings, capture_settings

    first = _shell()
    try:
        first.open_plugin("probe")
        payload = capture_settings(first)
        assert payload["shell"]["open"] == ["probe"]
    finally:
        first.close()

    second = _shell()
    try:
        assert not second.hosted
        apply_settings(second, payload)
        assert list(second.hosted) == ["probe"]
        assert second.docks.window(second.hosted["probe"].key) is not None, (
            "the payload's plugin is back as a dock window")
    finally:
        second.close()


def test_a_malformed_payload_is_skipped_never_fatal():
    from chisurf.web import apply_settings

    shell = _shell()
    try:
        for bad in (None, 42, "x", {"docks": {"shell": 1}, "shell": []}):
            apply_settings(shell, bad)  # must not raise
        assert not shell.hosted
    finally:
        shell.close()


# -- the factory, without Qt or sockets (the Pyodide shape) ---------------------- #

_PROBE = r'''
import json, socket, sys

class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6", "pyqtgraph"}:
            raise ImportError("Qt forbidden: " + fullname)
        return None

sys.meta_path.insert(0, BlockQt())

class NoSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("Pyodide simulated: cannot create sockets")

socket.socket = NoSocket

import chisurf.web

SEED = json.loads(SEED_JSON)

class SeedStore(chisurf.web.WebSettingsStore):
    """The store of a page whose ``localStorage`` holds SEED (from a previous visit)."""
    written = None

    def get(self, key=None):
        return SEED

    def set(self, key=None, payload=None):
        SeedStore.written = payload
        return True

chisurf.web.WebSettingsStore = SeedStore

from emtk.testing import RecordingPainter

result = {"store": "SeedStore"}
app = chisurf.web.make_app()
result["app"] = type(app).__name__
saver = app._settings_sink
result["has_sink"] = saver is not None

# The payload's plugin was reopened at boot, as a dock window.
hosted = app.hosted.get("pch")
result["restored"] = hosted is not None
if hosted is not None:
    result["dock_window"] = app.docks.window(hosted.key) is not None

painter = RecordingPainter()
for _ in range(600):
    app.draw(painter, 0, 0, 1200, 800)
    if hosted is not None and hosted.build is None:
        break
result["error"] = getattr(hosted, "error", None) if hosted is not None else "no plugin"

# A change (the plugin closed again) is written back through the store.
if hosted is not None:
    app.close_plugin("pch")
    saver.cancel()
    assert saver.flush(), "the write-back failed"
    written = SeedStore.written or {}
    result["written_version"] = written.get("version")
    result["written_open"] = (written.get("shell") or {}).get("open")
    result["written_docks"] = sorted((written.get("docks") or {}).keys())
print(json.dumps(result))
'''


def test_page_factory_restores_a_stored_payload_and_writes_back():
    """The Pyodide shape of a return visit: no Qt, sockets raise, the stored
    payload reopens its plugin, and the next change is written back."""
    seed = {"version": 1, "saved_at": 1.0,
            "shell": {"open": ["pch"], "ribbon": None}, "docks": {}}
    probe = _PROBE.replace("SEED_JSON", json.dumps(json.dumps(seed)))
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(ROOT),
        env={**os.environ},
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["app"] == "EmtkShellApp"
    assert out["has_sink"], "the page's shell must save through the sink"
    assert out["restored"], "the payload's plugin was not reopened at boot"
    assert out["dock_window"], "the reopened plugin has no dock window"
    assert out["error"] in (None, ""), f"pch failed to build: {out['error']}"
    assert out["written_version"] == 1
    assert out["written_open"] == []
    assert out["written_docks"] == ["shell", "workspace"]
