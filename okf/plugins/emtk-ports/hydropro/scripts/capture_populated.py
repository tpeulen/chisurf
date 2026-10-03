"""Populated captures of the HYDROPRO tool: T4 lysozyme (148l.pdb) through the HYDROPRO stub executable.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix>   (run from the repo root)
The executable is scripts/hydropro10_stub.sh (HYDROPRO is a separate download, not installed): it writes a
report with a FIXED stub value, 1.000E-06 cm2/s. HOME points into a temp folder, because run_hydro works in
~/.hydropp_gui by default; the Qt tool's _save_persisted is disabled, because QSettings on macOS writes the real
user preferences whatever HOME says (the first baseline run did: see REPORT / board).
"""
import importlib, os, pathlib, sys, tempfile, time

TMP = pathlib.Path(tempfile.mkdtemp(prefix="hydropro_capture_"))
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401  (first: it must win the name "test" over the stdlib package)
from chisurf.plugins.modelling.hydropro.test import hermetic  # noqa: E402

os.environ.update(hermetic.env_for(TMP))      # HOME, CHISURF_SETTINGS_DIR, MMFDB_* all inside TMP

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
STUB = str(hermetic.install_fake_exe(TMP / "bin"))   # fake executable: replies with recorded output, computes nothing
PDB = str(pathlib.Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve())

if which == "qt":
    from qtpy import QtWidgets
    hermetic.isolate(TMP)   # QSettings -> INI in TMP, before any QSettings object exists (the real plist is never written)
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.modelling.hydropro.gui.tool import HydroProTool
    w = HydroProTool()
    # _save_persisted runs for real, into the isolated INI file (the persistence round trip is part of the checks).
    assert str(TMP) in w._qsettings.fileName(), w._qsettings.fileName()
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
    print("QSETTINGS", w._qsettings.fileName())
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
