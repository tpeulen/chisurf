"""Populated captures of the Qt hub (the committed CalculatorHub): every entry selected, a broken entry, no entries. Usage: <out_dir>."""
import json, pathlib, sys
from qtpy import QtWidgets
from chisurf.plugins.calculator.hub.core.registry import CalculatorEntry, default_calculators
from chisurf.plugins.calculator.hub.gui.tool import CalculatorHub

out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
hub = CalculatorHub(); hub.resize(1200, 800); hub.show()


def settle():
    for _ in range(40): app.processEvents()


report = {}
for row, entry in enumerate(default_calculators()):
    hub._list.setCurrentRow(row); settle()
    report[entry.id] = {"title": hub._title.text(), "subtitle": hub._subtitle.text(),
                        "page_widget": type(hub._stack.currentWidget()).__name__, "stack_count": hub._stack.count()}
    if entry.id in ("fret_calculator", "kappa2_dist", "phasor", "f_test", "psf_calculator"):
        hub.grab().save(str(out / f"before_populated_{entry.id}.png"))
report["items"] = hub._list.count()
hub.close()

broken = [CalculatorEntry(id="broken", label="Broken one", description="Cannot be built.", widget="chisurf.nowhere:Nothing", icon="X"),
          *default_calculators()[:1]]
hub = CalculatorHub(entries=broken); hub.resize(1200, 800); hub.show(); settle()
report["broken_first"] = {"title": hub._title.text(), "page_text": hub._stack.currentWidget().text() if hasattr(hub._stack.currentWidget(), "text") else None}
hub.grab().save(str(out / "before_populated_broken_entry.png"))
hub.close()
hub = CalculatorHub(entries=[]); hub.resize(1200, 800); hub.show(); settle()
report["empty"] = {"title": hub._title.text(), "subtitle": hub._subtitle.text(), "page_text": hub._stack.currentWidget().text()}
hub.grab().save(str(out / "before_populated_no_entries.png"))
(out / "qt_hub_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
print(json.dumps(report, indent=1, ensure_ascii=False)[:3000])
