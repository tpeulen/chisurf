"""Main import regressions against real authenticated native-PTO HTTP transport."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets

from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    standalone_server as standalone_server,
)


@pytest.fixture
def import_host(authenticated_browser, sample_project_payload, monkeypatch):
    """Keep a real measured reader and live Qt windows while importing a store copy."""
    import chisurf as cs
    from chisurf.core.project import Project, restore_session
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.core.project.pto import write_project
    from chisurf.gui.main_helper import ProjectMixin

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class Host(QtWidgets.QWidget, ProjectMixin):
        pass

    host = Host()
    host.setWindowTitle("Existing scientific document")
    layout = QtWidgets.QVBoxLayout(host)
    layout.addWidget(QtWidgets.QLabel("Existing measured TCSPC science"))
    host.resize(420, 180)
    host.show()
    original = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    monkeypatch.setattr(cs, "imported_datasets", [original])
    monkeypatch.setattr(cs, "fits", [])
    document = ProjectDocument(name="original", path=Path("original.cs.pto"))
    host._project_document = document
    host._current_project_id = "original-project"
    host._current_project_version_id = "original-version"
    host._current_project_path = document.path
    host._current_project_name = document.name
    path = authenticated_browser["tmp_path"] / "import-me.cs.pto"
    write_project(path, sample_project_payload)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    notices = []
    for name in ("warning", "information"):
        monkeypatch.setattr(
            f"chisurf.gui.main_helper.dialogs.{name}",
            lambda *a, kind=name: notices.append((kind, a[-1])),
        )
    monkeypatch.setattr(
        "chisurf.gui.main_helper.dialogs.question", lambda *a: QtWidgets.QMessageBox.Yes
    )
    before = document.clone()
    old_bytes = path.read_bytes()
    old_y = original.y.copy()
    yield host, path, notices
    assert host._project_document == before
    assert host._current_project_id == "original-project"
    assert host._current_project_version_id == "original-version"
    assert host._current_project_path == before.path
    assert host._current_project_name == before.name
    assert cs.imported_datasets[0] is original
    np.testing.assert_array_equal(original.y, old_y)
    assert path.read_bytes() == old_bytes
    assert host.isVisible()
    host.close()
    application.processEvents()


def test_main_import_uses_configured_authenticated_http_without_adopting_store_copy(
    authenticated_browser,
    import_host,
    sample_project_payload,
    monkeypatch,
):
    """Use the configured server and verify exact science without attaching live ownership."""
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    host, path, notices = import_host
    construction = []
    calls = []
    init = ProjectBrowserClient.__init__
    call = ProjectBrowserClient._call

    def record_init(self, *args, **kwargs):
        construction.append(kwargs)
        return init(self, *args, **kwargs)

    def record_call(self, method, params=None, **kwargs):
        calls.append((method, self.token, self.mode))
        return call(self, method, params, **kwargs)

    monkeypatch.setattr(ProjectBrowserClient, "__init__", record_init)
    monkeypatch.setattr(ProjectBrowserClient, "_call", record_call)
    assert host.onImportProject() is True
    assert len(construction) == 1
    assert construction[0]["mmfdb_client"].mode == "remote"
    assert "inprocess" not in construction[0]
    assert [entry[0] for entry in calls] == [
        "project_browser.import_preview",
        "project_browser.import_csp",
        "project_browser.restore",
    ]
    assert all(entry[1:] == (authenticated_browser["token"], "remote") for entry in calls)
    projects = authenticated_browser["client"].list_projects()
    assert len(projects) == 1
    restored = authenticated_browser["client"].restore_project(projects[0]["latest_version_id"])
    assert restored["project_payload"] == sample_project_payload
    assert restored["project_id"] == projects[0]["project_id"]
    assert notices[0][0] == "information"


@pytest.mark.parametrize("token_state", ["missing", "rejected", "expired"])
def test_main_import_requires_actual_authenticated_deployment(
    authenticated_browser,
    import_host,
    monkeypatch,
    token_state,
):
    """Missing credentials and server-rejected credentials never invent local auth."""
    from mmfdb.repository import MFDatabase
    from mmfdb.security.credentials import credential_account, session_token_registry

    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config, credential_endpoint

    endpoint = credential_endpoint(client_config(authenticated_browser["settings"]))
    key = credential_account(*endpoint, "real-http-user")
    registry = session_token_registry()
    if token_state == "missing":
        monkeypatch.delitem(registry, key)
    elif token_state == "rejected":
        monkeypatch.setitem(registry, key, "rejected-real-http-token")
    else:
        with MFDatabase(authenticated_browser["path"]) as db:
            db.conn.execute("UPDATE mmfdb_session SET expires_at = '2000-01-01T00:00:00'")
            db.conn.commit()
    host, path, notices = import_host
    assert host.onImportProject() is False
    assert notices and notices[-1][0] == "warning"
    with MFDatabase(authenticated_browser["path"]) as db:
        assert (
            db.conn.execute(
                "SELECT count(*) FROM mmfdb_operation WHERE operation_type = 'project'"
            ).fetchone()[0]
            == 0
        )
        assert db.conn.execute("SELECT count(*) FROM mmfdb_session").fetchone()[0] == 1


@pytest.mark.parametrize("cancel_at", ["chooser", "confirmation"])
def test_main_import_cancellation_preserves_document(
    authenticated_browser, import_host, monkeypatch, cancel_at
):
    """Cancel before publication leaves the real database and current science untouched."""
    host, path, notices = import_host
    if cancel_at == "chooser":
        monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    else:
        monkeypatch.setattr(
            "chisurf.gui.main_helper.dialogs.question", lambda *a: QtWidgets.QMessageBox.No
        )
    assert host.onImportProject() is False
    assert notices == []
    assert authenticated_browser["client"].list_projects() == []


def test_main_import_actual_collision_dialog_cancel_preserves_remote_versions(
    authenticated_browser,
    import_host,
    sample_project_payload,
    monkeypatch,
):
    """Cancel the real rendered collision dialog after authenticated HTTP preview."""
    from chisurf.core.project.pto import read_project
    from chisurf.plugins.core.project_browser.gui.tool import CollisionDialog

    client = authenticated_browser["client"]
    saved = client.save_project("Collision source", project_payload=sample_project_payload)
    assert saved["ok"] is True
    exported_path = authenticated_browser["tmp_path"] / "existing-export.cs.pto"
    exported = client.export_csp(saved["version_id"], target_path=str(exported_path))
    assert exported["ok"] is True and exported["version_id"] == saved["version_id"]
    assert read_project(exported_path)[0] == sample_project_payload
    expected_bytes = exported_path.read_bytes()
    preview = client.import_preview(file_path=str(exported_path))
    assert preview["ok"] is True and preview["has_collisions"] is True
    assert any(preview["collisions"].values())
    before_versions = client.list_projects()
    host, path, notices = import_host
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: (str(exported_path), "")
    )
    observations = []
    capture = authenticated_browser["tmp_path"] / "actual-import-collision-cancel.png"

    def press_actual_cancel():
        """Drive only the real modal dialog's cancel button, retaining a render."""
        dialog = next(
            (
                widget
                for widget in QtWidgets.QApplication.topLevelWidgets()
                if isinstance(widget, CollisionDialog)
            ),
            None,
        )
        if dialog is None:
            observations.append({"error": "The actual CollisionDialog was not shown"})
            return
        buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
        observations.append(
            {
                "visible": dialog.isVisible(),
                "title": dialog.windowTitle(),
                "text": dialog.findChild(QtWidgets.QTextEdit).toPlainText(),
                "captured": dialog.grab().save(str(capture)),
                "cancel_text": buttons.button(QtWidgets.QDialogButtonBox.Cancel).text(),
            }
        )
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).click()

    QtCore.QTimer.singleShot(0, press_actual_cancel)
    assert host.onImportProject() is False
    assert len(observations) == 1
    assert observations[0]["visible"] and observations[0]["captured"]
    assert observations[0]["title"] == "Import — Collision Warning"
    for category, identifiers in preview["collisions"].items():
        if identifiers:
            assert f"{category} ({len(identifiers)}):" in observations[0]["text"]
            assert all(identifier in observations[0]["text"] for identifier in identifiers[:20])
    assert notices == []
    assert exported_path.read_bytes() == expected_bytes
    assert client.list_projects() == before_versions


@pytest.mark.parametrize("field", ["version_id", "project_id", "version_number", "project_payload"])
def test_main_import_rejects_readback_corruption_after_actual_http(
    authenticated_browser,
    import_host,
    monkeypatch,
    field,
):
    """Fault-inject only the reply of a completed real authenticated readback."""
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    restore = ProjectBrowserClient.restore_project
    calls = []

    def damaged_reply(self, version_id):
        result = restore(self, version_id)
        assert result["ok"] is True
        assert self.token == authenticated_browser["token"]
        calls.append(version_id)
        result[field] = 999 if field == "version_number" else "wrong-reply"
        return result

    monkeypatch.setattr(ProjectBrowserClient, "restore_project", damaged_reply)
    host, path, notices = import_host
    assert host.onImportProject() is False
    assert calls
    assert notices[-1][0] == "warning"


def test_main_file_import_without_any_mmfdb_import(tmp_path):
    """Run actual Main and the guarded file path in a fresh MMFDB-blocked interpreter."""
    script = textwrap.dedent(r"""
        import importlib.abc
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB blocked", name=fullname)
        sys.meta_path.insert(0, NoMMFDB())
        import numpy as np
        import chisurf as cs
        import chisurf.gui as gui
        from chisurf.core.project import capture_session
        from chisurf.core.project.pto import write_project
        from chisurf.core.experiments.tcspc import TCSPCReader
        from chisurf.gui.main import Main
        application = gui.QtWidgets.QApplication.instance() or gui.QtWidgets.QApplication([])
        cs.console = gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None
        main = Main()
        main._save_window_state = lambda: None
        cs.cs = main
        main.init_setups()
        main.define_actions()
        main.arrange_widgets()
        main.resize(1500, 950)
        main.show()
        reader = TCSPCReader(dt=.048, rep_rate=80., skiprows=9, use_header=False,
                             rebin=(1, 1), record_provenance=False)
        curve = reader.get_data(filename="test/data/tcspc/ibh_sample/Decay_577D.txt")[0]
        curve.unique_identifier = "portable-import-measured"
        payload = capture_session([curve], [], name="Portable imported science")
        destination = Path(sys.argv[1]) / "native.cs.pto"
        write_project(destination, payload.to_dict())
        gui.QtWidgets.QFileDialog.getOpenFileName = lambda *a, **k: (str(destination), "")
        gui.dialogs.choice = lambda *a, **k: SimpleNamespace(key="discard")
        warnings = []
        gui.dialogs.warning = lambda *a: warnings.append(a)
        assert main.onImportProject() is True, warnings
        restored = next(
            d for d in cs.imported_datasets if d.unique_identifier == curve.unique_identifier
        )
        np.testing.assert_array_equal(restored.y, curve.y)
        assert type(restored.data_reader) is TCSPCReader
        assert main._get_project_document().path == destination
        main.dataset_selector.update()
        application.processEvents()
        main.dockWidgetDatasets.raise_()
        application.processEvents()
        assert main.grab().save(str(Path(sys.argv[1]) / "mmfdb-blocked-import-main.png"))
        old_document = main._get_project_document().clone()
        old_identity = (
            main._current_project_id, main._current_project_version_id,
            main._current_project_path, main._current_project_name,
        )
        old_file = destination.read_bytes()
        main._guard_project_transition = lambda: False
        assert main.onImportProject() is False
        assert cs.imported_datasets[0] is restored
        assert main._get_project_document() == old_document
        assert (
            main._current_project_id, main._current_project_version_id,
            main._current_project_path, main._current_project_name,
        ) == old_identity
        assert destination.read_bytes() == old_file
        assert main.isVisible()
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        main._guard_project_transition = lambda: True
        main.close()
        application.processEvents()
        print("Actual Main portable import/cancellation with all MMFDB imports blocked verified")
    """)
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )
    (tmp_path / "mmfdb-blocked-import.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
