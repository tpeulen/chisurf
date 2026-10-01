"""Drive the Qt TTTR <-> .pto drop tool into populated states. Usage: <tempdir> <out dir> (repo root).

Temporary folder only; the vendor files are private copies of the burst_selection BH fixture.
"""
import json, os, pathlib, shutil, sys
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
DATA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
for n in ("m000.spc", "m001.spc"): shutil.copy(DATA / n, T / n)
(T / "m000.set").write_bytes(b"BH settings kept byte for byte\r\n")
from chisurf.plugins.core.tttr_to_pto.gui.tool import TttrToPtoTool
w = TttrToPtoTool(); w.resize(900, 600); w.show()
def grab(name):
    for _ in range(30): app.processEvents()
    w.grab().save(str(O / name))
out = {}
grab("before_populated_empty.png")
out["accepts"] = {n: TttrToPtoTool._accepts(str(T / n)) for n in ("m000.spc", "m000.set")}
w._on_dropped([str(T / "m001.spc"), str(T / "m000.spc")])  # the .set beside m000.spc rides along
out["after_pack"] = [w._list.item(i).text() for i in range(w._list.count())]
out["pto"] = sorted(p.name for p in T.glob("*.pto")); out["pto_size"] = (T / "m000.pto").stat().st_size
grab("before_populated_packed.png")
for n in ("m000.spc", "m001.spc", "m000.set"): (T / n).rename(T / (n + ".saved"))
w._on_dropped([str(T / "m000.pto")])
out["after_unpack"] = [w._list.item(i).text() for i in range(w._list.count())]
out["recovered"] = sorted(p.name for p in T.iterdir() if p.suffix in (".spc", ".set"))
out["spc_equal"] = (T / "m000.spc").read_bytes() == (DATA / "m000.spc").read_bytes()
grab("before_populated_unpacked.png")
bad = T / "bad.pto"; bad.write_bytes(b"not a PTO")
w._on_dropped([str(bad)])
out["after_error"] = [w._list.item(i).text() for i in range(w._list.count())]
grab("before_populated_error.png")
print(json.dumps(out, indent=1, default=str)); (O / "before_populated.json").write_text(json.dumps(out, indent=1, default=str))
