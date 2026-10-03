"""Populated captures of the native code editor driven with real input (temp HOME, in-memory clipboard): python capture_input_states.py <outdir>."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui
tmp = Path(tempfile.mkdtemp(prefix="codeeditor_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
from emtk import clipboard, keys
from emtk.events import CONTROL_MODIFIER as CTRL, SHIFT_MODIFIER as SHIFT
from chisurf.plugins.core.code_editor.test.test_emtk_editor_input import Ed
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
held = {"t": ""}; clipboard.set_hook(lambda t: held.__setitem__("t", t), lambda: held["t"])
proj = tmp / "proj"; proj.mkdir(); (proj / "script.py").write_text("import numpy as np\n\n\ndef total(values):\n    return sum(values)\n\n\nprint(total([1, 2, 3]))\n")
out = Path(sys.argv[1]); app = make_editor_app(str(proj)); d = Ed(app); d.draw(3)
app.model.open_file(proj / "script.py"); d.draw(3)
for size in ((1200, 800), (800, 600)):
    d.resize(size); d.screenshot(out / f"after_script_{size[0]}x{size[1]}.png")
d.resize((1200, 800)); d.click_at(3, 4)
for _ in range(5): d.key(keys.KEY_RIGHT, "", SHIFT)
d.screenshot(out / "after_selection_1200x800.png")
d.combo("f"); d.type("total"); d.key(keys.KEY_RETURN, "\r"); d.screenshot(out / "after_find_1200x800.png")
app.close()
