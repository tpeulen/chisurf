"""Draw the CURRENT (pre-upgrade) native app: empty, packed, unpacked, error; and probe the host drop hook.
Usage: <tempdir> <out> (repo root)."""
import json, os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
DATA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
for n in ("m000.spc", "m001.spc"): shutil.copy(DATA / n, T / n)
(T / "m000.set").write_bytes(b"BH settings kept byte for byte\r\n")
from chisurf.plugins.core.tttr_to_pto.gui.app import TttrToPtoApp
app = TttrToPtoApp()
def finish():
    while app.job.running or app.pending:
        try:
            app.job.future.result(timeout=60)
        except Exception:
            pass  # the job re-raises a failed write; poll() records it in the row
        app.poll()
S = (900, 600)
emtk_screenshot(app, O / "before_emtk_empty_900x600.png", S)
# what the host does with a drop: ImApp.on_files_dropped -> files_dropped / on_files_dropped
# emtk's Qt host accepts a drag only when the control has `files_dropped` or `on_files_dropped`
out = {"host_would_accept_a_drop": callable(getattr(app, "files_dropped", None)) or callable(getattr(app, "on_files_dropped", None))}
app.add_paths([str(T / "m001.spc"), str(T / "m000.spc")]); finish()
emtk_screenshot(app, O / "before_emtk_packed_900x600.png", S)
app.add_paths([str(T / "m000.pto")]); finish()
(T / "bad.pto").write_bytes(b"not a PTO"); app.add_paths([str(T / "bad.pto")]); finish()
app.add_paths([str(T / "m000.set")])
emtk_screenshot(app, O / "before_emtk_error_900x600.png", S)
out["rows"] = [(r["action"], r["status"]) for r in app.rows]
print(json.dumps(out)); (O / "before_emtk.json").write_text(json.dumps(out, indent=1))
