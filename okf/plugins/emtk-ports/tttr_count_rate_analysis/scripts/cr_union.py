"""Union of the emtk inventory over every channel-editor section (the editor shows one at a time)."""
import json, sys, pathlib
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory
out = pathlib.Path(sys.argv[1]); pid = sys.argv[2]
app = build_emtk_app(pid)
editor = None
for obj in (getattr(app, "controller", None), getattr(app, "tool", None), app):
    for name in ("channel_definition", "channel_editor", "editor"):
        cand = getattr(obj, name, None) if obj is not None else None
        if cand is not None and hasattr(cand, "section"):
            editor = cand
union = set(); rows = {}
for index in range(6):
    if editor is not None:
        editor.section = index
    inv = emtk_inventory(app)
    union |= set(inv["controls"])
    for r in inv["interactive"]:
        rows[(r["kind"], r["label"])] = r["tooltip"]
before = set(json.load(open(out / "before.json"))["controls"])
res = {"editor_found": editor is not None, "controls": sorted(union), "lost_vs_qt": sorted(before - union),
       "untooltipped": sorted(f"{k}: {l}" for (k, l), t in rows.items() if not t)}
(out / "after_all_sections.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
print(res["editor_found"], len(union), "lost:", res["lost_vs_qt"]); print("untooltipped:", res["untooltipped"])
