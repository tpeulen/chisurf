"""The port-evidence tool measures what a porter would otherwise only claim.

Runs without Qt except for the ``before`` half, which is not exercised here.
"""

from __future__ import annotations

import json

import pytest

from test.gui import emtk_port_parity as epp


def test_normalize_treats_renames_as_parity():
    assert epp.normalize("&Open…") == epp.normalize("Open...")
    assert epp.normalize("📁 Folder") == epp.normalize("Folder")
    assert epp.normalize("<b>Bins X:</b>") == "binsx"
    assert epp.normalize("ℹ️ Help") == "help"
    assert epp.normalize("📥loadtttr") == "loadtttr"      # already normalised, emoji glued on
    assert epp.normalize(epp.normalize("📥 Load TTTR")) == "loadtttr"
    assert epp.normalize("χ² min") == "χ²min"       # a name, not a pictogram


def test_recorder_attributes_a_tooltip_to_the_control_before_it():
    from emtk import im
    from emtk.app import ImApp

    def gui():
        im.begin("t", (0, 0, 300, 200))
        im.button("Run")
        im.set_item_tooltip("Start the analysis.")
        im.button("Stop")            # no tooltip: must be reported
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


def test_compare_flags_a_lost_control(tmp_path):
    (tmp_path / "before.json").write_text(json.dumps({"controls": ["run", "stop", "save"]}))
    (tmp_path / "after.json").write_text(
        json.dumps({"controls": ["run", "stop"], "controls_without_tooltip": [],
                    "qt_free": {"ok": True}})
    )
    result = epp.compare("x", tmp_path)
    assert result["lost"] == ["save"]


def test_unknown_plugin_is_a_clear_error():
    with pytest.raises(KeyError):
        epp.manifest_of("no_such_plugin_id")


def _evidence(tmp_path, before, after, deliberate=None):
    (tmp_path / "before.json").write_text(json.dumps({"controls": before}))
    (tmp_path / "after.json").write_text(
        json.dumps({"controls": after, "controls_without_tooltip": [], "qt_free": {"ok": True}})
    )
    if deliberate is not None:
        (tmp_path / "deliberate.json").write_text(json.dumps(deliberate))


def test_a_deliberate_difference_is_explained_not_hidden(tmp_path):
    _evidence(tmp_path, ["run", "\u03b51", "save"], ["run", "save"], {"\u03b5 1": "now a table column"})
    result = epp.compare("x", tmp_path)
    assert result["lost"] == []
    assert result["explained"] == {"\u03b51": "now a table column"}


def test_an_explanation_for_a_control_that_is_present_is_reported_stale(tmp_path):
    _evidence(tmp_path, ["run"], ["run"], {"run": "no longer needed"})
    assert epp.compare("x", tmp_path)["stale_explanations"] == ["run"]


def test_an_unexplained_loss_still_blocks(tmp_path, capsys):
    _evidence(tmp_path, ["run", "save"], ["run"], {"other": "x"})
    assert epp.main(["compare", "x", "--out", str(tmp_path)]) == 1


def test_compare_normalises_both_halves(tmp_path):
    """Evidence written by an older tool (emoji glued on) still compares equal."""
    _evidence(tmp_path, ["\U0001f4e5loadtttr", "run"], ["loadtttr", "run"])
    assert epp.compare("x", tmp_path)["lost"] == []
