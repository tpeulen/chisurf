"""Populated captures of the FCS confocal calculator.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix>   (run from the repo root)
State: tau 120 us, T 25 C, conc 2 nM, then the reference dye "ATTO 655 (COOH)" applied with T/eta scaling
(which switches to Fix D), then the shape set to Ellipsoid. qt = the committed Qt widget (wizard.py at HEAD).
"""
import importlib, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
DYE = "ATTO 655 (COOH)"

if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget
    w = ConfocalCalcWidget()
    w.tau_us.setValue(120.0)
    w.temp_C.setValue(25.0)
    w.conc_nM.setValue(2.0)
    w.dye_combo.setCurrentText(DYE)
    w.btn_apply_dref.click()
    w.shape_combo.setCurrentText("Ellipsoid")
    w.resize(820, 900); w.show()
    for _ in range(40):
        qapp.processEvents(); time.sleep(0.02)
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", {k: v for k, v in w._collect_settings().items()})
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("fcs_calculator")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        for name, value in (("tau_us", 120.0), ("temp_C", 25.0), ("conc_nM", 2.0)):
            setattr(a.model, name, value)
            a.edited(name)
        a.dye = DYE
        a.apply_dye()
        a.shape = 1
        for _ in range(4):
            a.draw(RecordingPainter(), 0, 0, *size)
        if which == "emtk-states" and hasattr(a, "tour"):
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.settings())
        getattr(a, "close", lambda: None)()
