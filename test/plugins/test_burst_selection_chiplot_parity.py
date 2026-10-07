"""Measured retained plot data survives both rendering backends without passthrough."""

from __future__ import annotations

import hashlib
import json
import shutil
import warnings
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from chisurf.gui import chiplot as cp
from chisurf.gui.chiplot import backends

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures/burst_selection_plot_reference.json").read_text()
)
DATA = (
    Path(__file__).parents[2] / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)


def _items(plot):
    """Inspect backend items in tests only, returning their original numeric samples."""
    canvas = plot._canvas
    if hasattr(canvas, "_entries"):
        result = []
        for entry in canvas._entries:
            state = entry.state
            if entry.kind == "curve":
                result.append({"kind": "curve", "x": state["x"], "y": state["y"]})
            elif entry.kind == "bars":
                result.append(
                    {
                        "kind": "bars",
                        "x": state["x"],
                        "height": state["height"],
                        "width": state["width"],
                    }
                )
            elif entry.kind == "text":
                result.append({"kind": "text", "text": state["text"]})
        return result
    result = []
    items = list(canvas._pi.items)
    items.extend(
        item
        for item in canvas._pi.childItems()
        if type(item).__name__ == "TextItem" and item not in items
    )
    for item in items:
        if hasattr(item, "getOriginalDataset"):
            x, y = item.getOriginalDataset()
            if x is not None and y is not None:
                result.append({"kind": "curve", "x": x, "y": y})
        elif type(item).__name__ == "BarGraphItem":
            opts = item.opts
            result.append(
                {"kind": "bars", "x": opts["x"], "height": opts["height"], "width": opts["width"]}
            )
        elif type(item).__name__ == "TextItem":
            result.append({"kind": "text", "text": item.toPlainText()})
    return result


@pytest.mark.parametrize("backend", ["pyqtgraph", "emtk"])
def test_measured_six_panels_keep_raw_samples_units_and_modes(qapp, tmp_path, monkeypatch, backend):
    """Two genuine files yield the legacy numeric arrays and reachable plot quantities."""
    from mmfdb.repository import MFDatabase

    from chisurf.plugins.burst.burst_selection.gui.model import save_setup
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    monkeypatch.setenv("CHISURF_PLOT_BACKEND", backend)
    monkeypatch.setattr(backends, "_active", None)
    for key, name in {
        "CHISURF_SETTINGS_DIR": "settings",
        "MMFDB_SETTINGS_DIR": "mmfdb",
        "MMFDB_DATABASE_PATH": "database.sqlite",
        "MMFDB_OBJECT_STORE_ROOT": "objects",
    }.items():
        monkeypatch.setenv(key, str(tmp_path / name))
    MFDatabase(str(tmp_path / "database.sqlite")).close()
    save_setup(
        "plot-proof",
        {
            "detectors": {
                "green": {"chs": [0, 1], "micro_time_ranges": []},
                "red": {"chs": [8, 9], "micro_time_ranges": []},
            },
            "windows": {},
            "tttr_reading": {"file_type": "SPC-130"},
        },
    )
    paths = []
    for name in ["m000.spc", "m001.spc"]:
        path = tmp_path / name
        shutil.copy2(DATA / name, path)
        paths.append(path)
    tool = BurstSelectionTool(embedded=True, show_filter_plot=True, show_burst_plot=True)
    cp.reset_gaps()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", cp.ChiplotPassthroughWarning)
            tool._apply_detector_setup("plot-proof")
            tool._add_paths(paths)
            settings = tool._settings_from_controls()
            result = tool._client.analyze_files(
                paths,
                settings=asdict(settings),
                windows=tool.wizard.windows,
                detectors=tool.wizard.detectors,
                filetype=tool._selected_filetype,
                legacy_output=True,
                selected_setup=tool.wizard.comboBox.currentText(),
                legacy_parameters=tool._legacy_parameters(),
                mmfdb=None,
            )
            assert {
                k: v for k, v in result["metadata"].items() if k != "output_folder"
            } == REFERENCE["metadata"]
            tool._analysis_finished(result, settings)
            tool.resize(1400, 1000)
            tool.show()
            tool.repaint()
            tool.grab()
            # The legacy reference is the actual visible-window preview, not the full table.
            tool._display_view_model.set_diagnostic_window(10.0, 0.0)
            tool._display_view_model.show_time_window(0.0, 10.0)
            tool._on_filter_settings_changed()
            tool.host.hide()
            tool.dock_area.show()
            qapp.processEvents()
            tool.update_burst_plots()
            for name, expected in REFERENCE["panes"].items():
                plot = getattr(tool, name + "_plot")
                assert isinstance(plot, cp.Plot)
                actual = _items(plot)
                assert len(actual) == len(expected["items"]), name
                for observed, frozen in zip(actual, expected["items"]):
                    assert observed["kind"] == frozen["kind"]
                    for key in ["x", "y", "height"]:
                        if key in frozen:
                            values = np.asarray(observed[key], dtype=np.float64)
                            assert list(values.shape) == frozen[key]["shape"]
                            assert (
                                hashlib.sha256(values.tobytes()).hexdigest()
                                == frozen[key]["sha256"]
                            ), (
                                name,
                                key,
                                float(values.sum()),
                                tool.plot_min_spin.value(),
                                tool.plot_max_spin.value(),
                            )
                    if "width" in frozen:
                        np.testing.assert_allclose(
                            observed["width"], frozen["width"], rtol=0, atol=1e-12
                        )
                    if "text" in frozen:
                        assert observed["text"] == frozen["text"]
                canvas = plot._canvas
                if backend == "emtk":
                    assert [canvas._log["x"], canvas._log["y"]] == expected["log"]
                    for side, labels in expected["labels"].items():
                        assert canvas._labels[side] == labels["text"]
                        assert canvas._units.get(side, "") == labels["units"]
                else:
                    assert [
                        canvas._pi.ctrl.logXCheck.isChecked(),
                        canvas._pi.ctrl.logYCheck.isChecked(),
                    ] == expected["log"]
                    for side, labels in expected["labels"].items():
                        axis = canvas._pi.getAxis(side)
                        assert (
                            axis.labelText == labels["text"] and axis.labelUnits == labels["units"]
                        )
            assert not cp.passthrough_gaps()
    finally:
        for name in REFERENCE["panes"]:
            getattr(tool, name + "_plot").close()
        tool.close()
        qapp.processEvents()
