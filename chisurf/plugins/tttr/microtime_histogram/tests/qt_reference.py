"""Runs the Qt Histogram-Microtime wizard on BH_SPC132.spc in a throw-away process and prints a JSON reference.

usage: python qt_reference.py <repo> <out.npz>
Configurations: default (green detector), binning 4 with VV/VH shifts and a G-factor. Needs QT_QPA_PLATFORM=offscreen and a
temporary HOME / CHISURF_SETTINGS_DIR (the caller's job).
"""

import json
import pathlib
import sys
import tempfile

repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo))
import numpy as np  # noqa: E402
from qtpy import QtWidgets  # noqa: E402

import test.gui.emtk_port_parity  # noqa: E402,F401  (before the plugin import)

app = QtWidgets.QApplication([])
from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram  # noqa: E402

out = {}
arrays = {}
for name, binning, vv, vh, g in (("default", "1", 0, 0, "1.0"), ("shifted", "4", 3, -2, "1.25")):
    w = MicrotimeHistogram()
    w.listWidget.add_paths([str(repo / "test/data/tttr/BH/132/BH_SPC132.spc")])
    w.comboBox_2.setCurrentText(binning)
    w.spinBox_timeshift_vv.setValue(vv)
    w.spinBox_timeshift_vh.setValue(vh)
    w.lineEdit_gfactor.setText(g)
    w.lineEdit_5.setText(
        str(pathlib.Path(tempfile.mkdtemp()) / "decay.dat")
    )  # after the signals that rename it
    w.compute_microtime_histogram()
    arrays[name] = np.asarray(w.cumulative_ps)
    out[name] = {
        "parallel": w.parallel_channels,
        "perpendicular": w.perpendicular_channels,
        "detector": w.current_detector_name,
        "setup": w.detector_wizard_page.detectors.get(w.current_detector_name),
        "binning": int(binning),
        "vv": vv,
        "vh": vh,
        "g": float(g),
        "fwhm_text": w.lineEdit_fwhm.text(),
        "output_name": pathlib.Path(w.lineEdit_5.text()).name,
    }
np.savez(sys.argv[2], **arrays)
print("JSON" + json.dumps(out))
