"""Native intensity-trace tool in the Qt baseline's states: empty, BH_SPC132.spc loaded (a temp copy), both tabs, a
3-state HMM, the four result views. usage: capture_emtk.py <out_dir>

Writes after_<state>_<W>x<H>.png and after.json (union of the control inventory over the states, tooltips, Qt-free).
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile

out = pathlib.Path(sys.argv[1])
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
SPC = work / "BH_SPC132.spc"
shutil.copy(REPO / "test/data/tttr/BH/132/BH_SPC132.spc", SPC)
# the repo's test.gui first: a chisurf import loads the standard library's ``test`` package otherwise
from test.gui import emtk_port_parity as epp  # noqa: E402, I001
from chisurf.plugins.tttr.intensity_trace.gui.app import make_app  # noqa: E402

SIZES = ((1200, 800), (800, 600))
app = make_app()
controls, rows = set(), []


def state(name):
    for size in SIZES:
        epp.emtk_screenshot(app, out / f"after_{name}_{size[0]}x{size[1]}.png", size)
    inv = epp.emtk_inventory(app, SIZES[0])
    controls.update(inv["controls"])
    rows.extend(inv["interactive"])
    print(name, len(inv["controls"]), inv["controls_without_tooltip"][:6])


state("empty")
app.model.selected = ["routing_0"]
app.open_file(str(SPC))
app.wait()
state("processing")
app.form_model.request_edit_setup()
state("setup_editor")
app.tab = "HMM"
app.model.n_states = 3
app.compute_hmm()
app.wait()
state("hmm")
app.compute_bic()
app.wait()
for result in ("BIC Elbow", "Dwell Times", "HMM Matrix", "FRET Distributions"):
    app.show_result(result)
    state(result.lower().replace(" ", "_"))
seen, uniq = set(), []
for r in rows:
    if (r["kind"], r["label"]) not in seen:
        seen.add((r["kind"], r["label"]))
        uniq.append(r)
(out / "after.json").write_text(json.dumps({
    "size": list(SIZES[0]), "controls": sorted(controls), "interactive": uniq,
    "controls_without_tooltip": sorted({f"{r['kind']}: {r['label']}" for r in uniq if not r["tooltip"]}),
    "qt_free": epp.qt_free("intensity_trace")}, indent=2, ensure_ascii=False))
print(app.status)
app.close()
