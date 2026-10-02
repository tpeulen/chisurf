"""Capture both frontends with the same real bead FLIM fit (synthetic IRF)."""

from pathlib import Path

from chisurf.plugins.microscopy.img_pixel_mle.core import fit_pixel_lifetimes_from_file
from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel
from chisurf.plugins.microscopy.img_pixel_mle.test.test_pixel_mle_core import _FLIM_PTU, _settings

output = Path(__file__).with_name("artifacts")
output.mkdir(exist_ok=True)
model = PixelMleViewModel()
model.files = [str(_FLIM_PTU)]
model.irf_files = ["Synthetic Gaussian IRF, 256 bins"]
model.channels_perpendicular_text = "1"
model.micro_time_binning = 8
settings = _settings(convolution_stop=-1)
settings.period = model._period_ns(str(_FLIM_PTU), 8)
model.results = [fit_pixel_lifetimes_from_file(str(_FLIM_PTU), settings)]
model.result_names, model.result_paths = ["beads"], [str(_FLIM_PTU)]
model.current_result_name = "beads"

from emtk.pil_painter import PilPainter

from chisurf.plugins.microscopy.img_pixel_mle.gui.app import make_app

app = make_app(model=model)
for _ in range(3):
    painter = PilPainter(1200, 800)
    app.draw(painter, 0, 0, 1200, 800)
painter.frame.save(output / "native.png")

from qtpy import QtWidgets

from chisurf.plugins.microscopy.img_pixel_mle.gui.tool import ImgPixelMleTool

qtapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
widget = ImgPixelMleTool(view_model=model)
widget.resize(1200, 800)
widget.show()
for _ in range(10):
    qtapp.processEvents()
widget.auto_form.refresh_plots()
for _ in range(5):
    qtapp.processEvents()
widget.grab().save(str(output / "qt.png"))
from qtpy import QtCore

for tab in widget.findChildren(QtWidgets.QTabBar):
    for index in range(tab.count()):
        if "Lifetime" in tab.tabText(index):
            tab.setCurrentIndex(index)
for _ in range(5):
    qtapp.processEvents()
widget.grab().save(str(output / "qt-map.png"))
widget.close()
