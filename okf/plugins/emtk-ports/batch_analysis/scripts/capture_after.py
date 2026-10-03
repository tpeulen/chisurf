"""Populated screenshots of the native Batch Analysis at both sizes: every step, the file dialog, Help and a tour card.

Usage: python capture_after.py <out dir>  (temp HOME / settings are set by the caller)
"""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui.emtk_port_parity import emtk_screenshot  # noqa: F401  (before the working directory changes)
from chisurf.plugins.core.batch_analysis.gui.app import BatchAnalysisApp
from chisurf.plugins.core.batch_analysis.gui.model import BatchModel
from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession
from chisurf.plugins.emtk_test_input import Driver

out = pathlib.Path(sys.argv[1]).resolve(); out.mkdir(parents=True, exist_ok=True)
tmp = pathlib.Path(tempfile.mkdtemp())
for n in ("run_01.sm", "run_02.sm", "run_03.sm"):
    (tmp / n).write_text("x")
import os; os.chdir(tmp)
NAMES = ["welcome", "datasets", "files", "run", "results"]
for size in ((1200, 800), (800, 600)):
    s = f"{size[0]}x{size[1]}"
    app = BatchAnalysisApp(BatchModel(session=FakeSession(fits=("Template fit", "Second fit"))))
    d = Driver(app, size); d.draw(3)
    m = app.model
    m.add_paths([str(tmp)])
    m.set_dataset_use(m.dataset_rows()[0], "use", True); m.set_dataset_use(m.dataset_rows()[2], "use", True)
    m.save_path = str(tmp / "results.csv")
    for i, name in enumerate(NAMES):
        if name == "results":
            m.go_to(3); m.run(); m.wait()
        m.go_to(i); d.screenshot(out / f"after_populated_{i+1}_{name}_{s}.png")
    m.go_to(2); d.click_name("add_files"); d.screenshot(out / f"after_file_dialog_{s}.png"); d.click_text("Cancel")
    d.click_name("help"); d.screenshot(out / f"after_help_{s}.png"); d.escape()
    m.go_to(2); d.click_name("guide"); d.screenshot(out / f"after_tour_{s}.png")
    app.tour.stop(); m.go_to(3); m.message=""; m.files=[]; m.save_path=""; d.click_name("run"); d.screenshot(out / f"after_no_data_{s}.png")
