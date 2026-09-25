"""The Global View's parity captures: the emtk window in the baseline's state.

Three parse fits ``c + a x**2`` share ``a`` (the second and third follow the
first) and the third holds ``c`` -- the state the legacy window was captured in
(``chisurf/plugins/core/globalview/tests/renders/globalview.before*.png``, by the
version of this script in commit 635ea02a3, which drove widgets that no longer
exist). Writes the after-images and the control inventory beside them:

    QT_QPA_PLATFORM=offscreen python test/gui/globalview_parity_capture.py
"""

import json
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = pathlib.Path(__file__).resolve().parents[2] / "chisurf/plugins/core/globalview/tests/renders"
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/test")
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/test/gui")
import numpy as np
from qtpy import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse

x = np.linspace(0.0, 5.0, 32)
fits = []
for k in range(3):
    y = 3.1 + (1.0 + 0.1 * k) * x**2
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * 0.05)
    data.name = f"dataset {k + 1}"
    fit = chisurf.core.fitting.fit.Fit(model_class=chisurf.core.models.parse.ParseModel, data=data)
    fit.model.func = "c+a*x**2"
    fit.model.find_parameters()
    fits.append(fit)
master = fits[0].model.parameters_all_dict["a"]
for f in fits[1:]:
    f.model.parameters_all_dict["a"].link = master
fits[2].model.parameters_all_dict["c"].fixed = True

from chisurf.plugins.core.globalview.gui.tool import GraphWizard

w = GraphWizard(fit_list=fits, remember_layout=False)
w.resize(1100, 760)
w.show()


def pump(n=6):
    for _ in range(n):
        app.processEvents()
        w.host.repaint()


pump()
w.host.grab().save(str(OUT / "globalview.after.png"))
# Selection: the master a and a follower.
ids = [n.id for n in w.model.control.document.nodes if n.title == "a"][:2]
w.model.selection = ids
w.surface.docks.focus("Selection")
pump()
w.host.grab().save(str(OUT / "globalview.after.selection.png"))
w.surface.docks.focus("Parameters")
w.surface.docks.focus("View")
pump()
w.host.grab().save(str(OUT / "globalview.after.parameters.png"))
w.model.representation = "factor graph"
w.model.include_fixed = True
w.model.relayout()
w.surface.docks.focus("Network")
pump()
w.host.grab().save(str(OUT / "globalview.after.factors.png"))
print(w.model.status)
w.model.representation = "network"
w.model.include_fixed = False
w.model.relayout()
w.show_guide()
tour = w._guided_tour
tour.start(1)
pump()
app.processEvents()
w.grab().save(str(OUT / "globalview.after.tour.png"))
tour.stop()

# The inventory: every control the spec drew, every table column, every dock.
w.surface.docks.focus("Parameters")
w.surface.docks.focus("View")
pump()
w.surface.docks.focus("Network")
w.surface.docks.focus("Selection")
pump()
inventory = {
    "controls": sorted({n for f in w.surface.forms.values() for n in f.rects}),
    "columns": {
        name: [c.title for c in b.control.columns]
        for f in w.surface.forms.values()
        for name, b in f.tables.items()
    },
    "docks": [
        title
        for title, _region in __import__(
            "chisurf.plugins.core.globalview.gui.surface", fromlist=["DOCKS"]
        ).DOCKS
    ],
}
(OUT / "globalview_after_inventory.json").write_text(json.dumps(inventory, indent=1))
