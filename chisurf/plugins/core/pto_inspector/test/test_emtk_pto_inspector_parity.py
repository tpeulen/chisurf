"""The native PTO inspector against the Qt tool: rows, details, payloads, actions, errors, drawing, no Qt.

Hermetic: the settings folder and the containers live in temporary folders (the container is built
from a private copy of ``test/data/clsm/Leica_SP5.ptu`` by the plugin's own fixture); nothing reads or
writes ``~/.chisurf``, and no network is used (the MMFDB picker is stubbed).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.pto_inspector.core import PtoInspection
from chisurf.plugins.core.pto_inspector.gui.app import PtoInspectorApp, make_app
from chisurf.plugins.core.pto_inspector.gui.view_model import PtoInspectorViewModel
from chisurf.plugins.core.pto_inspector.test.test_core import PTU
from chisurf.plugins.core.pto_inspector.test.test_core import container as _fixture

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="instrument test data missing")


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


@pytest.fixture(scope="module")
def shared_container(tmp_path_factory):
    """One container (README, instrument file, bursts, background, lifetimes, fcs) for the module."""
    return _fixture.__wrapped__(tmp_path_factory.mktemp("pto"))


@pytest.fixture
def container(shared_container, tmp_path):
    """A private copy, for tests that write or damage it."""
    target = tmp_path / "copy.pto"
    shutil.copy(shared_container, target)
    return target


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def uid_of(model, name):
    return next(i.uid for i in model.inspection.infos() if i.name == name)


@pytest.fixture
def app(shared_container):
    a = make_app()
    a.model.set_filename(str(shared_container))
    yield a
    a.close()


# ── 1. numbers equal the container's and the Qt tool's ──────────────────


def test_rows_equal_the_container_and_the_qt_table(qapp, shared_container, app):
    from chisurf.gui.widgets.chitable import ChiTableWidget
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    # the container as the library reads it (not through the view model)
    with Measurement.open(shared_container, writable=False) as m:
        expected = {(o.name, o.kind) for o in m.artifacts()}
    draw(app, frames=1)  # the table binds its source on a frame
    rows = app.artifacts.control.records
    assert {(r["name"], r["kind"]) for r in rows} == expected
    assert [r["name"] for r in rows] == ["README", "m.ptu", "bursts", "background", "lifetimes", "fcs"]
    by = {r["name"]: r for r in rows}
    assert (by["bursts"]["rows"], by["bursts"]["grain"], by["bursts"]["operation"], by["bursts"]["parents"]) == (
        32, "burst", "burst_selection", 1)
    assert by["lifetimes"]["parents"] == 2 and by["fcs"]["rows"] == 64

    tool = PtoInspectorTool()
    try:
        tool.model.set_filename(str(shared_container))
        qapp.processEvents()
        from qtpy import QtWidgets

        table = next(
            t for t in tool.auto_form.findChildren(QtWidgets.QTableWidget) if t.rowCount() == len(rows)
        )
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        assert headers[:3] == ["Name", "Kind", "Operation"]
        # every cell of the Qt table is the native table's value (same columns, same rows)
        keys = ["name", "kind", "operation", "grain", "rows", "size", "parents"]
        for r, row in enumerate(rows):
            for c, key in enumerate(keys):
                assert table.item(r, c).text() == str(row[key]), (r, key)
        # the same selection, summary and details: the Qt window and the native one read one view model
        assert tool.model.selected.name == app.model.selected.name == "fcs"
        assert tool.model.summary_html() == app.model.summary_html()
        assert tool.model.detail_html() == app.model.detail_html()
        assert tool.statusBar().currentMessage() == app.model.status == "m.pto — 6 objects"
    finally:
        tool.model.close()
        tool.deleteLater()


def test_payload_and_curve_equal_what_was_stored(app):
    app.model.select_uid(uid_of(app.model, "lifetimes"))
    app.refresh_payload()
    np.testing.assert_allclose(app.payload["tau"], np.linspace(1.0, 4.0, 32))
    np.testing.assert_array_equal(app.payload["First Photon"], np.arange(32))
    assert [c["title"] for c in app.payload_columns] == ["First Photon", "tau [nanoseconds]"]
    assert app.model.curve_series() == []  # a table is not a curve
    app.model.select_uid(uid_of(app.model, "fcs"))
    series = app.model.curve_series()[0]
    np.testing.assert_allclose(series["x"], np.logspace(-3, 3, 64))
    np.testing.assert_allclose(series["y"], np.linspace(1.4, 1.0, 64))
    axes = app.model.curve_axes()
    assert axes["log_x"] and axes["x_label"] == "x [ms]"


def test_the_details_name_the_settings_and_the_parents(app):
    app.model.select_uid(uid_of(app.model, "lifetimes"))
    html = app.model.detail_html()
    assert "burst_lifetime_fitting" in html and "1-exponential" in html
    assert "bursts" in html and "background" in html and "First Photon" in html
    drawn = " ".join(draw(app).strings)  # the Details tab draws the same text, tags removed
    assert "burst_lifetime_fitting" in drawn and "1-exponential" in drawn and "<table>" not in drawn
    assert len(app.graph.document.edges) >= 4  # instrument->3, bursts->lifetimes, background->lifetimes


def test_selection_by_row_graph_node_and_double_click(app):
    app.model.select_row({"uid": uid_of(app.model, "bursts")})
    assert app.model.selected.name == "bursts"
    assert app.artifacts.control.selected_key == uid_of(app.model, "bursts")
    node = next(n for n in app.graph.document.nodes if n.title == "background")
    app.model.select_node({"id": node.id, "config": {"uid": node.id}})
    assert app.model.selected.name == "background"
    opened = []
    app.safe = lambda fn: opened.append(fn.__name__)
    app.model.open_row({"uid": uid_of(app.model, "bursts")})  # a double-click on a row
    assert opened == ["open_tool"] and app.model.selected.name == "bursts"


# ── 2. every action and its error path ──────────────────────────────────


def test_verify_says_what_the_qt_tool_says(qapp, shared_container, app, monkeypatch):
    from chisurf.gui import dialogs
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    shown = []
    monkeypatch.setattr(dialogs.ChiSurfMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a)))
    tool = PtoInspectorTool()
    try:
        tool.model.set_filename(str(shared_container))
        tool._verify()
    finally:
        tool.model.close()
        tool.deleteLater()
    assert shown[0][1:] == ("Integrity", "Every recorded checksum matches the stored bytes.")
    app.verify()
    assert app.notice == shown[0][2]
    assert "Integrity" in app.model.summary_html()


def test_a_damaged_container_fails_verification_in_one_status_line(container, monkeypatch):
    with Measurement.open(container) as m:
        offset = next(o for o in m.artifacts() if o.kind == "tttr_photon_stream").offset
    with open(container, "r+b") as file:
        file.seek(offset + 128)
        byte = file.read(1)
        file.seek(offset + 128)
        file.write(bytes([byte[0] ^ 1]))
    app = make_app()
    try:
        app.model.set_filename(str(container))
        app.verify()
        assert app.notice.startswith("Checksum mismatch:") and "\n" not in app.notice
        assert "mismatch" in " ".join(draw(app).strings).lower()
    finally:
        app.close()


def test_verify_with_nothing_open_reports_it():
    app = make_app()
    try:
        app.verify()
        assert app.notice == "No container open."
        assert any("No container open" in s for s in draw(app).strings)
    finally:
        app.close()


def test_export_equals_the_qt_tool_for_a_table_and_a_raw_payload(qapp, shared_container, app, tmp_path, monkeypatch):
    from chisurf.gui import dialogs
    from chisurf.gui.widgets import general
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    monkeypatch.setattr(dialogs.ChiSurfMessageBox, "information", staticmethod(lambda *a, **k: None))
    tool = PtoInspectorTool()
    try:
        tool.model.set_filename(str(shared_container))
        for name, suffix in (("bursts", ".csv"), ("m.ptu", ".ptu")):
            qt_out, native_out = tmp_path / f"qt_{name}{suffix}", tmp_path / f"native_{name}{suffix}"
            tool.model.select_uid(uid_of(tool.model, name))
            monkeypatch.setattr(general, "save_file", lambda **kw: str(qt_out))
            tool._export()
            app.model.select_uid(uid_of(app.model, name))
            app.export_payload(native_out)
            assert native_out.read_bytes() == qt_out.read_bytes() and native_out.stat().st_size > 0
            assert app.notice == f"Exported: {native_out}"
    finally:
        tool.model.close()
        tool.deleteLater()
    assert "First Photon" in (tmp_path / "native_bursts.csv").read_text().splitlines()[0]
    assert (tmp_path / "native_m.ptu.ptu").read_bytes() == PTU.read_bytes()


def test_export_with_nothing_selected_raises_a_message_not_a_crash():
    app = make_app()
    try:
        with pytest.raises(ValueError, match="Select an artifact"):
            app.export_payload("/nonexistent/x.csv")
        assert app.safe(lambda: app.export_payload("/nonexistent/x.csv")) is None
        assert app.notice.startswith("Error: ")
    finally:
        app.close()


def test_open_tool_picks_the_same_manifest_and_says_so_when_none_claims_it(qapp, shared_container, app, monkeypatch):
    from chisurf.gui import dialogs
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    messages = []
    monkeypatch.setattr(dialogs.ChiSurfMessageBox, "information", staticmethod(lambda *a, **k: messages.append(a)))
    tool = PtoInspectorTool()
    try:
        tool.model.set_filename(str(shared_container))
        launched = []
        tool._launch = launched.append
        for name in ("bursts", "m.ptu"):
            tool.model.select_uid(uid_of(tool.model, name))
            app.model.select_uid(uid_of(app.model, name))
            app.changed("selected")
            launched.clear()
            tool.open_tool()
            assert [m.id for m in app.tools] == [m.id for m in tool.model.tool_manifests()]
            if name == "bursts":  # a tool claims burst_selection; the Qt tool launches the first
                assert app.tools and [m.id for m in launched] == [app.tools[0].id]
            else:  # the carried instrument file has no operation
                assert app.tools == [] and launched == []
        assert app.open_tool() is None and app.notice == "No tool for this operation."
        assert messages and messages[-1][1] == "No tool for this step"
    finally:
        tool.model.close()
        tool.deleteLater()


def test_open_tool_hands_the_file_to_a_ported_tool_and_reports_an_unported_one(app, shared_container):
    calls = []
    child = SimpleNamespace(model=SimpleNamespace(set_filename=lambda p: calls.append(p)), close=lambda: calls.append("closed"))
    app.tool_loader = lambda plugin_id: child
    app.tools = [SimpleNamespace(id="ported", entrypoints=SimpleNamespace(emtk="x:make_app"))]
    assert app.open_tool() is child and calls == [str(shared_container)] and app.child is child
    app.child = None
    app.tools = [SimpleNamespace(id="legacy", entrypoints=SimpleNamespace(emtk=None))]
    assert app.open_tool() is None and app.notice == "This tool has not been ported to EMTK yet. legacy"


def test_a_broken_file_reports_what_the_qt_tool_reports(qapp, tmp_path):
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    bad = tmp_path / "broken.pto"
    bad.write_bytes(b"not a pto")
    tool = PtoInspectorTool()
    app = make_app()
    try:
        tool.model.set_filename(str(bad))
        app.model.set_filename(str(bad))
        assert app.model.status == tool.statusBar().currentMessage()
        assert app.model.status.startswith("Cannot open broken.pto: ")
        assert app.model.inspection is None and app.artifacts.control.records == []
        strings = " ".join(draw(app).strings)
        assert "No container open" in strings and "not a PTO" in strings.replace("PTO.MFDB", "PTO")
    finally:
        tool.model.close()
        tool.deleteLater()
        app.close()


def test_reload_picks_up_a_result_written_since(container):
    app = make_app()
    try:
        app.model.set_filename(str(container))
        draw(app, frames=1)
        assert len(app.artifacts.control.records) == 6
        with Measurement.open(container, writable=True) as m:
            m.put_table("later", {"v": np.array([1.0, 2.0])}, artifact_kind="analysis_result",
                        operation_type="fcs_correlation", row_grain="curve_point")
        app.model.reload()
        draw(app, frames=1)
        assert app.model.selected.name == "later" and len(app.artifacts.control.records) == 7
    finally:
        app.close()


# ── 3. drop and pack, MMFDB picker ──────────────────────────────────────


def test_the_host_hook_takes_a_dropped_container(shared_container):
    """emtk's Qt host accepts a drag only for a control with files_dropped / on_files_dropped."""
    app = make_app()
    try:
        assert callable(app.files_dropped) and callable(app.on_files_dropped)
        assert app.on_files_dropped([]) is False
        assert app.files_dropped(["/tmp/readme.txt"]) is False  # nothing to open or pack
        assert app.model.inspection is None and app.vendor_paths == []
        assert app.files_dropped([str(shared_container)]) is True
        assert app.model.filename == str(shared_container) and app.model.selected.name == "fcs"
    finally:
        app.close()


def test_a_dropped_vendor_file_is_offered_for_packing_and_sources_are_kept(tmp_path):
    raw = tmp_path / "raw.ptu"
    shutil.copy(PTU, raw)
    app = make_app()
    try:
        assert app.files_dropped([str(raw)]) is True
        assert app.vendor_paths == [raw]
        assert any("Choose a folder for the new PTO container" in s for s in draw(app).strings)
        out = tmp_path / "containers"
        out.mkdir()
        app.pack_vendor_files(out)
        assert app.model.filename == str(out / "raw.pto") and app.vendor_paths == []
        assert raw.read_bytes() == PTU.read_bytes()
        with pytest.raises(FileExistsError):
            app.vendor_paths = [raw]
            app.pack_vendor_files(out)
    finally:
        app.close()


def test_the_open_dialog_loads_the_choice_and_cancel_changes_nothing(shared_container, monkeypatch):
    from emtk.file_dialog import FileDialog

    app = make_app()
    try:
        app.choose_file("open")
        assert app.dialog is not None and app.file_action == "open"
        monkeypatch.setattr(FileDialog, "draw", lambda self: False)
        draw(app, frames=1)
        assert app.dialog is None and app.model.inspection is None
        app.choose_file("open")
        monkeypatch.setattr(FileDialog, "draw", lambda self: [str(shared_container)])
        draw(app, frames=1)
        assert app.model.filename == str(shared_container)
    finally:
        app.close()


def test_the_database_picker_opens_the_resolved_container(shared_container, monkeypatch):
    import chisurf.plugins.core.pto_inspector.gui.app as module

    calls = []

    class Picker:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def open(self):
            calls[0]["on_paths"]([shared_container])

        def draw(self, box):
            pass

    monkeypatch.setattr(module, "DatasetPicker", Picker)
    monkeypatch.setattr(module, "session_client", lambda: "fake client")
    app = make_app()
    try:
        app.open_database()
        assert calls[0]["client"] == "fake client" and calls[0]["kinds"] == ["raw_measurement", "raw_data"]
        assert app.model.filename == str(shared_container)
    finally:
        app.close()


# ── 4. drawing, no invented data ────────────────────────────────────────


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (500, 500)])
def test_draws_empty_and_populated(app, size):
    empty = make_app()
    try:
        painter = draw(empty, size)
        strings = " ".join(painter.strings)
        assert "No container open" in strings
        assert empty.artifacts.control.records == []
        assert "is not a" not in strings  # nothing selected: no "not a table" claim about an artifact
    finally:
        empty.close()
    painter = draw(app, size)
    strings = " ".join(painter.strings)
    assert "fcs" in strings and "m.pto" in strings


def test_a_curve_and_a_table_draw_without_error(app, caplog):
    for name in ("lifetimes", "fcs", "README", "m.ptu"):
        app.model.select_uid(uid_of(app.model, name))
        assert draw(app).strings
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    app.model.select_uid(uid_of(app.model, "README"))
    assert app.model.payload_text()  # the README is a text payload, drawn in the Text tab


# ── 5. tooltips, guide, help ────────────────────────────────────────────


def test_every_control_has_a_tooltip(shared_container):
    from test.gui.emtk_port_parity import emtk_inventory

    empty = make_app()
    try:
        assert emtk_inventory(empty)["controls_without_tooltip"] == []
    finally:
        empty.close()
    populated = make_app()
    try:
        populated.model.set_filename(str(shared_container))
        inventory = emtk_inventory(populated)
        assert inventory["controls_without_tooltip"] == []
        labels = {row["label"] for row in inventory["interactive"]}
        assert {"Open", "Database", "Reload", "Verify", "Export", "Help", "Guide", "Fit graph", "Open tool"} <= labels
    finally:
        populated.close()


def test_button_enabled_states_follow_the_state(shared_container, monkeypatch):
    import chisurf.plugins.core.pto_inspector.gui.app as module

    seen = {}
    real = module.PtoInspectorApp.button

    def spy(self, title, tip, fn, enabled=True):
        seen[title] = enabled
        return real(self, title, tip, fn, enabled)

    monkeypatch.setattr(module.PtoInspectorApp, "button", spy)
    app = make_app()
    try:
        draw(app, frames=1)
        assert (seen["Open"], seen["Reload"], seen["Verify"], seen["Export"], seen["Open tool"]) == (
            True, False, False, False, False)
        app.model.set_filename(str(shared_container))  # fcs: no tool claims it
        draw(app, frames=1)
        assert (seen["Reload"], seen["Verify"], seen["Export"], seen["Open tool"]) == (True, True, True, False)
        app.model.select_uid(uid_of(app.model, "bursts"))
        draw(app, frames=1)
        assert seen["Open tool"] is True
    finally:
        app.close()


def test_guide_steps_point_at_controls_the_app_draws(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app.model.select_uid(uid_of(app.model, "bursts"))  # a tool exists, so Open tool is enabled
    draw(app)
    steps = json.loads((GUI / "guide_emtk.json").read_text())["steps"]
    assert len(steps) == 8
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        assert app.rects.get(name), f"{step['title']}: nothing drawn for {name!r}"
    assert [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")] == ["filename", "Verify"]


def test_the_tour_waits_for_the_open_and_the_verify_press(shared_container):
    app = make_app()
    try:
        app.tour.start(1)  # "Open a container"
        assert app.tour.awaiting
        app.model.set_filename(str(shared_container))  # the container is opened, by any route
        assert not app.tour.awaiting
        app.tour.start(7)
        assert app.tour.awaiting
        app.verify()
        app.tour.notify_used("Verify")  # what the button press does
        assert not app.tour.awaiting
        assert draw(app).strings
    finally:
        app.close()


def test_the_qt_tool_keeps_its_own_help_and_guide():
    assert json.loads((GUI / "guide.json").read_text())["steps"][1]["target"] == {"attr": "filename"}
    assert "csg_pto_inspect" in (GUI / "help.md").read_text()


def test_help_exists_its_links_are_live_and_it_draws(app):
    import re

    text = (GUI / "help_emtk.md").read_text()
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert links and all((repo / link).is_file() for link in links)
    for word in ("Open tool", "Verify", "Export", "Provenance", "Database"):
        assert word in text
    app.help.show()
    assert draw(app).strings


# ── 6. persistence, translations, no Qt ─────────────────────────────────


def test_settings_round_trip(shared_container):
    app = make_app()
    try:
        app.model.set_filename(str(shared_container))
        app.model.select_uid(uid_of(app.model, "bursts"))
        app.artifacts.control.filter.set_text("burst")
        saved = json.loads(json.dumps(app.export_settings()))
        assert saved == {"filename": str(shared_container), "selected_uid": uid_of(app.model, "bursts"),
                         "artifact_filter": "burst"}
        other = make_app()
        try:
            other.restore_settings(saved)
            assert other.model.selected.name == "bursts" and other.artifacts.control.filter.text == "burst"
            other.restore_settings({"filename": "/nonexistent/x.pto"})  # a vanished file is reported, not raised
            assert other.model.inspection is None and other.model.status.startswith("Cannot open x.pto")
        finally:
            other.close()
    finally:
        app.close()


def test_the_new_strings_are_translated_in_all_locales():
    from emtk import i18n

    from chisurf.plugins.core.pto_inspector.gui.translations import install, tr

    install()
    original = i18n.get_locale()
    try:
        for locale in ("de", "fr", "es", "pt", "ru"):
            i18n.set_locale(locale)
            assert tr("No container open.") != "No container open."
            assert draw(make_app()).strings
    finally:
        i18n.set_locale(original)


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("pto_inspector")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.core.pto_inspector.gui.app:make_app"
    assert isinstance(make_app(), PtoInspectorApp)
