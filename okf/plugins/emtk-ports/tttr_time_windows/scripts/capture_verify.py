"""Verification pass screenshots: dropped folder, failed process on the status line, guide waiting for a press."""
import pathlib, sys, tempfile
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app

out = pathlib.Path(sys.argv[1])
ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()

def shot(app, name, size=(1200, 800)):
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"{name}_{size[0]}x{size[1]}.png", size)

def wait(app):
    t = app.tool
    if t.job.future is not None:
        try: t.job.future.result(timeout=300)
        except Exception: pass
    app.draw(RecordingPainter(), 0, 0, 1200, 800)

app = create_app(); t = app.tool
folder = pathlib.Path(tempfile.mkdtemp()) / "measurements"; folder.mkdir()
(folder / "notes.txt").write_text("x")
print("drop folder without TTTR:", app.files_dropped([str(folder)]), "|", t.message)
shot(app, "verify_drop_nothing")
(folder / "Leica_SP5.ptu").symlink_to(ptu)
print("drop folder with TTTR:", app.files_dropped([str(folder)]), [p.name for p in t._file_paths])
wait(app); wait(app)
shot(app, "verify_drop_folder"); shot(app, "verify_drop_folder", (800, 600))
t.output_dir_text = "/proc/forbidden/out"; t.time_window_ms = 10000.0
t._process_all(); wait(app); wait(app)
print("failed process:", t.message, "|", t._log_lines[-1][:100])
shot(app, "verify_process_failed")
app.start_guide(); shot(app, "verify_guide_await_files")
app.close()
