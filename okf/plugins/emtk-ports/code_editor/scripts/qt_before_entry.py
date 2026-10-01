"""emtk_port_parity.qt_before with an explicit Qt entrypoint (when the manifest's gui was repointed)."""
import sys, pathlib
from test.gui import emtk_port_parity as epp
pid, entry, out = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
orig = epp.manifest_of
def patched(i):
    m = dict(orig(i)); ep = dict(m.get("entrypoints", {})); ep["gui"] = entry; m["entrypoints"] = ep; return m
epp.manifest_of = patched
inv = epp.qt_before(pid, out)
print("before:", len(inv["controls"]), "controls ->", out)
