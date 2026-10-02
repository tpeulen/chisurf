"""Populate historical genuine Qt calibration via the bounded reference harness."""

from pathlib import Path

root = Path(__file__).resolve().parents[5]
harness = root / "tools/emtk_migration/capture_qt_references.py"
source = harness.read_text()
needle = "            widget = factory()\n"
injection = """            widget = factory()
            if module_name == "chisurf.plugins.microscopy.img_calibration.gui.tool":
                import numpy as np
                model = widget.model
                model.apply_setup_settings({"detectors": {"green": {"chs": [0,1], "ch_p": [0], "ch_s": [1]}, "red": {"chs": [2,3]}}})
                model.filename = "Reference FLIM source.ptu"
                model.sel_irf_files = ["Reference IRF.ptu"]
                x = np.arange(256)
                vv = 3 + 900*np.exp(-np.maximum(x-35,0)/42)*(x>=35)
                vh = 2 + 450*np.exp(-np.maximum(x-35,0)/32)*(x>=35)
                model._hist_cache[model._hist_key()] = {"n":256,"data":vv+vh,"data_vv":vv,"data_vh":vh,"irf_vv_raw":3+300*np.exp(-((x-35)/5)**2),"irf_vh_raw":2+200*np.exp(-((x-38)/6)**2)}
                model.set_conv_range(32,220)
                model.set_irf_range(20,65)
                model.set_bg_range(0,20)
                widget.auto_form.sync_fields()
                widget.auto_form.refresh_plots()
"""
assert needle in source
source = source.replace(needle, injection)
# Child command must invoke this populated harness rather than the generic file.
source = source.replace("str(Path(__file__).resolve()),", repr(str(Path(__file__).resolve())) + ",")
exec(compile(source, str(harness), "exec"), {"__name__": "__main__", "__file__": str(harness)})
