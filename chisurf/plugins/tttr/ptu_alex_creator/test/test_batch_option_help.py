"""ALEX batch radio help explains actual operations without changing values or controls."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from emtk.i18n import get_locale, set_locale, tr

from chisurf.plugins.emtk_test_input import Driver

GUI = Path(__file__).resolve().parents[1] / "gui"
CONVERT_NOTE = "Fold each input file independently and write one converted output per input file."
MERGE_NOTE = "Concatenate the input files with continuing macro-time, then fold once and write one merged output."


def walk(sections):
    """Visit the native form’s authored sections without changing their order."""
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def batch_choice(spec):
    """Return the actual native batch-mode control."""
    return next(
        section for section in walk(spec["sections"]) if section.get("attr") == "batch_mode"
    )


@pytest.fixture
def ui(tmp_path, monkeypatch):
    """Isolate every preference and restore the prior UI language."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

    locale = get_locale()
    app = AlexApp(tmp_path / "state.json")
    driver = Driver(app, size=(1100, 720))
    yield driver
    app.close()
    set_locale(locale)


def test_batch_metadata_explains_both_operations_and_keeps_actual_values():
    """The two existing choices acquire distinct operational notes, not new option values."""
    spec = json.loads((GUI / "alex_emtk.view.json").read_text())
    choice = batch_choice(spec)
    assert choice["descriptions"] == [CONVERT_NOTE, MERGE_NOTE]
    assert choice["options"] == ["convert", "merge"]
    assert choice["labels"] == ["Convert each", "Merge into one"]
    assert choice["attr"] == "batch_mode" and choice["style"] == "radio"
    fields = {
        section["attr"]: section
        for section in walk(spec["sections"])
        if section.get("attr") in {"alex_period", "period_shift"}
    }
    assert (
        fields["alex_period"]["minimum"],
        fields["alex_period"]["maximum"],
        fields["alex_period"]["step"],
    ) == (1, 65536, 100)
    assert (
        fields["period_shift"]["minimum"],
        fields["period_shift"]["maximum"],
        fields["period_shift"]["step"],
    ) == (-1000000, 1000000, 1)


@pytest.mark.parametrize("locale", ["de", "fr"])
def test_description_arrays_translate_without_translating_option_values(ui, locale):
    """The app localizes option help through the same catalog as labels."""
    from chisurf.plugins.tttr.ptu_alex_creator.gui.app import translated

    set_locale(locale)
    original = json.loads((GUI / "alex_emtk.view.json").read_text())
    changed = translated(original)
    notes = batch_choice(changed)["descriptions"]
    assert notes == [tr(CONVERT_NOTE), tr(MERGE_NOTE)]
    assert all(
        localized != english for localized, english in zip(notes, [CONVERT_NOTE, MERGE_NOTE])
    )
    assert batch_choice(changed)["options"] == ["convert", "merge"]
    assert batch_choice(original)["descriptions"] == [CONVERT_NOTE, MERGE_NOTE]


@pytest.mark.parametrize("locale", ["en", "de", "fr"])
@pytest.mark.parametrize("size", [(1100, 720), (800, 600)])
def test_help_metadata_keeps_all_default_and_narrow_control_rectangles(ui, locale, size):
    """Adding help does not move, rename or resize any existing control in the same locale."""
    set_locale(locale)
    ui.size = size
    choice = batch_choice(ui.app.spec_source)
    descriptions = choice.pop("descriptions")
    ui.app.spec = None
    ui.draw(3)
    before_rectangles, before_settings = dict(ui.app.item_rects), ui.app.get_state()
    choice["descriptions"] = descriptions
    ui.app.spec = None
    ui.draw(3)
    assert ui.app.item_rects == before_rectangles
    assert ui.app.get_state() == before_settings


@pytest.mark.parametrize("locale", ["en", "de", "fr"])
@pytest.mark.parametrize("index", [0, 1])
def test_hover_displays_each_operational_note_without_changing_settings(ui, locale, index):
    """Real pointer hover produces the corresponding rendered, localized option tooltip."""
    set_locale(locale)
    ui.draw(3)
    before = ui.app.get_state()
    assert {"batch_mode.0", "batch_mode.1"} <= ui.app.item_rects.keys()
    x, y, w, h = ui.rect(f"batch_mode.{index}")
    # Hover the visible radio indicator; long localized labels can extend
    # beyond the legacy pane even though the indicator remains reachable.
    ui.app.pointer_move(x + min(10.0, w / 2), y + h / 2)
    ui.draw(2)
    time.sleep(0.55)
    painter = ui.draw(2)
    rendered = " ".join(str(row[5]) for row in painter.texts)
    expected = tr([CONVERT_NOTE, MERGE_NOTE][index])
    assert " ".join(expected.split()) in " ".join(rendered.split())
    assert ui.app.get_state() == before
    ui.click_name(f"batch_mode.{index}", fx=min(10.0 / w, 0.5))
    assert ui.app.batch_mode == ["convert", "merge"][index]
    assert (ui.app.alex_period, ui.app.period_shift) == (8000, 0)
