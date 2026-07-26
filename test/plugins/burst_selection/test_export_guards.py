"""Headless tests for the Burst Selection export entries (`.bur` / flrCIF).

Pins the guard of :meth:`BurstSelectionTool.export_bur` and
:meth:`BurstSelectionTool.export_flr_cif`: a ``pandas.DataFrame`` has no truth
value, so ``if not self._last_frame`` raised ``ValueError`` for exactly the case
that has something to export.
"""

from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("qtpy")
pytest.importorskip("pyqtgraph")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def tool(qapp):
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    return BurstSelectionTool(show_channel_selection=False)


@pytest.fixture
def frame():
    """Build a minimal burst table with the columns the exporters walk."""
    return pd.DataFrame(
        {
            "Duration (ms)": [1.5, 2.5, 3.5],
            "Number of Photons": [120, 240, 360],
            "Proximity Ratio": [0.1, 0.5, 0.9],
        }
    )


def _patch_save_dialog(monkeypatch, path):
    """Make ``QFileDialog.getSaveFileName`` return *path* without a GUI."""
    from qtpy import QtWidgets

    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(path), "")),
    )


def test_export_bur_writes_non_empty_frame(tool, frame, tmp_path, monkeypatch):
    target = tmp_path / "bursts.bur"
    _patch_save_dialog(monkeypatch, target)
    tool._last_frame = frame

    tool.export_bur()

    assert target.exists()
    assert "Exported to" in tool.summary.toPlainText()
    written = pd.read_csv(target, sep="\t")
    assert list(written.columns) == list(frame.columns)
    assert len(written) == len(frame)


def test_export_flr_cif_writes_non_empty_frame(tool, frame, tmp_path, monkeypatch):
    target = tmp_path / "bursts.cif"
    _patch_save_dialog(monkeypatch, target)
    tool._last_frame = frame

    tool.export_flr_cif()

    assert target.exists()
    assert "Exported to" in tool.summary.toPlainText()
    text = target.read_text()
    assert "loop_" in text
    for column in frame.columns:
        assert f"_{column}" in text


@pytest.mark.parametrize("empty", [None, pd.DataFrame()])
@pytest.mark.parametrize("method", ["export_bur", "export_flr_cif"])
def test_export_without_data_reports_instead_of_writing(tool, tmp_path, monkeypatch, empty, method):
    target = tmp_path / "should-not-appear"
    _patch_save_dialog(monkeypatch, target)
    tool._last_frame = empty

    getattr(tool, method)()

    assert not target.exists()
    assert tool.summary.toPlainText() == "No burst data to export."
