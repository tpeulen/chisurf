"""Write deliberate.json from compare.json's lost list: the Qt hub's text is the embedded Qt children's (the Setup wizard
shown first) and the lazy-load placeholders; the native hub hosts the accepted native children, each with its own report."""
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
lost = json.load(open(out / "compare.json"))["lost"]
named = {"?": "Qt '?' help button: native 'Help'"}
placeholder = "Qt lazy-load placeholder 'Select <tool> to load.': the native hub builds a tool when it is selected and draws it (no placeholder page)"
child = ("text of the embedded Qt Setup panel (the detector wizard) and its dialogs, which the Qt hub shows on its first page: the native "
         "hub hosts the native setup_channel_definition app instead (its own report: okf/plugins/emtk-ports/setup_channel_definition); "
         "cells and captions of that wizard are data of that tool, not of the hub")
res = {}
for k in lost:
    res[k] = named.get(k) or (placeholder if k.startswith("select") and k.endswith("toload.") else child)
(out / "deliberate.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
print(len(res))
