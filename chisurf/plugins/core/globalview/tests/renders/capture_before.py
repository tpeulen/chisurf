"""Capture the legacy Global View in a realistic state: three linked fits."""
import json, os, pathlib, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = pathlib.Path(__file__).parent
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/test")
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/test/gui")
import numpy as np
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import chisurf as cs
import chisurf.core.data, chisurf.core.fitting.fit, chisurf.core.models.parse
from chisurf.core.api._client import ChisurfClient
from chisurf.server.startup import ensure_embedded_chisurf_rpc_server
from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
import chisurf.core.settings as cs_settings

cfg = cs_settings.cs_settings.get("mmfdb", {})
from chisurf.server.startup import session_state_from_live_chisurf
ensure_embedded_chisurf_rpc_server(str(cfg.get("rpc_host", "127.0.0.1")),
                                   int(cfg.get("cmd_port", 8765)), int(cfg.get("pub_port", 8766)),
                                   state=session_state_from_live_chisurf())
client = ChisurfClient(cmd_port=int(cfg.get("cmd_port", 8765)), pub_port=int(cfg.get("pub_port", 8766)),
                       host=str(cfg.get("rpc_host", "127.0.0.1")), timeout_ms=2000)
client.connect(); client.call("meta.ping", {})
install_fitting_client(client)

x = np.linspace(0.0, 5.0, 32)
fits = []
for k in range(3):
    y = 3.1 + (1.0 + 0.1 * k) * x ** 2
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * 0.05)
    data.name = f"dataset {k + 1}"
    fit = chisurf.core.fitting.fit.Fit(model_class=chisurf.core.models.parse.ParseModel, data=data)
    fit.model.func = "c+a*x**2"
    fit.model.find_parameters()
    cs.fits.append(fit)
    fits.append(fit)
master = fits[0].model.parameters_all_dict["a"]
for f in fits[1:]:
    f.model.parameters_all_dict["a"].link = master
fits[2].model.parameters_all_dict["c"].fixed = True

from chisurf.plugins.core.globalview.gui.tool import GraphWizard
w = GraphWizard()
w.resize(1100, 760); w.show()
for _ in range(20): app.processEvents()
if hasattr(w, "refresh"): w.refresh()
for _ in range(20): app.processEvents()
import migration_parity as mp
path = mp.capture(w, "globalview", "before", out_dir=OUT, width=1100, min_height=760)
inv = mp.control_inventory(w)
(OUT / "globalview_before_inventory.json").write_text(json.dumps(inv, indent=1, default=str))
print(path)
print(json.dumps(inv, default=str)[:1500])
# Every dock, grabbed on its own at the right-hand panel size.
w.graph_widget.set_selection if hasattr(w.graph_widget, "set_selection") else None
for name, panel in [("parameters", w.parameters_form),
                    ("view", w._combo_layout.window() and w._combo_layout.parentWidget().parentWidget()),
                    ("selection", w._selection_hint.parentWidget())]:
    panel.show(); panel.resize(650, 700)
    for _ in range(10): app.processEvents()
    panel.grab().save(str(OUT / f"globalview.before.{name}.png"))
    print(name, OUT / f"globalview.before.{name}.png")
# Selection in its realistic state: the master a and a follower selected.
objs = w.node_data.get("objects", [])
names = [getattr(o, "name", None) for o in objs]
print("nodes", names, w.node_data.get("owners"))
pick = [i for i, n in enumerate(names) if n == "a"][:2]
w.graph_widget._selected = pick
w.callback_selection()
panel = w._selection_hint.parentWidget(); panel.resize(650, 700)
for _ in range(10): app.processEvents()
panel.grab().save(str(OUT / "globalview.before.selection.png"))
