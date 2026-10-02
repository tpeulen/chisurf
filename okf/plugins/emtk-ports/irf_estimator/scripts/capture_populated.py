"""Populated captures of the IRF estimator on a measured donor decay.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
Data: test/data/tcspc/Jordi_FRETsens/Donor/D0_14_TAC1024_DexDem.dat (VV/VH, 2 x 1024 channels, no dt in the
file -> 1 ns/channel); the file's background estimate (median of the last 10 %), RL iterations 100, estimated.
qt = the committed Qt tool (HEAD gui/tool.py via qt_head).
"""
import importlib, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
DECAY = str(pathlib.Path("test/data/tcspc/Jordi_FRETsens/Donor/D0_14_TAC1024_DexDem.dat").resolve())
ITERATIONS = 100

if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("irf_estimator")
    w = klass()
    w.load_decay_file(DECAY)
    w.rl_iterations_spinbox.setValue(ITERATIONS)
    w.range_selection_checkbox.setChecked(True)
    w.estimate_irf()
    w.resize(1200, 800); w.show()
    for _ in range(40):
        qapp.processEvents(); time.sleep(0.02)
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.lifetime_value.text(), w.decay_rate_value.text(), w.amplitude_value.text(), w.offset_value.text(),
          w.background_spinbox.value(), w.status_time_label.text())
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("irf_estimator")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        a.model.load_file(DECAY)
        a.model.rl_iterations = ITERATIONS
        a.model.use_range_selection = True
        a.start_estimate()
        a.future.result(timeout=120)
        for _ in range(4):
            a.draw(RecordingPainter(), 0, 0, *size)
        if which == "emtk-states" and hasattr(a, "tour"):
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        r = a.model.result
        print("EMTK", r.lifetime_ns, r.decay_rate_ns, r.amplitude, r.offset, a.model.manual_background)
        getattr(a, "close", lambda: None)()
