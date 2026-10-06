"""The native MMFDB Admin as a whole: Qt-free, drawn offline at both sizes, settings, the worker.

The click tests (``test_native_clicks``) and the model tests (``test_native_model``)
cover what the panels do; these cover what the window owes every port: no Qt on
the production path, a sensible window before any connection, a persistence round
trip that never stores a password, and server calls that run in order off the
drawing thread.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from chisurf.plugins.emtk_test_input import SMALL, Driver

from .native_support import admin_folder, app, client, offline_app, seeded_template  # noqa: F401

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.json"


def test_the_production_path_is_qt_free(tmp_path, monkeypatch):
    from test.gui.emtk_port_parity import qt_free

    from . import seeded_admin as sa

    # The check draws make_app(), which connects on its first frame: point the
    # subprocess at an empty temporary MMFDB, never the user's own.
    sa.use_folder(tmp_path / "mmfdb", monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = qt_free("mmfdb_admin", "chisurf.plugins.core.mmfdb_admin.gui.app:make_app")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    entry = json.loads(MANIFEST.read_text(encoding="utf-8"))["entrypoints"]
    assert entry.get("emtk") == "chisurf.plugins.core.mmfdb_admin.gui.app:make_app"
    assert entry.get("gui"), "the Qt tool stays reachable as the legacy entry"


@pytest.mark.parametrize("size", [(1200, 800), SMALL])
def test_draws_before_any_connection(size):
    application = offline_app()
    try:
        d = Driver(application, size=size)
        d.draw(3)
        assert not application.model.connected
        texts = [t[5] for t in d.draw(1).texts]
        assert any(t.startswith("Not connected") for t in texts), texts
        assert "Overview" in texts
        for name in ("search", "back", "next", "help", "guide"):
            x, y, w, h = application.item_rects[name]
            assert x >= 0 and y >= 0 and x + w <= size[0] + 1 and y + h <= size[1] + 1, (name, size)
    finally:
        application.close()


def test_every_panel_draws_connected(app):
    d = Driver(app)
    d.draw(3)
    assert app.model.connected, app.model.status
    for key in app.model.panel_keys():
        app.model.select(key)
        d.draw(2)
        assert d.drawn(app.model.panel_name(key)), key


def test_settings_round_trip_never_store_the_password(app):
    model = app.model
    model.password = "s3cret-pass"
    model.select("spectra")
    app.splits["entity"] = 0.3
    saved = app.export_settings()
    assert "s3cret-pass" not in json.dumps(saved)
    assert saved["selected"] == "spectra"

    other = offline_app()
    try:
        other.restore_settings(json.loads(json.dumps(saved)))
        assert other.model.selected == "spectra"
        assert other.splits["entity"] == pytest.approx(0.3)
        other.restore_settings({"selected": "no_such_panel", "splits": {"bogus": 1.0}})
        assert other.model.selected == "spectra"
        assert "bogus" not in other.splits
    finally:
        other.close()


def test_the_thread_runner_runs_calls_in_order_off_the_drawing_thread():
    from chisurf.plugins.core.mmfdb_admin.gui.native.runner import Call, ThreadRunner

    runner = ThreadRunner()
    main = threading.get_ident()
    seen, done, errors = [], [], []
    try:
        for i in range(5):
            runner.submit(Call(f"c{i}", lambda i=i: (seen.append((i, threading.get_ident())), i)[1],
                               done=done.append))
        runner.submit(Call("bad", lambda: 1 / 0, failed=errors.append))
        import time

        deadline = time.time() + 10.0
        while (len(done) < 5 or not errors) and time.time() < deadline:
            runner.poll()
            time.sleep(0.01)
    finally:
        runner.close()
    assert done == [0, 1, 2, 3, 4]
    assert [i for i, _ in seen] == [0, 1, 2, 3, 4]
    assert all(tid != main for _, tid in seen)
    assert errors and "division" in errors[0]
