"""Draw the CURRENT (pre-upgrade) native PTO inspector: empty, populated, lifetimes, error; probe the host drop hook.
Usage: <tempdir> <out> (repo root)."""
import json, os, pathlib, sys
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.pto_inspector.test.test_core import container
path = container.__wrapped__(T)
from chisurf.plugins.core.pto_inspector.gui.app import PtoInspectorApp
app = PtoInspectorApp()
S = (1300, 850)
def shot(name):
    import time; t0 = time.time(); emtk_screenshot(app, O / f"{name}_{S[0]}x{S[1]}.png", S); print(name, round(time.time() - t0, 1), flush=True)
out = {"host_would_accept_a_drop": callable(getattr(app, "files_dropped", None)) or callable(getattr(app, "on_files_dropped", None))}
shot("before_emtk_empty")
app.on_paths_dropped([str(path)])
shot("before_emtk_populated")
uid = next(i.uid for i in app.model.inspection.infos() if i.name == "lifetimes"); app.model.select_uid(uid)
shot("before_emtk_lifetimes")
app.verify(); out["notice_after_verify"] = app.notice
bad = T / "broken.pto"; bad.write_bytes(b"not a pto"); app.model.set_filename(str(bad))
shot("before_emtk_error")
print(json.dumps(out)); (O / "before_emtk.json").write_text(json.dumps(out, indent=1))
