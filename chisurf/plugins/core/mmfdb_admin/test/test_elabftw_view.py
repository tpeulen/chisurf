"""Headless behavior contracts for the MMFDB Admin eLabFTW panel."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class FakeClient:
    """Record all MMFDB client calls made by the eLabFTW panel."""

    def __init__(self):
        """Initialize call recordings."""
        self.connected = []
        self.disconnected = []
        self.imported = []
        self.exported = []

    def connect_elabftw(self, base_url, api_key, **kwargs):
        self.connected.append((base_url, api_key, kwargs))
        return {
            "connection_id": "opaque-handle",
            "endpoint": "https://lab.example/api/v2",
            "info": {"version": "5.2.0"},
        }

    def disconnect_elabftw(self, connection_id):
        self.disconnected.append(connection_id)

    def list_elabftw_experiments(self, connection_id, **kwargs):
        assert connection_id == "opaque-handle"
        return [
            {
                "id": 7,
                "title": "Lifetime series",
                "date": "2026-07-13",
                "status": "Complete",
                "modified_at": "2026-07-13 12:00:00",
                "tags": ["tcspc", "fret"],
            }
        ]

    def import_elabftw_experiments(self, connection_id, remote_ids, **kwargs):
        self.imported.append((connection_id, remote_ids, kwargs))
        return {
            "imported": [{"remote_id": item} for item in remote_ids],
            "updated": [],
            "skipped": [],
        }

    def list_experiments(self):
        return [{"experiment_id": "local-1", "status": "complete"}]

    def export_elabftw_experiment(self, connection_id, experiment_id, **kwargs):
        self.exported.append((connection_id, experiment_id, kwargs))
        return {"remote_id": kwargs.get("remote_id") or 91, "mode": kwargs["mode"]}


def _immediate_submit(fn, success, failure):
    try:
        success(fn())
    except Exception as exc:  # pragma: no cover - exercised by error test
        failure(str(exc))


def test_key_is_masked_never_persisted_and_cleared_after_connect(qapp):
    from qtpy import QtWidgets

    from chisurf.plugins.core.mmfdb_admin.gui.elabftw_view import ELabFTWView

    client = FakeClient()
    view = ELabFTWView(client, submit=_immediate_submit)
    assert view.api_key_edit.echoMode() == QtWidgets.QLineEdit.Password
    view.endpoint_edit.setText("https://lab.example")
    view.api_key_edit.setText("secret-key")

    view.connect_remote()

    assert view.api_key_edit.text() == ""
    assert view.connection_id == "opaque-handle"
    assert client.connected[0][1] == "secret-key"
    assert "secret-key" not in view.status_label.text()
    assert view.remote_table.rowCount() == 1


def test_busy_state_disables_remote_mutations(qapp):
    from chisurf.plugins.core.mmfdb_admin.gui.elabftw_view import ELabFTWView

    view = ELabFTWView(FakeClient(), submit=_immediate_submit)
    view.connection_id = "opaque-handle"
    view._set_busy(True)
    assert not view.connect_button.isEnabled()
    assert not view.refresh_button.isEnabled()
    assert not view.import_button.isEnabled()
    assert not view.export_button.isEnabled()
    view._set_busy(False)
    assert view.refresh_button.isEnabled()
    assert view.import_button.isEnabled()


def test_selected_import_and_explicit_export_modes(qapp):
    from qtpy import QtCore

    from chisurf.plugins.core.mmfdb_admin.gui.elabftw_view import ELabFTWView

    client = FakeClient()
    view = ELabFTWView(client, submit=_immediate_submit)
    view.endpoint_edit.setText("https://lab.example")
    view.api_key_edit.setText("secret-key")
    view.connect_remote()
    view.remote_table.item(0, 0).setCheckState(QtCore.Qt.Checked)
    view.conflict_combo.setCurrentText("update")
    view.sample_id_edit.setText("sample-1")

    view.import_selected()

    assert client.imported == [
        (
            "opaque-handle",
            [7],
            {"conflict": "update", "sample_id": "sample-1"},
        )
    ]
    view.local_experiment_combo.setCurrentText("local-1")
    view.export_mode_combo.setCurrentText("create")
    view.export_selected()
    view.export_mode_combo.setCurrentText("update")
    view.remote_id_spin.setValue(91)
    view.export_selected()
    assert client.exported == [
        ("opaque-handle", "local-1", {"mode": "create", "remote_id": None}),
        ("opaque-handle", "local-1", {"mode": "update", "remote_id": 91}),
    ]


def test_disconnect_discards_handle_and_remote_rows(qapp):
    from chisurf.plugins.core.mmfdb_admin.gui.elabftw_view import ELabFTWView

    client = FakeClient()
    view = ELabFTWView(client, submit=_immediate_submit)
    view.endpoint_edit.setText("https://lab.example")
    view.api_key_edit.setText("secret-key")
    view.connect_remote()

    view.disconnect_remote()

    assert client.disconnected == ["opaque-handle"]
    assert view.connection_id is None
    assert view.remote_table.rowCount() == 0


def test_error_path_is_non_modal_and_does_not_echo_key(qapp):
    from chisurf.plugins.core.mmfdb_admin.gui.elabftw_view import ELabFTWView

    class FailingClient(FakeClient):
        def connect_elabftw(self, base_url, api_key, **kwargs):
            raise RuntimeError("authentication rejected")

    view = ELabFTWView(FailingClient(), submit=_immediate_submit)
    view.endpoint_edit.setText("https://lab.example")
    view.api_key_edit.setText("super-secret")
    view.connect_remote()
    assert view.connection_id is None
    assert "authentication rejected" in view.status_label.text()
    assert "super-secret" not in view.status_label.text()
    assert view.api_key_edit.text() == ""
