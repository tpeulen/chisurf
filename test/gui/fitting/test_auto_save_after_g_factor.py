"""Actual native reference actions archive and auto-save only the active owned setup."""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from mmfdb.provenance.result_registry import read_result
from mmfdb.repository import MFDatabase
from mmfdb.schema import schema

from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient
from test.gui.test_cell_text_editing import cell_rect, double_click
from test.native_emtk.test_channel_definition_json import editor as editor
from test.native_emtk.test_channel_definition_reference import open_real_reference, reveal_reference


@pytest.fixture
def calibration(editor: Any, tmp_path: Any, monkeypatch: Any) -> Iterator[dict[str, Any]]:
    """Use real measured input, actual client/service/registry and scratch named/SQL stores."""
    app, ui, notices, path = editor
    database, objects = tmp_path / "archive.sqlite", tmp_path / "objects"
    objects.mkdir(exist_ok=True)
    with sqlite3.connect(database) as connection:
        schema.migrate_schema(connection)
    monkeypatch.setattr("mmfdb.store.database_resolver.resolve_database_path", lambda: database)
    monkeypatch.setattr("mmfdb.store.database_resolver.object_store_root", lambda: objects)
    donor = app.model.data["detectors"]["donor"]
    donor.update(chs=[8, 0, 3], g_factor_channels=[850, 1850])
    app.model.data["detectors"]["other"] = {
        "chs": [7],
        "micro_time_ranges": [[0, 32]],
        "g_factor": 2.5,
        "future_metadata": {"neighbour": "preserved"},
    }
    saved = copy.deepcopy(app.model.get_settings())
    saved["stored_metadata"] = {"hidden": "preserved"}
    app.model.setups["Validation"] = saved
    path.write_text(json.dumps({"setups": app.model.setups, "last_used": "Validation"}))
    calls: list[dict] = []
    original = VvVhGFactorClient.archive_g_factor

    def tracked(self: Any, **kwargs: Any) -> Any:
        calls.append(copy.deepcopy(kwargs))
        return original(self, **kwargs)

    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", tracked)
    ui.draw(2)
    yield {
        "app": app,
        "ui": ui,
        "notices": notices,
        "path": path,
        "database": database,
        "calls": calls,
        "original_bytes": path.read_bytes(),
        "original_data": copy.deepcopy(app.model.data),
    }


def settle_child(child: Any, ui: Any) -> None:
    """Await the real bounded native calculator job before inspecting its result."""
    deadline = time.monotonic() + 10
    while child.job.running and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    assert not child.job.running
    ui.draw(2)


def assert_publication(
    context: dict[str, Any],
    reference: Any,
    timing: float,
    source: Any,
    *,
    mixing: tuple[float, float] = (0.05, 0.02),
) -> None:
    """Assert actual scientific payload, named metadata, archive SQL and lineage together."""
    app, path = context["app"], context["path"]
    assert len(context["calls"]) == len(context["notices"]) == 1
    call = context["calls"][0]
    parameters = call["parameters"]
    assert call["active_user"] == "validation-owner"
    assert parameters["micro_time_resolution"] == timing
    assert reference.fp_dt_ns == pytest.approx(timing * 1e-3)
    assert parameters["source_measurement"] == str(source)
    assert parameters["g_factor"] == reference.g_factor
    assert (parameters["l1"], parameters["l2"]) == mixing
    expected_sd = reference.detector_parameters(micro_time_resolution=timing)["g_factor_stddev"]
    assert parameters["g_factor_stddev"] == expected_sd
    detector = app.model.data["detectors"]["donor"]
    assert detector["g_factor"] == reference.g_factor
    assert detector["g_factor_channels"] == [850, 1850]
    assert (detector["l1"], detector["l2"]) == mixing
    assert detector["future_detector_metadata"] == {"untouched": [1, 2]}
    source_id, calibration_id = detector["g_factor_decay_uuid"], detector["g_factor_calibration_id"]
    assert UUID(source_id) != UUID(calibration_id)
    stored = json.loads(path.read_text())
    assert stored["last_used"] == "Validation"
    named = stored["setups"]["Validation"]
    assert named["stored_metadata"] == {"hidden": "preserved"}
    assert named["detectors"] == app.model.get_settings()["detectors"]
    assert named["detectors"]["other"] == context["original_data"]["detectors"]["other"]
    with MFDatabase(str(context["database"])) as db:
        raw, artifact = db.get_artifact(source_id), db.get_artifact(calibration_id)
        assert raw["created_by_user_id"] == artifact["created_by_user_id"] == "validation-owner"
        metadata = json.loads(raw["metadata_json"])
        assert metadata["active_user"] == "validation-owner"
        assert metadata["micro_time_resolution"] == timing
        assert metadata["calibration_parameters"] == parameters
        payload = read_result(db, calibration_id)
        assert payload is not None
        assert payload.data["g_factor_stddev"][0] == expected_sd
        assert (payload.data["l1"][0], payload.data["l2"][0]) == mixing
        edge = db.conn.execute(
            "SELECT relationship_type FROM mmfdb_edge WHERE source_node_id=? AND target_node_id=?",
            (calibration_id, source_id),
        ).fetchone()
        assert edge is not None and edge[0] == "derived_from"
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 3
        assert {
            row[0] for row in db.conn.execute("SELECT operator_user_id FROM mmfdb_operation")
        } == {"validation-owner"}


@pytest.mark.parametrize("manual_zero", [False, True])
def test_actual_native_apply_persists_once_with_sd_ids_actor_and_mixing(
    calibration: dict[str, Any],
    tmp_path: Any,
    manual_zero: bool,
) -> None:
    """The actual calculator Apply/close publishes once and saves the owned named setup."""
    app, ui = calibration["app"], calibration["ui"]
    preview, reading = app.model.preview, copy.deepcopy(app.model.get_settings()["tttr_reading"])
    source = open_real_reference(app, ui, tmp_path)
    ui.click("calibration_interactive")
    child = app.page.reference_app
    assert child is not None
    settle_child(child, ui)
    if manual_zero:
        # c27f562eb: the mixing controls are rows of the parameters table now; the
        # manual override is the Fixed toggle on the l1 row.
        l1_row = next(r for r in child.model.parameter_rows() if r["key"] == "l1")
        child.model.edit_parameter(l1_row, "fixed", True)
        settle_child(child, ui)
        assert child.model.manual_l and child.model.l1_override == 0.0
    reference, timing = child.model, app.page._reference_context["timing"]
    ui.click("calibration_apply")
    ui.draw(4)
    child.close()
    child.close()
    assert app.page.reference_app is None
    assert_publication(
        calibration, reference, timing, source, mixing=(0.0, 0.0) if manual_zero else (0.05, 0.02)
    )
    assert app.model.preview is preview
    assert app.model.get_settings()["tttr_reading"] == reading


@pytest.mark.parametrize("headless", [False, True])
@pytest.mark.parametrize("archive_ok", [False, True])
def test_real_reference_action_effective_timing_success_and_archive_failure(
    calibration: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
    headless: bool,
    archive_ok: bool,
) -> None:
    """Both real actions use the same measured result; a failed transport leaves all stores intact."""
    app, ui = calibration["app"], calibration["ui"]
    if not archive_ok:

        def failed(self: Any, **kwargs: Any) -> Any:
            calibration["calls"].append(copy.deepcopy(kwargs))
            raise OSError("controlled archive failure")

        monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", failed)
    source = open_real_reference(app, ui, tmp_path)
    reference, timing = app.page._reference_model, app.page._reference_context["timing"]
    if headless:
        ui.click("calibration_headless")
    else:
        ui.click("calibration_interactive")
        child = app.page.reference_app
        settle_child(child, ui)
        child.close()
        ui.draw(3)
        child.close()
    if archive_ok:
        assert_publication(calibration, reference, timing, source)
    else:
        assert len(calibration["calls"]) == 1
        assert "controlled archive failure" in app.page.status
        assert not calibration["notices"]
        assert app.model.data == calibration["original_data"]
        assert calibration["path"].read_bytes() == calibration["original_bytes"]


def test_queued_publication_obeys_readonly_after_preparation(
    calibration: dict[str, Any],
    tmp_path: Any,
) -> None:
    """A real pending native result cannot bypass read-only when its callback arrives late."""
    app, ui = calibration["app"], calibration["ui"]
    open_real_reference(app, ui, tmp_path)
    app.page.read_only = True
    app.page._publish_reference(app.page._reference_model)
    assert not calibration["calls"] and not calibration["notices"]
    assert app.model.data == calibration["original_data"]
    assert calibration["path"].read_bytes() == calibration["original_bytes"]
    app.page.calibration_cancel()


def test_nonowner_reference_updates_working_definition_without_autosaving_named_store(
    calibration: dict[str, Any],
    tmp_path: Any,
) -> None:
    """An archived working result never rewrites another actor's named setup."""
    app, ui = calibration["app"], calibration["ui"]
    app.model.setups["Validation"]["_owner"] = "another-owner"
    stored = json.loads(calibration["path"].read_text())
    stored["setups"]["Validation"]["_owner"] = "another-owner"
    calibration["path"].write_text(json.dumps(stored))
    original_bytes = calibration["path"].read_bytes()
    source = open_real_reference(app, ui, tmp_path)
    reference = app.page._reference_model
    ui.click("calibration_headless")
    assert len(calibration["calls"]) == len(calibration["notices"]) == 1
    assert calibration["calls"][0]["parameters"]["source_measurement"] == str(source)
    assert app.model.data["detectors"]["donor"]["g_factor"] == reference.g_factor
    assert app.model.data["detectors"]["donor"]["g_factor_calibration_id"]
    assert calibration["path"].read_bytes() == original_bytes


@pytest.mark.parametrize("state", ["readonly", "disabled", "cancelled"])
def test_unavailable_or_cancelled_native_controls_do_not_publish(
    calibration: dict[str, Any],
    tmp_path: Any,
    state: str,
) -> None:
    """Read-only, parent editing during a child calibration, and chooser Cancel preserve state."""
    app, ui = calibration["app"], calibration["ui"]
    if state == "disabled":
        open_real_reference(app, ui, tmp_path)
        ui.click("calibration_interactive")
        assert app.page.reference_app is not None and not app.page.enabled("edit_json")
        # The actual parent table is still drawn but disabled while its child owns input.
        double_click(ui, cell_rect(app.page, ui, 0, "g"))
        assert app.page._detector_table.control.editing is None
        ui.type("9.999")
        ui.click("calibration_cancel")
    else:
        if state == "readonly":
            app.page.read_only = True
        ui.draw(2)
        rectangle = next(
            box
            for _, row, key, box in app.page._detector_buttons.cells()
            if row == 0 and key == "calc"
        )
        ui.click(rectangle)
        if state == "cancelled":
            assert app.page.dialog is not None
            ui.click("Cancel")
        assert app.page.dialog is None and app.page._reference_future is None
    assert not calibration["calls"] and not calibration["notices"]
    assert app.model.data == calibration["original_data"]
    assert calibration["path"].read_bytes() == calibration["original_bytes"]
