"""Native FCS hub, the Qt baseline's state: BH_SPC132.spc ticked, the photon filter on, two chunks correlated, every rail
row visited. usage: capture_emtk.py <out_dir>

Writes ``after_<role>_<W>x<H>.png`` for every row at 1200x800 and 800x600 and ``after.json`` (union of the control
inventory over the rows, every interactive control with its tooltip, Qt-free check).
"""

import json
import os
import pathlib
import sys
import tempfile

out = pathlib.Path(sys.argv[1])
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
SPC = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"
# the repo's test.gui first: a chisurf import loads the standard library's ``test`` package otherwise
from test.gui import emtk_port_parity as epp  # noqa: E402, I001
from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app  # noqa: E402

SIZES = ((1200, 800), (800, 600))
app = make_app()
app.files_step.add_paths([str(SPC)])
app.files_step.use_filter = True
app.files_step.changed()
controls, rows, roles = set(), [], []
for panel in app.tools:
    role = panel["role"]
    app.select(role, by_user=False)
    if role == "correlator":
        app.correlator_model.n_splits = 2
        app.child.correlate(wait=True)
    for size in SIZES:
        epp.emtk_screenshot(app, out / f"after_{role}_{size[0]}x{size[1]}.png", size)
    inv = epp.emtk_inventory(app, SIZES[0])
    controls |= set(inv["controls"])
    rows += inv["interactive"]
    roles.append(role)
    print(role, len(inv["controls"]), inv["controls_without_tooltip"][:8])
seen, uniq = set(), []
for r in rows:
    if (r["kind"], r["label"]) not in seen:
        seen.add((r["kind"], r["label"]))
        uniq.append(r)
after = {"size": list(SIZES[0]), "states": roles, "controls": sorted(controls), "interactive": uniq,
         "controls_without_tooltip": sorted({f"{r['kind']}: {r['label']}" for r in uniq if not r["tooltip"]}),
         "qt_free": epp.qt_free("fcs_toolbox")}
(out / "after.json").write_text(json.dumps(after, indent=2, ensure_ascii=False))
print("correlations", len(app.correlator_model._correlations), "errors", app.errors)
app.close()
