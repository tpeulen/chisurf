"""The shared detector row launches full native reference calibration without altering preview data."""
from __future__ import annotations

import copy

import pytest

from test.native_emtk.test_channel_definition_json import editor as editor_fixture

editor = editor_fixture


def test_calc_g_row_opens_an_independent_reference_chooser_without_mutating(editor):
    app, ui, notices, _ = editor
    before = copy.deepcopy(app.model.data)
    ui.draw(2)
    cells = app.page._detector_buttons.cells()
    rectangle = next(box for _, row, key, box in cells if row == 0 and key == "calc")
    ui.click(rectangle)
    assert app.page.dialog is not None
    assert app.page.action == "reference_calibration"
    assert app.model.data == before and not notices


def open_real_reference(app, ui, tmp_path):
    """Click the actual row action, native file entry and Open button; wait for its real reader."""
    import shutil
    import time
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "data/tttr/BH/132/BH_SPC132.spc"
    target = tmp_path / "reference.spc"
    shutil.copy2(source, target)
    detector = app.model.data["detectors"]["donor"]
    detector["chs"] = [8, 0, 3]
    detector["g_factor_channels"] = [850, 1850]
    ui.draw(2)
    cells = app.page._detector_buttons.cells()
    ui.click(next(box for _, row, key, box in cells if row == 0 and key == "calc"))
    assert app.page.action == "reference_calibration" and app.page.dialog is not None
    app.page.dialog.directory = str(tmp_path)
    ui.draw(2)
    ui.click("reference.spc")
    ui.click("Open")
    deadline = time.monotonic() + 20
    while app.page._reference_future is not None and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    ui.draw(2)
    assert app.page.reference_prompt.open, app.page.status
    return target


def test_full_native_child_pointer_apply_and_once_publication(editor, tmp_path, monkeypatch):
    app, ui, notices, _ = editor
    import time

    import numpy as np

    from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    archived: list[dict] = []
    def archive(self, **kwargs):
        archived.append(kwargs)
        return {"ok": True, "reference_decay_id": "new-reference-id", "calibration_id": "new-calibration-id"}
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", archive)
    original_preview = app.model.preview
    original_reading = copy.deepcopy(app.model.data["tttr_reading"])
    source = open_real_reference(app, ui, tmp_path)
    assert not notices and app.model.preview is original_preview
    assert app.model.data["tttr_reading"] == original_reading
    ui.click("calibration_interactive")
    child = app.page.reference_app
    assert child is not None
    ui.draw(3)
    expected = calculate_g_factor_core(child.model.fast[0], child.model.fast[1], child.model.region)
    assert child.model.g_factor == expected["g_factor"]
    assert child.model.fp_dt_ns == app.page._reference_context["timing"] * 1e-3
    ui.click("reference.manual_l")
    deadline = time.monotonic() + 10
    while child.job.running and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    assert child.model.manual_l and child.model.l_override == 0.0, {"manual_rect": app.item_rects.get("reference.manual_l"), "window": app.page.reference_window.content_box, "parent_pointer": app.io.mouse_pos, "child_pointer": child.io.mouse_pos, "job_running": child.job.running}
    ui.click("calibration_apply")
    ui.draw(4)
    child.close()
    assert app.page.reference_app is None
    assert len(archived) == len(notices) == 1
    parameters = archived[0]["parameters"]
    assert parameters["l1"] == parameters["l2"] == 0.0
    assert parameters["g_factor_stddev"] == expected["g_factor_stddev_uncorrected"]
    assert parameters["source_measurement"] == str(source)
    detector = app.model.data["detectors"]["donor"]
    assert detector["g_factor_calibration_id"] == "new-calibration-id"
    assert detector["g_factor_decay_uuid"] == "new-reference-id"
    assert detector["g_factor_channels"] == [850, 1850]
    assert detector["future_detector_metadata"] == {"untouched": [1, 2]}
    assert np.array_equal(app.model.preview[0], original_preview[0])


def test_headless_archive_failure_and_cancel_leave_all_previous_calibration(editor, tmp_path, monkeypatch):
    app, ui, notices, path = editor
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    def failed(self, **kwargs):
        return {"ok": False, "error": "controlled archive failure"}
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", failed)
    open_real_reference(app, ui, tmp_path)
    previous = copy.deepcopy(app.model.data)
    original_file = path.read_bytes()
    ui.click("calibration_headless")
    assert "controlled archive failure" in app.page.status
    assert app.model.data == previous and not notices
    assert path.read_bytes() == original_file
    open_real_reference(app, ui, tmp_path)
    ui.click("calibration_interactive")
    ui.click("calibration_cancel")
    assert app.page.reference_app is None
    assert app.model.data == previous and not notices


def test_reloaded_fast_reference_requires_a_new_tttr_context(editor, tmp_path, monkeypatch):
    """The full child can reload a DAT, but cannot attach the old TTTR provenance to it."""
    import time

    import numpy as np

    from chisurf.core.fio import write_vv_vh
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    app, ui, notices, _ = editor
    calls = []
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", lambda *a, **kw: calls.append(kw))
    open_real_reference(app, ui, tmp_path)
    before = copy.deepcopy(app.model.data)
    ui.click("calibration_interactive")
    child = app.page.reference_app
    replacement = tmp_path / "replacement.dat"
    decay = np.exp(-np.arange(100) / 20) * 1000
    write_vv_vh(str(replacement), vv=decay, vh=decay / 1.3)
    ui.click("reference.load_fast")
    child.dialog.directory = str(tmp_path)
    ui.draw(2)
    ui.click("replacement.dat")
    ui.click("Open")
    deadline = time.monotonic() + 10
    while child.job.running and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    ui.click("calibration_apply")
    ui.draw(3)
    assert "fast reference changed" in app.page.status.lower()
    assert not calls and app.model.data == before and not notices


@pytest.mark.parametrize("changed", ["readonly", "routing", "definition"])
def test_publication_rejects_changed_capture_context(editor, tmp_path, monkeypatch, changed):
    app, ui, notices, _ = editor
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    calls = []
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", lambda *a, **kw: calls.append(kw))
    open_real_reference(app, ui, tmp_path)
    if changed == "readonly":
        app.page.read_only = True
    elif changed == "routing":
        app.model.data["detectors"]["donor"]["chs"] = [0, 1]
    else:
        app.page.load_definition(app.model.get_settings())
    before, notices_before = copy.deepcopy(app.model.data), len(notices)
    # A queued publication callback still obeys the captured context/read-only boundary.
    app.page._publish_reference(app.page._reference_model)
    assert not calls and app.model.data == before and len(notices) == notices_before
    app.page.calibration_cancel()


def test_parent_drop_is_captured_by_child_without_replacing_parent(editor, tmp_path):
    import time

    import numpy as np

    from chisurf.core.fio import write_vv_vh

    app, ui, notices, _ = editor
    original_instance_hooks = {name: app.__dict__.get(name) for name in ("files_dropped", "on_files_dropped", "on_paths_dropped")}
    open_real_reference(app, ui, tmp_path)
    before = copy.deepcopy(app.model.data)
    ui.click("calibration_interactive")
    replacement = tmp_path / "dropped.dat"
    values = np.exp(-np.arange(100) / 20) * 1000
    write_vv_vh(str(replacement), vv=values, vh=values / 1.4)
    assert ui.surface.on_files_dropped([str(replacement)])
    child = app.page.reference_app
    deadline = time.monotonic() + 10
    while child.job.running and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    assert child.model.fast_file == str(replacement)
    assert app.model.data == before and not notices
    ui.click("calibration_cancel")
    assert {name: app.__dict__.get(name) for name in original_instance_hooks} == original_instance_hooks


def test_closed_parent_cleans_late_preparation_and_never_requests_a_frame(editor, tmp_path, monkeypatch):
    """Close after real preparation but before future delivery; its scratch resource must disappear."""
    import shutil
    from pathlib import Path
    from threading import Event

    app, ui, notices, _ = editor
    source = Path(__file__).resolve().parents[1] / "data/tttr/BH/132/BH_SPC132.spc"
    target = tmp_path / "late.spc"
    shutil.copy2(source, target)
    app.model.data["detectors"]["donor"].update(chs=[8, 0, 3], g_factor_channels=[850, 1850])
    app.page._reference_context = {"name": "donor", "channels": [8, 0, 3], "definition": app.model.data, "setup_name": app.model.current_name}
    original = app.page._prepare_reference
    ready, release = Event(), Event()
    resources = []
    def delayed(*args):
        result = original(*args)
        resources.append(Path(result[1].name))
        ready.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(app.page, "_prepare_reference", delayed)
    frames = []
    monkeypatch.setattr(app, "request_frame", lambda: frames.append(app.page._closing))
    before = copy.deepcopy(app.model.data)
    app.page._read_reference(str(target))
    future = app.page._reference_future
    assert ready.wait(10)
    app.close()
    release.set()
    future.result(timeout=10)
    # The future's actual completion callbacks dispose the late result without poll().
    import time
    deadline = time.monotonic() + 5
    while resources[0].exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not resources[0].exists()
    assert app.page._reference_future is None and not notices
    assert app.model.data == before and not any(frames)


def reveal_reference(ui, page, name):
    """Reach a lower child control with actual wheel events within its clipped control pane."""
    for _ in range(12):
        ui.draw(1)
        rectangle = ui.rect("reference." + name)
        box = page.reference_window.content_box
        x, y, width, height = rectangle
        if box[1] <= y and y + height < box[1] + box[3] - 8:
            return rectangle
        ui.wheel(-4 if y > box[1] else 4, at=(x + min(width / 2, 20), box[1] + box[3] - 40))
    raise AssertionError((name, rectangle, box))


def test_pending_keyboard_mixing_applies_after_compute_and_nested_help_guide_batch_are_reachable(editor, tmp_path, monkeypatch):
    import time

    from emtk.events import CONTROL_MODIFIER

    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    app, ui, notices, _ = editor
    records = []
    def archive(self, **kwargs):
        records.append(kwargs)
        return {"ok": True, "reference_decay_id": "pending-reference", "calibration_id": "pending-calibration"}
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", archive)
    open_real_reference(app, ui, tmp_path)
    ui.click("calibration_interactive")
    child = app.page.reference_app
    ui.draw(3)
    ui.click("reference.help")
    assert child.help.open
    # Escape closes the nested help, not the full calibration/parent.
    ui.hover((child.help.dlg.box[0] + 20 + app.page.reference_window.content_box[0],
              child.help.dlg.box[1] + 40 + app.page.reference_window.content_box[1]))
    ui.escape()
    assert not child.help.open and app.page.reference_app is child and not records
    ui.click("reference.guide")
    assert child.guide.active
    ui.escape()
    # Use the tour's real close caption so it does not cover editing controls.
    if child.guide.active:
        close_text = next(entry[:4] for entry in reversed(ui.painter.texts) if entry[5] in {"Close", "×"})
        ui.click(close_text)
    assert app.page.reference_app is child and not records
    ui.click("Batch anisotropy")
    assert "reference.batch_files.add" in ui.ids()
    ui.click("G-factor and mixing")
    ui.click(reveal_reference(ui, app.page, "manual_l"))
    deadline = time.monotonic() + 10
    while child.job.running and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    ui.click(reveal_reference(ui, app.page, "l_override"))
    ui.key(0x41, "a", CONTROL_MODIFIER)
    ui.type("0.12")
    assert child.model.l_override == 0.0  # actual edit is still pending, not pre-mutated
    ui.click("calibration_apply")
    deadline = time.monotonic() + 10
    while app.page.reference_app is not None and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    assert app.page.reference_app is None, {"apply": app.page._reference_apply_requested, "guide": child.guide.active, "running": child.job.running, "mixing": child.model.l_override, "buffers": child.forms["controls"].buffers if "controls" in child.forms else {key: value.buffers for key, value in child.forms.items()}, "footer": ui.rect("calibration_apply"), "window": app.page.reference_window.content_box}
    assert len(records) == len(notices) == 1
    assert records[0]["parameters"]["l1"] == records[0]["parameters"]["l2"] == 0.12


def test_real_headless_archive_persists_actor_uuid_sd_and_lineage(editor, tmp_path, monkeypatch):
    """Exercise the canonical client/service/registry against a fresh actual scratch database."""
    import json
    import sqlite3
    from uuid import UUID

    from mmfdb.provenance.result_registry import read_result
    from mmfdb.repository import MFDatabase
    from mmfdb.schema import schema

    app, ui, notices, path = editor
    database, objects = tmp_path / "archive.sqlite", tmp_path / "objects"
    objects.mkdir()
    with sqlite3.connect(database) as connection:
        schema.migrate_schema(connection)
    monkeypatch.setattr("mmfdb.store.database_resolver.resolve_database_path", lambda: database)
    monkeypatch.setattr("mmfdb.store.database_resolver.object_store_root", lambda: objects)
    open_real_reference(app, ui, tmp_path)
    expected_sd = app.page._reference_model.result["g_factor_stddev_uncorrected"]
    ui.click("calibration_headless")
    assert "archived" in app.page.status, app.page.status
    assert len(notices) == 1
    detector = app.model.data["detectors"]["donor"]
    source_id, calibration_id = detector["g_factor_decay_uuid"], detector["g_factor_calibration_id"]
    assert UUID(source_id) != UUID(calibration_id)
    assert detector["l1"] == 0.05 and detector["l2"] == 0.02
    assert json.loads(path.read_text())["setups"]["Validation"]["detectors"]["donor"] == detector
    with MFDatabase(str(database)) as db:
        source, calibration = db.get_artifact(source_id), db.get_artifact(calibration_id)
        assert source["created_by_user_id"] == calibration["created_by_user_id"] == "validation-owner"
        assert json.loads(source["metadata_json"])["active_user"] == "validation-owner"
        payload = read_result(db, calibration_id)
        assert payload is not None and payload.data["g_factor_stddev"][0] == expected_sd
        assert payload.data["l1"][0] == 0.05 and payload.data["l2"][0] == 0.02
        edge = db.conn.execute("SELECT relationship_type FROM mmfdb_edge WHERE source_node_id=? AND target_node_id=?", (calibration_id, source_id)).fetchone()
        assert edge is not None and edge[0] == "derived_from"
        actors = {row[0] for row in db.conn.execute("SELECT created_by_user_id FROM mmfdb_artifact WHERE deleted_at IS NULL")}
        assert actors == {"validation-owner"}
