"""Populated captures of the HYDROPRO tool: T4 lysozyme (148l.pdb) through the HYDROPRO stub executable.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix>   (run from the repo root)
The executable is scripts/hydropro10_stub.sh (HYDROPRO is a separate download, not installed): it writes a
report with a FIXED stub value, 1.000E-06 cm2/s. HOME points into a temp folder, because run_hydro works in
~/.hydropp_gui by default; the Qt tool's _save_persisted is disabled, because QSettings on macOS writes the real
user preferences whatever HOME says (the first baseline run did: see REPORT / board).
"""
import importlib, os, pathlib, sys, tempfile, time

HOME = tempfile.mkdtemp()
os.environ["HOME"] = HOME
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
STUB = str(pathlib.Path(__file__).with_name("hydropro10_stub.sh").resolve())
PDB = str(pathlib.Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve())

if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.modelling.hydropro.gui.tool import HydroProTool
    w = HydroProTool()
    # Run would store the settings (and the stub path) in the user's real QSettings
    # (macOS CFPreferences ignores HOME): never let a capture write them.
    w._save_persisted = lambda: None
    w._model.exe_path, w._model.struct_files, w._model.indmode = STUB, PDB, "1"
    w._form.rebuild(); w._refresh_table_files()
    w._on_run()
    for _ in range(200):
        qapp.processEvents(); time.sleep(0.02)
        if w._thread is None:
            break
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents(); time.sleep(0.02)
    w.grab().save(str(out / f"{prefix}.png"))
    if w._out_dlg is not None:
        w._out_dlg.grab().save(str(out / f"{prefix}_output.png"))
    print("QT", w._model.status, [w.table.item(0, c).text() for c in range(2)])
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("hydropro")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        a.exe_path, a.struct_files, a.indmode = STUB, PDB, "1"
        start = getattr(a, "start_run", None) or a._run
        start()
        end = time.monotonic() + 60
        while getattr(a, "future", None) is not None and time.monotonic() < end:
            a.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.02)
        for _ in range(4):
            a.draw(RecordingPainter(), 0, 0, *size)
        if which == "emtk-states" and hasattr(a, "tour"):
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.status)
        getattr(a, "close", lambda: None)()
