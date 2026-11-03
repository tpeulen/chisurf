"""The port-check tool measures what a porter would otherwise only claim: tooltips, controls, no Qt."""

from __future__ import annotations

import json

import pytest

from test.gui import emtk_port_parity as epp


def test_normalize_treats_renames_as_parity():
    assert epp.normalize("&Open…") == epp.normalize("Open...")
    assert epp.normalize("📁 Folder") == epp.normalize("Folder")
    assert epp.normalize("<b>Bins X:</b>") == "binsx"
    assert epp.normalize("ℹ️ Help") == "help"
    assert epp.normalize("📥loadtttr") == "loadtttr"  # already normalised, emoji glued on
    assert epp.normalize(epp.normalize("📥 Load TTTR")) == "loadtttr"
    assert epp.normalize("χ² min") == "χ²min"  # a name, not a pictogram


def test_recorder_attributes_a_tooltip_to_the_control_before_it():
    from emtk import im
    from emtk.app import ImApp

    def gui():
        im.begin("t", (0, 0, 300, 200))
        im.button("Run")
        im.set_item_tooltip("Start the analysis.")
        im.button("Stop")  # no tooltip: must be reported
        im.end()

    inventory = epp.emtk_inventory(ImApp(gui), (400, 300))
    by_label = {row["label"]: row["tooltip"] for row in inventory["interactive"]}
    assert by_label == {"Run": "Start the analysis.", "Stop": ""}
    assert inventory["controls_without_tooltip"] == ["button: Stop"]
    assert {"run", "stop"} <= set(inventory["controls"])


def test_recorder_restores_emtk_after_use():
    from emtk import im

    original = im.button
    from emtk.app import ImApp

    epp.emtk_inventory(ImApp(lambda: None), (100, 100))
    assert im.button is original


def test_a_real_port_produces_the_evidence_files(tmp_path):
    """f_test is the reference port: it must come out clean, Qt-free and screenshotted."""
    data = epp.after("f_test", tmp_path)
    assert data["controls_without_tooltip"] == []
    assert data["qt_free"]["ok"], data["qt_free"]["output"]
    assert (tmp_path / "after_1200x800.png").stat().st_size > 2000
    assert (tmp_path / "after_800x600.png").stat().st_size > 2000


def test_the_command_line_writes_the_evidence_and_passes_a_clean_port(tmp_path):
    assert epp.main(["after", "f_test", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "after.json").read_text())
    assert data["controls_without_tooltip"] == [] and data["qt_free"]["ok"]


def test_unknown_plugin_is_a_clear_error():
    with pytest.raises(KeyError):
        epp.manifest_of("no_such_plugin_id")


def test_entry_overrides_the_manifest_so_a_partial_port_can_be_checked(tmp_path):
    """f_test's factory, named explicitly, builds and passes the Qt-free proof without the manifest."""
    entry = "chisurf.plugins.core.f_test.gui.app:make_app"
    assert epp.build_emtk_app("no_such_plugin_id_needed", entry) is not None
    assert epp.qt_free("no_such_plugin_id_needed", entry)["ok"]


def test_a_missing_entry_is_a_clear_error(monkeypatch):
    # A synthetic Qt-only manifest: a real plugin id stops being Qt-only the day it is ported.
    monkeypatch.setattr(epp, "manifest_of", lambda _id: {"entrypoints": {"gui": "m:Tool"}})
    with pytest.raises(ValueError, match="--entry"):
        epp.build_emtk_app("qt_only")


def test_a_numeric_input_is_one_control_with_its_tooltip():
    """input_float/input_int are built on other wrapped widgets; they must not add phantom rows."""
    from emtk import im
    from emtk.app import ImApp

    def gui():
        im.begin("t", (0, 0, 300, 300))
        im.input_float("##a", 1.0)
        im.set_item_tooltip("tip a")
        im.input_int("##b", 2)
        im.set_item_tooltip("tip b")
        im.end()

    inventory = epp.emtk_inventory(ImApp(gui), (400, 400))
    rows = {(r["kind"], r["label"]): r["tooltip"] for r in inventory["interactive"]}
    assert rows == {("input_float", "a"): "tip a", ("input_int", "b"): "tip b"}
    assert inventory["controls_without_tooltip"] == []
