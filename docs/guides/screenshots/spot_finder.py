"""Spot Finder screenshots on a real HT3 confocal image (mGBP puncta in a MEF cell)."""
import sys, pathlib
from qtpy.QtWidgets import QApplication, QTabBar
app = QApplication.instance() or QApplication([])
import chisurf.core.settings  # noqa
S = pathlib.Path(__import__("tempfile").mkdtemp(prefix="chisurf_grab_"))
FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
MGBP = __import__("os").path.expanduser(__import__("os").environ.get("CHISURF_TTTR_DATA", "~/dev/tttr-data")) + "/imaging/pq/ht3/58 MEF ko mGBP7 + GFP-mGBP7 + mCherry-mGBP6 + IFNg_green.ht3"

def _grab(w, name):
    w.show(); QApplication.processEvents(); w.grab().save(str(FIG / name)); print("wrote", name)

def raise_tab(tool, title):
    for bar in tool.findChildren(QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == title:
                bar.setCurrentIndex(i)
    QApplication.processEvents()

def _grab_spot_finder():
    from chisurf.plugins.microscopy.spot_finder.gui.tool import SpotFinderTool
    tool = SpotFinderTool()
    m = tool.model
    m.files = [MGBP]
    m.workflow = "camera_spots"
    m.settings.threshold = 50.0          # in image units: see guide 84
    m.settings.max_sigma = 4.0
    m.name = "puncta"
    m.preview()
    tool.resize(1500, 950)
    tool.show(); tool._refresh(); tool._refresh_region_overlays(); QApplication.processEvents()
    print(m.status_text)
    raise_tab(tool, "Regions"); tool._refresh(); QApplication.processEvents()
    _grab(tool, "spot_finder_regions.png")
    raise_tab(tool, "Detection")
    from qtpy.QtWidgets import QAbstractButton
    for b in tool.findChildren(QAbstractButton):
        if any(k in b.text() for k in ("Spot width", "Filters")):
            b.click()
    QApplication.processEvents(); tool._refresh(); QApplication.processEvents()
    _grab(tool, "spot_finder_detection.png")

def _grab_spot_finder_hub():
    from chisurf.plugins.microscopy.imaging_tools.gui.tool import ImagingToolsTool
    hub = ImagingToolsTool()
    hub.resize(1500, 950); hub.show(); QApplication.processEvents()
    # select the Spot Finder entry in the navigation list
    from qtpy.QtWidgets import QListWidget
    for lw in hub.findChildren(QListWidget):
        for i in range(lw.count()):
            if "Spot Finder" in lw.item(i).text():
                lw.setCurrentRow(i)
    QApplication.processEvents()
    _grab(hub, "spot_finder_hub.png")

if __name__ == "__main__":
    for name in sys.argv[1:] or ["_grab_spot_finder", "_grab_spot_finder_hub"]:
        globals()[name]()
