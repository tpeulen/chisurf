"""Capture the Qt tool as COMMITTED (HEAD) when the working file was rewritten to host emtk.

Usage: python qt_before_head.py <plugin_id> <out_dir> [<prefix>]
The HEAD source of the manifest's entrypoints.gui module is loaded as a sibling module
(`<package>._head_<name>`) so its relative imports resolve, then the parity tool's
qt_before runs on that class. Writes <prefix>.png / <prefix>.json (default "before").
"""
import importlib.util, json, pathlib, subprocess, sys, tempfile
from test.gui import emtk_port_parity as epp

pid, out = sys.argv[1], pathlib.Path(sys.argv[2])
prefix = sys.argv[3] if len(sys.argv) > 3 else "before"
out.mkdir(parents=True, exist_ok=True)
man_path = next(p for p in pathlib.Path("chisurf/plugins").rglob("manifest.json")
                if json.loads(p.read_text()).get("id") == pid)
head_man = json.loads(subprocess.run(["git", "show", f"HEAD:{man_path}"], capture_output=True, text=True, check=True).stdout)
spec = head_man["entrypoints"]["gui"]
mod, cls = spec.split(":")
rel = pathlib.Path(mod.replace(".", "/"))
src_path = rel.with_suffix(".py") if rel.with_suffix(".py").exists() else rel / "__init__.py"
src = subprocess.run(["git", "show", f"HEAD:{src_path}"], capture_output=True, text=True, check=True).stdout
pkg = mod.rsplit(".", 1)[0] if src_path.name != "__init__.py" else mod
importlib.import_module(pkg)
tmp = pathlib.Path(tempfile.mkdtemp()) / f"_head_{rel.name}.py"
tmp.write_text(src)
name = f"{pkg}._head_{rel.name}"
s = importlib.util.spec_from_file_location(name, tmp)
m = importlib.util.module_from_spec(s); sys.modules[name] = m; s.loader.exec_module(m)
klass = getattr(m, cls)
orig_resolve, orig_manifest = epp._resolve, epp.manifest_of
epp._resolve = lambda sp: klass if sp == "HEAD" else orig_resolve(sp)
def patched(i):
    d = dict(orig_manifest(i)); ep = dict(d.get("entrypoints", {})); ep["gui"] = "HEAD"; d["entrypoints"] = ep; return d
epp.manifest_of = patched
inv = epp.qt_before(pid, out)
inv["entrypoint"] = f"HEAD:{spec}"
if prefix != "before":
    (out / "before.png").rename(out / f"{prefix}.png"); (out / "before.json").unlink()
(out / f"{prefix}.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
print(f"{prefix}: {len(inv['controls'])} controls (HEAD {spec}) -> {out}")
