"""Headless tests for the additive FRET Line Generator.

Each press of *Add FRET line* snapshots the current mixture/sweep and appends it
to a collection that is overlaid on the plots -- successive presses accumulate
rather than replace. These tests drive that accumulation logic on the emtk app's
Qt-free model (:class:`chisurf.plugins.fret_line.gui.model.FretLineModel`); they
drove the retired Qt ``FRETLineTool`` before, and assert the same behaviour.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.fret_line.gui.model import FretLineModel


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture
def model():
    m = FretLineModel()
    assert m.sweep_labels(), "there is something to sweep"
    yield m
    m.close()


def compute_one(model, sweep_index=0, lo=20.0, hi=60.0, n=8):
    labels = model.sweep_labels()
    model.sweep_label = labels[min(sweep_index, len(labels) - 1)]
    model.minimum, model.maximum, model.n_points = lo, hi, n
    assert model.add_line() is not None, model.message


def test_starts_empty(model):
    assert model.lines == [] and model.line_rows() == []
    assert not model.enabled("save_csv")
    assert not model.enabled("push")


def test_compute_is_additive(model):
    compute_one(model, 0)
    assert len(model.lines) == len(model.line_rows()) == 1
    assert model.enabled("save_csv") and model.enabled("push")

    # a second press appends rather than replaces
    compute_one(model, 1)
    assert len(model.lines) == len(model.line_rows()) == 2

    # each line carries a distinct colour and a populated result
    assert len({line["color"] for line in model.lines}) == 2
    for line in model.lines:
        assert len(line["result"]["parameter_values"]) == 8


def test_remove_and_clear(model):
    compute_one(model, 0)
    compute_one(model, 1)
    compute_one(model, 0)
    assert len(model.lines) == 3

    model.select_line(model.lines[1])
    model.remove_line()
    assert len(model.lines) == len(model.line_rows()) == 2

    model.clear_lines()
    assert model.lines == []
    assert not model.enabled("save_csv") and not model.enabled("push")


def test_visibility_checkboxes(model):
    compute_one(model, 0)
    compute_one(model, 1)
    # both start visible (their Show box ticked)
    assert all(line["visible"] for line in model.line_rows())

    # unticking a Show box hides that line but keeps it in the table
    row = model.line_rows()[0]
    row["visible"] = False
    model.line_edited(row, "visible", False)
    assert not model.lines[0]["visible"] and model.lines[1]["visible"]
    assert len(model.lines) == 2 and "hidden" in model.message

    # hide-all / show-all
    model.hide_all()
    assert not any(line["visible"] for line in model.lines)
    model.show_all()
    assert all(line["visible"] for line in model.lines)


def test_editing_mixture_keeps_lines(model):
    # Computed lines are snapshots: changing the mixture must not drop them.
    compute_one(model, 0)
    model.add_component()
    assert len(model.lines) == 1 and model.enabled("save_csv")


def test_save_csv_all_lines(model, tmp_path):
    compute_one(model, 0)
    compute_one(model, 1)
    path = tmp_path / "lines.csv"
    model.write_csv(path)
    text = path.read_text()
    assert "Line 1" in text and "Line 2" in text
    # the header documents the tidy/long layout with a per-row line column
    assert "line,sweep,log,components,parameter" in text
