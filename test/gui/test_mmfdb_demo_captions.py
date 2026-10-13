"""MMFDB Admin's demo-data action describes and shows its real synthetic table seed.

The retired Qt window populated the packaged synthetic smFRET burst tables after ten
clicks on its header label; the native app has an explicit *Demo data...* button on the
Import / Export panel. The confirmation names the packaged tables, declining starts
nothing, the running caption is shown while the call is out, and the result is the
real 120-row / 63-row seed (replayed: it is computed once against scratch services).
"""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest


class _HeldRunner:
    """Run the connection inline, hold every later call until :meth:`flush`."""

    on_error = None

    def __init__(self):
        from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner

        self.inline = InlineRunner()
        self.held = []
        self.hold = False

    def submit(self, call):
        (self.held.append if self.hold else self.inline.submit)(call)

    def flush(self):
        while self.held:
            self.inline.submit(self.held.pop(0))

    def poll(self):
        return False

    @property
    def busy(self):
        return bool(self.held)

    def close(self):
        pass


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    """The native app over scratch services, replaying only the seed result."""
    from mmfdb.config import configure_runtime, reset_runtime_config

    from chisurf.plugins.core.mmfdb_admin.gui.app import MMFDBAdminApp
    from chisurf.plugins.core.mmfdb_admin.test import seeded_admin as sa

    sa.use_folder(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    configure_runtime(
        settings_dir=tmp_path,
        database_path=tmp_path / "mmfdb.db",
        source_database_path=tmp_path / "missing.db",
        object_store_root=tmp_path / "objects",
    )

    def no_connect(*args, **kwargs):
        raise AssertionError("caption test attempted an external socket connection")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr(socket, "create_connection", no_connect)
    local = sa.admin_client()
    summary = local.populate_mock_data()
    assert Path(summary["database_path"]).resolve() == (tmp_path / "mmfdb.db").resolve()
    assert summary["input_row_counts"] == [50, 38, 32]
    assert summary["output_row_count"] == 63 and summary["synthetic"] is True
    calls = []

    class ReplayClient:
        """Delegate reads locally and return the already verified seed on demand."""

        def __getattr__(self, name):
            return getattr(local, name)

        def populate_mock_data(self):
            calls.append("populate")
            return copy.deepcopy(summary)

    runner = _HeldRunner()
    app = MMFDBAdminApp(client=ReplayClient(), runner=runner)
    app.model.user = "admin"
    from chisurf.plugins.emtk_test_input import Driver

    driver = Driver(app)
    driver.draw(3)
    assert app.model.connected, app.model.status
    driver.type_into_name("search", "Import / Export")
    driver.click_name("nav.import_export")
    driver.draw(2)
    try:
        yield app, driver, runner, summary, calls
    finally:
        app.close()
        reset_runtime_config()


def test_confirmation_describes_packaged_tables_and_declining_starts_nothing(demo_app):
    from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg

    app, driver, _runner, _summary, calls = demo_app
    driver.click_name("populate_demo")
    dialog = app.model.dialog
    assert isinstance(dialog, dlg.ConfirmDialog)
    assert "packaged synthetic smFRET burst tables" in dialog.text
    assert "test fixtures" not in dialog.text
    assert "synthetic smFRET burst" in " ".join(driver.draw(2).strings)  # the dialog shows it
    driver.click_name("dialog.no")
    assert app.model.dialog is None and not calls
    assert not app.model.current.busy_demo


def test_running_caption_and_real_result_survive_population(demo_app):
    app, driver, runner, summary, calls = demo_app
    panel = app.model.current
    driver.click_name("populate_demo")
    runner.hold = True
    driver.click_name("dialog.yes")
    assert panel.preview.startswith("Populating the packaged synthetic smFRET burst tables")
    assert "test fixtures" not in panel.preview
    assert panel.busy_demo and not panel.enabled("populate_demo") and not calls
    runner.hold = False
    runner.flush()
    assert calls == ["populate"]
    assert json.loads(panel.preview) == json.loads(json.dumps(summary, default=str))
    assert panel.message.startswith("Demo data populated:")
    assert not panel.busy_demo
