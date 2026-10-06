"""Ordinary PDA plot construction must not require the optional metadata catalog."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("catalog", ["normal", "absent", "import_error", "assertion"])
def test_real_pda_plots_and_metadata_in_fresh_process(catalog, tmp_path):
    """Resolve every declared plot, open it, and preserve exact numerical state."""
    source = r"""
import importlib.abc
import sys
from pathlib import Path

catalog, captures = sys.argv[1:]
if catalog != "normal":
    class NoMMFDB(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                if catalog == "import_error":
                    raise ImportError("Deliberate optional catalog import rejection")
                if catalog == "assertion":
                    raise AssertionError("Deliberate optional catalog assertion rejection")
                raise ModuleNotFoundError("Optional MMFDB absent", name=fullname)
    sys.meta_path.insert(0, NoMMFDB())

import numpy as np
from qtpy import QtWidgets
from chisurf.gui.widgets.models.model_editor import model_plot_specs
from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow
from chisurf.core.data import DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
sys.path.insert(0, str(Path("test/gui").resolve()))
from test_pda2c_model_editor import _make_pda_data

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
group = FitGroup(data=DataCurveGroup([_make_pda_data()]), model_class=Pda2cSimpleModel)
member = group[0]
member.model.parameters_all_dict["p01"].value = 0.61
member.model.parameters_all_dict["bg0"].value = 0.001
# Use a fully specified state: unestimated NaN errors cannot be compared with
# Python dictionary equality. Keep the exact state assertion below unchanged.
for parameter in member.model.parameters_all:
    parameter.error_estimate = 0.125
member.model.update()
before_y = np.array(member.model.y, copy=True)
before_data = np.array(member.data.y, copy=True)
before_state = member.model.get_state()
metadata = {"_unregistered.lab_key": "stored arbitrary value", "pH": "7.4"}
group.flr_metadata = dict(metadata)
declared = member.model.view_spec().plots
assert [spec.key for spec in declared] == [
    "distribution", "residual", "residual2d", "fit_info", "parameter_scan"
]
specs = model_plot_specs(member.model)
from chisurf.gui.widgets.models.model_editor import FIT_PLOT_KEYS
assert len(specs) == len(declared) + len(FIT_PLOT_KEYS), (len(specs), len(declared))

controls = QtWidgets.QWidget()
control_layout = QtWidgets.QVBoxLayout(controls)
window = FitSubWindow(group, control_layout)
window.close_confirm = False
host = QtWidgets.QWidget()
layout = QtWidgets.QHBoxLayout(host)
layout.addWidget(window, 3)
layout.addWidget(controls, 2)
host.resize(1200, 800)
host.show()
app.processEvents()
assert len(window._plot_specs) == len(declared) + len(FIT_PLOT_KEYS)
for i, (plot_class, options) in enumerate(specs):
    plot = window.ensure_plot_created(i)
    assert type(plot) is plot_class, (i, type(plot), plot_class)
    assert window.ensure_plot_created(i) is plot
    window.plot_tab_widget.setCurrentIndex(i)
    plot.update()
    app.processEvents()
    key = declared[i].key if i < len(declared) else None  # then the fit-level pages
    if key == "distribution":
        config = plot.options
        expected = config["accessor"](group, **config.get("accessor_kwargs", {}))
        traces = plot.distribution_plot.series()
        assert len(traces) >= 2
        for (_, handle), (y, x) in zip(traces[:2], expected[:2], strict=True):
            actual_x, actual_y = handle.get_data()
            np.testing.assert_array_equal(actual_x, x)
            np.testing.assert_array_equal(actual_y, y)
            assert np.isfinite(actual_y).all() and np.any(actual_y != 0)
    if key == "fit_info":
        editor = plot.metadata_editor
        assert editor.as_dict() == metadata
        # The stored, unregistered key is offered by the key catalogue.
        assert "_unregistered.lab_key" in editor.catalogue()
        row = editor.metadata_rows()[0]
        editor.select_row(row)
        editor.detail_key = "_unregistered.edited_key"
        editor.edited(row, "value", "edited stored value")
        edited = {"_unregistered.edited_key": "edited stored value", "pH": "7.4"}
        assert editor.as_dict() == edited
        assert group.flr_metadata == edited
        plot.tabs.select(plot.TABS.index("Metadata"))
        window.show_plot_settings()
        app.processEvents()
    for size in ((1200, 800), (800, 600)):
        host.resize(*size)
        app.processEvents()
        path = Path(captures) / f"{catalog}-pda-{key or type(plot).__name__}-{size[0]}x{size[1]}.png"
        assert host.grab().save(str(path))
        print("capture", path, flush=True)

np.testing.assert_array_equal(member.model.y, before_y)
np.testing.assert_array_equal(member.data.y, before_data)
assert member.model.get_state() == before_state, (before_state, member.model.get_state())
assert len(window._created_plots) == len(declared) + len(FIT_PLOT_KEYS)
if catalog != "normal":
    assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
print("all five real PDA plots opened; exact model, data and traces preserved", catalog)
window.close()
controls.close()
host.close()
app.processEvents()
"""
    capture_dir = Path(os.environ.get("CHISURF_OPTIONAL_PLOT_CAPTURES", tmp_path))
    capture_dir.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
    )
    result = subprocess.run(
        [sys.executable, "-c", source, catalog, str(capture_dir)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
