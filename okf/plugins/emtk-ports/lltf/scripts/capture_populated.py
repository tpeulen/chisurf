"""Populated captures of Lazy Lifetime Analysis on the shipped example (5-44_D0.dat, IRF_D0.dat, config.yml), fitted.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt wizard (HEAD lltf_gui.py via qt_head); its fit subprocess inherits MPLBACKEND=Agg from here,
     without which the CLI's plt.show() blocks a headless run (the defect the port fixes in the wizard itself).
"""
import importlib, os, pathlib, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401  (before any plugin import)

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
EXAMPLE = pathlib.Path("chisurf/plugins/fluorescence_decay/lltf/example")
DECAY, IRF, CONFIG = (str((EXAMPLE / n).resolve()) for n in ("5-44_D0.dat", "IRF_D0.dat", "config.yml"))
work = pathlib.Path(tempfile.mkdtemp())

if which == "qt":
    os.environ["MPLBACKEND"] = "Agg"
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("lltf", ())
    w = klass()
    w.decay_file, w.irf_file, w.output_dir = DECAY, IRF, str(work)
    w.decay_file_edit.setText(DECAY); w.irf_file_edit.setText(IRF); w.output_dir_edit.setText(str(work))
    w.config_file_edit.setText(CONFIG)
    w.n_lifetimes_spin.setValue(2)
    w._update_fit_button_state()
    w.on_fit()
    end = time.monotonic() + 300
    while w.analysis_tab.running:
        assert time.monotonic() < end
        qapp.processEvents(); time.sleep(0.05)
    for _ in range(30):
        qapp.processEvents()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", [(round(r["lifetime"], 4), round(r["amplitude"], 4)) for r in (w.last_fit_result or {}).get("lifetimes", [])])
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("lltf")["entrypoints"]["emtk"].split(":")
    a = getattr(importlib.import_module(module), attr)()
    m = a.model
    m.decay_file, m.irf_file, m.output_dir, m.n_lifetimes = DECAY, IRF, str(work), 2
    m.load_config(CONFIG)
    a.start() if hasattr(a, "start") else m.start()
    end = time.monotonic() + 300
    while m.process is not None:
        assert time.monotonic() < end
        time.sleep(0.1); a.draw(RecordingPainter(), 0, 0, 1200, 800)
    for size in [(1200, 800), (800, 600)]:
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
    print("EMTK", [(round(r["lifetime"], 4), round(r["amplitude"], 4)) for r in (m.result or {}).get("lifetimes", [])])
    a.close()
