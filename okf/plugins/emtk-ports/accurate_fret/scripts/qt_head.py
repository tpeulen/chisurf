"""Build a plugin's Qt tool exactly as committed (HEAD), overlaying HEAD sources of its package.

`load_head_tool(plugin_id, overlay=("app", "view_model"))` reads HEAD:manifest, loads the
HEAD source of every overlaid sibling module (and of the gui module itself) under its REAL
module name before anything imports the working copies, and returns the Qt class.
Use: python qt_head.py <plugin_id> <out_dir> [overlay,modules] -> before.png/json via qt_before.
"""
import importlib, importlib.util, json, pathlib, subprocess, sys, tempfile

def _head(path):
    return subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True, check=True).stdout

def _install(modname, src):
    tmp = pathlib.Path(tempfile.mkdtemp()) / (modname.rsplit(".", 1)[-1] + ".py")
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location(modname, tmp)
    m = importlib.util.module_from_spec(spec); sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m

def load_head_tool(pid, overlay=()):
    man = next(p for p in pathlib.Path("chisurf/plugins").rglob("manifest.json")
               if json.loads(p.read_text()).get("id") == pid)
    spec = json.loads(_head(man))["entrypoints"]["gui"]
    mod, cls = spec.split(":")
    rel = pathlib.Path(mod.replace(".", "/"))
    pkg = mod.rsplit(".", 1)[0]
    # the package __init__ as committed, then the overlays, then the gui module
    init = rel.parent / "__init__.py"
    pkg_mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(pkg, loader=None, is_package=True))
    pkg_mod.__path__ = [str(rel.parent)]
    sys.modules[pkg] = pkg_mod
    for name in overlay:
        _install(f"{pkg}.{name}", _head(rel.parent / f"{name}.py"))
    m = _install(mod, _head(rel.with_suffix(".py")))
    return getattr(m, cls), spec

if __name__ == "__main__":
    from test.gui import emtk_port_parity as epp
    pid, out = sys.argv[1], pathlib.Path(sys.argv[2])
    overlay = tuple(x for x in (sys.argv[3].split(",") if len(sys.argv) > 3 else []) if x)
    out.mkdir(parents=True, exist_ok=True)
    klass, spec = load_head_tool(pid, overlay)
    orig_resolve, orig_manifest = epp._resolve, epp.manifest_of
    epp._resolve = lambda sp: klass if sp == "HEAD" else orig_resolve(sp)
    def patched(i):
        d = dict(orig_manifest(i)); ep = dict(d.get("entrypoints", {})); ep["gui"] = "HEAD"; d["entrypoints"] = ep; return d
    epp.manifest_of = patched
    inv = epp.qt_before(pid, out)
    inv["entrypoint"] = f"HEAD:{spec} (+HEAD {', '.join(overlay) or 'no overlays'})"
    (out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
    print(f"before: {len(inv['controls'])} controls ({inv['entrypoint']}) -> {out}")
