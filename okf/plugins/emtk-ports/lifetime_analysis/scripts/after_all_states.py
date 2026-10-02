"""after.json over every hosted tool (the hub's own controls are the same on each), then `compare`. Usage: <out_dir>."""
import test.gui.emtk_port_parity as parity  # noqa (first: the stdlib "test" must not win)
import json, pathlib, sys, tempfile
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import make_app, PANELS
out = pathlib.Path(sys.argv[1]); app = make_app()
data = json.loads((out / "after.json").read_text()); controls = set(data["controls"]); rows = {r["id"]: r for r in data["interactive"]}
for ident, *_ in PANELS:
    app.select(ident); inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
    for r in inv["interactive"]: rows[r["id"]] = r
app.search = "zz"; inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
data["controls"] = sorted(controls); data["interactive"] = list(rows.values())
# the hosted tools' own controls are audited in their own reports: here only the hub's
hub = ("##search_tools", "Back", "Next", "Help", "Guide")
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip") and (r["id"] in hub or r["label"][:2] in ("1.", "2.", "3.", "4.", "5.")))
data["hosted_tools_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip") and r["label"] not in data["controls_without_tooltip"])
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)); print(len(controls), data["controls_without_tooltip"], len(data["hosted_tools_without_tooltip"]))
