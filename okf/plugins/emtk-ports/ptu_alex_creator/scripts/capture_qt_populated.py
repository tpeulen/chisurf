"""Populated Qt baseline of the ALEX Creator (temp HOME/settings; run from the repo root)."""
import os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tmp = Path(tempfile.mkdtemp(prefix="alexqt_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
import tttrlib
from qtpy import QtWidgets
out = Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
src = tmp / "source.ptu"
tttrlib.TTTR("test/data/clsm/Leica_SP5.ptu")[:5000].write(str(src))
second = tmp / "second.ptu"; second.write_bytes(src.read_bytes())
from chisurf.plugins.tttr.ptu_alex_creator.gui.tool import AlexPTUCreator
w = AlexPTUCreator(); w.resize(1200, 800); w.show()
def spin(n=20):
    for _ in range(n): app.processEvents(); time.sleep(0.01)
spin()
w.model.alex_period = 4000; w.model.period_shift = 23
sec = w.auto_form.findChildren(QtWidgets.QWidget)
edit = [e for e in w.auto_form.findChildren(QtWidgets.QLineEdit) if "TTTR" in e.placeholderText()][0]
w.model.load(str(src)); w.model.notify("loaded"); w.model.notify("plot"); spin()
w.model.add_batch_files([str(src), str(second)]); w.model.batch_output_folder = str(tmp / "out"); spin()
w.auto_form.sync_fields(); w.auto_form.refresh_plots(); spin()
bars = w.findChildren(QtWidgets.QTabBar)
for size in ((1200, 800), (800, 600)):
    w.resize(*size); spin()
    for i, name in enumerate(("controls", "histogram", "batch")):
        for b in bars: b.setCurrentIndex(i)
        spin(); w.grab().save(str(out / f"before_populated_{name}_{size[0]}x{size[1]}.png"))
# every tool button of the window, for the checklist
btns = sorted({b.text() + " | " + b.toolTip() for b in w.findChildren(QtWidgets.QToolButton)})
print("\n".join(btns))
