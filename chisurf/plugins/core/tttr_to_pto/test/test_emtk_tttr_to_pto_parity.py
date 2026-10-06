"""The native TTTR <-> .pto converter against the Qt drop tool: results, rows, actions, errors, drawing.

Hermetic: the settings folder and every vendor/container file live in ``tmp_path`` (private copies
of the burst_selection BH fixture); nothing reads or writes ``~/.chisurf``.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.tttr_to_pto.gui.app import TttrToPtoApp, create_app, make_app
from chisurf.plugins.core.tttr_to_pto.gui.model import TttrToPtoModel

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "tttr_to_pto_emtk.view.json"
DATA = HERE.parents[2] / "burst" / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
SIDECAR = b"BH settings kept byte for byte\r\n"

needs_data = pytest.mark.skipif(not (DATA / "m000.spc").exists(), reason="BH SPC fixture absent")


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


def make_folder(folder: Path) -> dict[str, bytes]:
    """m000.spc, m001.spc and the m000.set sidecar; returns name -> bytes."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("m000.spc", "m001.spc"):
        shutil.copy(DATA / name, folder / name)
    (folder / "m000.set").write_bytes(SIDECAR)
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def draw(app, size=(900, 600), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def finish(app, seconds=60.0):
    """Run the queue to its end the way frames do."""
    end = time.monotonic() + seconds
    while app.model.job.running or app.model.pending:
        draw(app, frames=1)
        assert time.monotonic() < end, "the conversion did not finish"
        time.sleep(0.01)
    draw(app, frames=1)


def table(app):
    return app.form.tables["records"].control


# ── 1. results equal the Qt tool's ──────────────────────────────────────


@needs_data
def test_pack_and_unpack_equal_the_qt_tool(qapp, tmp_path):
    """Same input in two folders: the Qt drop tool and the native app write and recover the same."""
    from chisurf.plugins.core.tttr_to_pto.gui.tool import TttrToPtoTool

    qt_dir, native_dir = tmp_path / "qt", tmp_path / "native"
    originals = make_folder(qt_dir)
    make_folder(native_dir)

    tool = TttrToPtoTool()
    try:
        tool._on_dropped([str(qt_dir / "m001.spc"), str(qt_dir / "m000.spc")])
        qt_pack = tool._list.item(0).text()
        tool._on_dropped([str(qt_dir / "m000.pto")])
        qt_unpack = tool._list.item(1).text()
        qt_bytes = {p.name: p.read_bytes() for p in qt_dir.iterdir()}
    finally:
        tool.close()

    app = make_app()
    try:
        assert app.add_paths([native_dir / "m001.spc", native_dir / "m000.spc"])
        finish(app)
        assert app.add_paths([native_dir / "m000.pto"])
        finish(app)
        pack, unpack = app.model.records
    finally:
        app.close()

    # the rows say what the Qt list says
    assert qt_pack == f"{pack['files']} → {pack['result']}" == "m000.spc, m001.spc → m000.pto"
    assert qt_unpack == f"m000.pto → {unpack['result']}"
    assert (pack["status"], pack["action"], unpack["status"], unpack["action"]) == (
        "Verified",
        "Pack",
        "Verified",
        "Unpack",
    )
    # the same files exist, byte for byte, and equal the originals; the sidecar rode along
    native_bytes = {p.name: p.read_bytes() for p in native_dir.iterdir()}
    assert sorted(native_bytes) == sorted(qt_bytes)
    for name, payload in originals.items():
        assert native_bytes[name] == payload and qt_bytes[name] == payload
    for folder in (qt_dir, native_dir):
        with Measurement.open(folder / "m000.pto", writable=False) as m:
            assert m.verify() == []


@needs_data
def test_an_unreadable_container_fails_with_the_text_the_qt_tool_shows(qapp, tmp_path):
    from chisurf.plugins.core.tttr_to_pto.gui.tool import TttrToPtoTool

    bad = tmp_path / "bad.pto"
    bad.write_bytes(b"not a PTO")
    tool = TttrToPtoTool()
    try:
        tool._on_dropped([str(bad)])
        qt_text = tool._list.item(0).text()
    finally:
        tool.close()
    app = make_app()
    try:
        assert app.add_paths([bad])
        finish(app)
        record = app.model.records[0]
        assert (record["status"], record["action"]) == ("Failed", "Unpack")
        assert qt_text == f"bad.pto: could not unpack ({record['result']})"
        assert "not an EBML file" in record["result"]
        assert bad.read_bytes() == b"not a PTO"
    finally:
        app.close()


@needs_data
def test_the_accept_rule_equals_the_qt_filter(qapp, tmp_path):
    from chisurf.plugins.core.tttr_to_pto.gui.tool import TttrToPtoTool

    make_folder(tmp_path)
    (tmp_path / "x.pto").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("hi")
    for name in ("m000.spc", "m000.set", "x.pto", "notes.txt"):
        assert TttrToPtoModel.accepts(tmp_path / name) == TttrToPtoTool._accepts(
            str(tmp_path / name)
        ), name
    assert not TttrToPtoModel.accepts(
        tmp_path / "missing.ptu"
    )  # the Qt drop only offers existing paths


# ── 2. every action and its error path ──────────────────────────────────


@needs_data
def test_pack_keeps_every_source_and_is_verified(tmp_path):
    originals = make_folder(tmp_path)
    app = make_app()
    try:
        assert app.add_paths([tmp_path / "m001.spc", tmp_path / "m000.spc"])
        finish(app)
        row = app.model.rows[0]
        assert row["status"] == "verified" and row["action"] == "pack"
        assert [Path(p).name for p in row["paths"]] == ["m000.spc", "m001.spc"]
        assert row["outputs"] == [str(tmp_path / "m000.pto")]
        for name, payload in originals.items():
            assert (tmp_path / name).read_bytes() == payload
        assert app.model.last_dir == str(tmp_path)
    finally:
        app.close()


@needs_data
def test_a_failed_verification_fails_the_row_and_keeps_the_sources(tmp_path, monkeypatch):
    originals = make_folder(tmp_path)
    monkeypatch.setattr(Measurement, "verify", lambda self: ["checksum mismatch"])
    app = make_app()
    try:
        app.add_paths([tmp_path / "m000.spc"])
        finish(app)
        record = app.model.records[0]
        assert record["status"] == "Failed" and record["result"] == "checksum mismatch"
        for name, payload in originals.items():
            assert (tmp_path / name).read_bytes() == payload
    finally:
        app.close()


def test_a_lone_sidecar_a_missing_file_and_an_unknown_type_are_rejected(tmp_path):
    (tmp_path / "alone.set").write_bytes(b"sidecar")
    (tmp_path / "notes.txt").write_text("hello")
    app = make_app()
    try:
        assert (
            app.add_paths(
                [tmp_path / "alone.set", tmp_path / "missing.ptu", tmp_path / "notes.txt"]
            )
            is False
        )
        records = app.model.records
        assert [r["status"] for r in records] == ["Rejected"] * 3
        assert records[0]["result"] == "Sidecars need their .spc file."
        assert (
            records[1]["result"]
            == records[2]["result"]
            == "Choose existing vendor photon files or PTO containers."
        )
        assert not app.model.pending and not app.model.job.running
        assert (tmp_path / "alone.set").read_bytes() == b"sidecar"
    finally:
        app.close()


@needs_data
def test_conversions_run_one_at_a_time_in_order(tmp_path, monkeypatch):
    import threading

    make_folder(tmp_path)
    gate = threading.Event()
    calls = []

    def converter(paths, keep_original=True):
        calls.append([Path(p).name for p in paths])
        gate.wait(10)
        from chisurf.plugins.core.tttr_to_pto import api

        return api.convert(paths, keep_original=keep_original)

    app = TttrToPtoApp(converter=converter)
    try:
        app.add_paths([tmp_path / "m000.spc"])
        app.add_paths([tmp_path / "m001.spc"])
        draw(app, frames=1)
        assert [r["status"] for r in app.model.rows] == ["running", "queued"]
        assert [r["status"] for r in app.model.records] == ["Converting...", "Queued"]
        assert "Converting" in " ".join(draw(app).strings)
        assert app.model.enabled("clear_history") is False  # nothing finished yet
        gate.set()
        finish(app)
        assert calls == [["m000.spc"], ["m001.spc"]]
        assert [r["status"] for r in app.model.rows] == ["verified", "verified"]
    finally:
        gate.set()
        app.close()


@needs_data
def test_clear_history_drops_finished_rows_only(tmp_path):
    make_folder(tmp_path)
    app = make_app()
    try:
        app.add_paths([tmp_path / "m000.spc"])
        finish(app)
        assert app.model.enabled("clear_history")
        app.model.pending.append(app.model._append([str(tmp_path / "x")], "pack", "queued"))
        app.model.clear_history()
        assert [r["status"] for r in app.model.rows] == ["queued"]
        assert (tmp_path / "m000.pto").exists()  # files on disk are not touched
        app.model.pending.clear()
        app.model.rows[0]["status"] = "interrupted"
        app.model.clear_history()
        assert app.model.rows == [] and app.model.records == []
    finally:
        app.close()


def test_the_host_hook_takes_a_drop(tmp_path):
    """emtk's Qt host only accepts a drag when the control has files_dropped / on_files_dropped."""
    (tmp_path / "alone.set").write_bytes(b"sidecar")
    app = make_app()
    try:
        assert callable(app.files_dropped) and callable(app.on_files_dropped)
        assert app.on_files_dropped([]) is False
        assert app.files_dropped([str(tmp_path / "alone.set")]) is False  # rejected, but listed
        assert len(app.model.rows) == 1
        app.close()
        assert app.files_dropped([str(tmp_path / "x.ptu")]) is False  # closed: nothing queued
        assert len(app.model.rows) == 1
    finally:
        app.close()


@needs_data
def test_a_drop_through_the_hook_converts(tmp_path):
    make_folder(tmp_path)
    app = make_app()
    try:
        assert app.on_files_dropped([str(tmp_path / "m000.spc")]) is True
        finish(app)
        assert (tmp_path / "m000.pto").exists()
        assert app.model.records[0]["status"] == "Verified"
    finally:
        app.close()


@needs_data
def test_add_files_opens_the_dialog_and_converts_the_choice(tmp_path, monkeypatch):
    from emtk.file_dialog import FileDialog

    make_folder(tmp_path)
    app = make_app()
    try:
        app.model.last_dir = str(tmp_path)
        app.model.request_add()
        draw(app, frames=1)
        assert app.dialog is not None and app.dialog.title == "Add files"
        assert Path(app.dialog.directory) == tmp_path
        monkeypatch.setattr(
            FileDialog,
            "draw",
            lambda self: [str(tmp_path / "m001.spc"), str(tmp_path / "m000.spc")],
        )
        draw(app, frames=1)
        assert app.dialog is None
        finish(app)
        assert app.model.records[0]["files"] == "m000.spc, m001.spc"  # one container, name order
        # cancel: closes, adds nothing
        monkeypatch.setattr(FileDialog, "draw", lambda self: False)
        app.model.request_add()
        draw(app, frames=1)
        assert app.dialog is None and len(app.model.rows) == 1
    finally:
        app.close()


# ── 3. drawing, no invented data ────────────────────────────────────────


def test_the_empty_state_is_a_message_and_no_rows():
    app = make_app()
    try:
        painter = draw(app)
        assert app.model.records == []
        assert any("No conversions yet" in s for s in painter.strings)
        assert any("Drop vendor photon file(s)" in s for s in painter.strings)
        assert app.model.enabled("clear_history") is False
    finally:
        app.close()


@needs_data
@pytest.mark.parametrize("size", [(1200, 800), (900, 600), (800, 600), (500, 500)])
def test_draws_empty_and_populated(tmp_path, size):
    make_folder(tmp_path)
    app = make_app()
    try:
        empty = draw(app, size)
        assert len(empty.texts) > 5
        app.add_paths([tmp_path / "m001.spc", tmp_path / "m000.spc", tmp_path / "alone.set"])
        finish(app)
        painter = draw(app, size)
        strings = " ".join(painter.strings)
        assert "m000.pto" in strings and "Verified" in strings and "Rejected" in strings
        assert table(app).row_count() == 2
    finally:
        app.close()


# ── 4. tooltips, spec, guide, help ──────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    model = TttrToPtoModel()
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source", "options_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options") or {}
        if options.get("source"):
            record_keys = set(
                model._record(
                    {
                        "id": "1",
                        "paths": ["a"],
                        "action": "pack",
                        "status": "queued",
                        "outputs": [],
                        "error": "",
                    }
                )
            )
            assert hasattr(model, options["source"])
            assert {c["key"] for c in options["columns"]} <= record_keys
            assert options["row_key"] in record_keys and options["tooltip_key"] in record_keys
    model.close()


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("tttr_to_pto")
    try:
        inventory = emtk_inventory(app)
    finally:
        app.close()
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {"Add files...", "Clear history", "Guide", "Help"} <= labels
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        if section.get("type") in ("custom", "info", "button_row"):
            assert section.get("description"), section.get("key") or section
        for button in section.get("buttons", []):
            assert button.get("description"), button
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("tooltip"), column


@needs_data
def test_the_populated_app_has_no_untooltipped_control_either(tmp_path):
    from test.gui.emtk_port_parity import emtk_inventory

    make_folder(tmp_path)
    app = make_app()
    try:
        app.add_paths([tmp_path / "m000.spc"])
        finish(app)
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()


def test_guide_steps_point_at_controls_the_app_draws():
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = make_app()
    try:
        draw(app)
        steps = json.loads((GUI / "guide_emtk.json").read_text())["steps"]
        assert len(steps) == 5
        for step in steps:
            name = EmTkGuidedTour._target_key(step["target"])
            rect = app.item_rects.get(name) or app.form.rects.get(name)
            assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
        assert [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")] == [
            "request_add"
        ]
        heard = []
        app.tour.notify_used = heard.append
        app.form.on_used = app.tour.notify_used
        app.form.used("request_add")
        assert heard == ["request_add"]
        app.tour.start()
        assert draw(app).strings
    finally:
        app.close()


def test_help_exists_and_draws():
    text = (GUI / "help_emtk.md").read_text()
    for word in ("Add files...", "Clear history", "sidecar", "Both ways"):
        assert word in text
    app = make_app()
    try:
        app.help_window.show()
        assert draw(app).strings
    finally:
        app.close()


def test_the_qt_tool_keeps_its_own_help_and_guide():
    """The legacy Qt tool still reads help.md and guide.json untouched."""
    assert json.loads((GUI / "guide.json").read_text())["steps"][1]["await"]["hint"].startswith(
        "Drop a vendor"
    )
    assert "TTTR ⇄ PTO" in (GUI / "help.md").read_text()


# ── 5. persistence, no Qt ───────────────────────────────────────────────


@needs_data
def test_settings_round_trip(tmp_path):
    make_folder(tmp_path)
    app = make_app()
    try:
        app.add_paths([tmp_path / "m000.spc"])
        finish(app)
        saved = json.loads(json.dumps(app.export_settings()))
        assert saved["last_dir"] == str(tmp_path) and saved["history"][0]["status"] == "verified"
        saved["history"].append(
            {
                "paths": ["/x/old.ptu"],
                "action": "pack",
                "status": "queued",
                "outputs": [],
                "error": "",
                "id": "9",
            }
        )
        other = make_app()
        try:
            other.restore_settings(saved)
            assert [r["status"] for r in other.model.rows] == ["verified", "interrupted"]
            assert other.model.last_dir == str(tmp_path)
            other.poll()
            assert not other.model.job.running and not other.model.pending  # never replayed
            assert draw(other).strings
        finally:
            other.close()
    finally:
        app.close()


def test_restore_is_refused_while_a_write_runs(tmp_path):
    import threading

    gate = threading.Event()
    (tmp_path / "a.ptu").write_bytes(b"x")
    app = TttrToPtoApp(
        converter=lambda paths, keep_original=True: gate.wait(10) or tmp_path / "a.pto"
    )
    try:
        app.add_paths([tmp_path / "a.ptu"])
        with pytest.raises(RuntimeError, match="write is active"):
            app.restore_settings({"history": []})
    finally:
        gate.set()
        app.close()


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_to_pto")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.core.tttr_to_pto.gui.app:create_app"
    assert isinstance(create_app(), TttrToPtoApp)
