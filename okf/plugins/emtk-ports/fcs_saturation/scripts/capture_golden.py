"""Write the Qt tool's numbers for a handful of states to the golden file the emtk parity tests compare with.

usage: capture_golden.py <out.json>   (run from the repo root, on temporary settings; the Qt tool must be the committed one)
"""
import json, sys
import numpy as np
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.calculator.fcs_saturation_calc.gui.tool import SaturationCalculatorTool

STATES = {
    "default": {},
    "power_2mW": {"power_mW": 2.0},
    "power_0": {"power_mW": 0.0},
    "cy5_1mW": {"scheme_preset": "Cyanine 5 (4-state, isomer + triplet)", "power_mW": 1.0},
    "two_state_640_ms": {"scheme_preset": "Two-state (ground + excited)", "wavelength_nm": 640.0, "rate_unit": "1/ms", "power_mW": 0.5},
    "oxazine_normalised_nobunching": {"scheme_preset": "Oxazine 1 (3-state, triplet)", "normalize_fcs": True, "include_bunching": False, "power_mW": 0.3},
}
SERIES = ("fcs_curves_series", "fcs_residual_series", "volume_profile_series", "volume_power_series", "tau_d_power_series")

def clean(series):
    return [{"name": s["name"], "x": [float(v) for v in s["x"]], "y": [float(v) for v in s["y"]]} for s in series]

out = {}
for name, settings in STATES.items():
    tool = SaturationCalculatorTool()
    for key, value in settings.items():
        setattr(tool, key, value)
    sat = tool.saturation
    sat.find_parameters()
    out[name] = {
        "settings": settings,
        "series": {s: clean(getattr(tool, s)) for s in SERIES},
        "info": tool.info_text(),
        "state_labels": list(sat.state_labels),
        "dark": {k: float(p.value) for k, p in sat.dark.rates_by_name().items()},
        "exc": {k: float(p.value) for k, p in sat.exc.rates_by_name().items()},
        "brightness": [float(p.value) for p in sat.brightness._brightness],
        "parameters": [[p.name, float(p.value), bool(p.fixed), [None if b is None else float(b) for b in p.bounds], bool(p.bounds_on)] for p in sat._parameters],
    }
    tool.deleteLater()  # not close(): closing saves the session, which the next tool would restore into its state
json.dump(out, open(sys.argv[1], "w"))
print("states", list(out))
