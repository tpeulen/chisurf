#!/usr/bin/env python3
"""Bring phacq/chisurf to the MT200 -- development and deployment.

The MT200 (the instrument PC) runs the chisurf source tree at
``C:\\phacq\\src\\chisurf`` and the phacq wheel in the conda env, with
phacq's pure-Python files deployed on top of the wheel. There is no git on
the machine, so this tool is the one way files should travel:

    python build_tools/mt200.py status           what runs there, what drifted
    python build_tools/mt200.py push             deploy changed files (dev)
    python build_tools/mt200.py push --restart   ... and stop the app for relaunch
    python build_tools/mt200.py rollback         undo the last push
    python build_tools/mt200.py wheels [DIR]     install wheels from DIR (release)

How push works: the changed files travel as one tar; a small helper on the
instrument (installed by this tool, C:\\phacq\\deploy\\mt200_helper.py)
extracts it to a staging folder, **byte-compiles everything with the
instrument's own Python** (a file that does not compile is never deployed),
backs up the previous versions to ``C:\\phacq\\deploy\\backup\\<timestamp>``,
and only then moves files into place. ``C:\\phacq\\deploy\\deploy.json``
records the commit, the time and the sha256 of every deployed file; ``status``
re-hashes the machine against it and against this checkout, so drift is a
command away. Wheels installed by pip are not overlaid -- ``status`` warns
when a pip operation has clobbered the phacq overlay and push restores it.

Runs on the development machine (ssh/scp; the key and host are configured
below). The MT200 side needs nothing but the instrument's own Python.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

#: the instrument
HOST = "Mess-Admin@129.217.203.66"
KEY = str(Path.home() / ".ssh/id_ed25519_mt200")
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "LogLevel=ERROR", HOST]

#: this checkout and its siblings
HERE = Path(__file__).resolve().parent.parent
PHACQ = Path.home() / "dev/libphacq"

#: where things live on the instrument
REMOTE_HELPER = "C:/phacq/deploy/mt200_helper.py"
REMOTE_RECORD = "C:/phacq/deploy/deploy.json"
REMOTE_STAGE = "C:/phacq/deploy/stage"
REMOTE_PY = "C:/Users/Mess-Admin/miniforge3/envs/chisurf/python.exe"
REMOTE_CHISURF = "C:/phacq/src/chisurf"
REMOTE_SITE_PACKAGES = "C:/Users/Mess-Admin/miniforge3/envs/chisurf/Lib/site-packages"

#: what this tool owns: (local root, pattern, remote root). The chisurf
#: package (what the app imports), and phacq's pure-Python files over the
#: wheel -- __init__.py is rendered from phacq_init.py.in (template markers
#: would not run).
MANIFEST = [
    (HERE / "chisurf", "**/*.py", REMOTE_CHISURF + "/chisurf"),
    (HERE / "chisurf", "**/*.json", REMOTE_CHISURF + "/chisurf"),
    (HERE / "chisurf", "**/*.md", REMOTE_CHISURF + "/chisurf"),
    (HERE / "chisurf", "**/*.yaml", REMOTE_CHISURF + "/chisurf"),
    (PHACQ / "ext/python", "pqusb.py", REMOTE_SITE_PACKAGES + "/phacq"),
    (PHACQ / "ext/python", "snapi.py", REMOTE_SITE_PACKAGES + "/phacq"),
]

HELPER = r'''
"""The MT200 side of build_tools/mt200.py (installed by it; do not edit).

    mt200_helper.py record            the deploy record (deploy.json)
    mt200_helper.py hash <listfile>   sha256 of each path in the list (JSON)
    mt200_helper.py install <tar> <commit> <time>
        extract the tar (paths inside are absolute), byte-compile every .py
        with this Python, back up the files being replaced, move them into
        place, and update the deploy record
    mt200_helper.py rollback          restore the newest backup
"""
import hashlib
import json
import os
import py_compile
import shutil
import sys
import tarfile
import time
from pathlib import Path

DEPLOY = Path(r"C:\phacq\deploy")
RECORD = DEPLOY / "deploy.json"
BACKUP = DEPLOY / "backup"


def record():
    try:
        print(json.dumps(json.loads(RECORD.read_text())))
    except OSError:
        print("{}")


def do_hash(listfile):
    out = {}
    for path in Path(listfile).read_text().splitlines():
        path = Path(path.strip())
        try:
            out[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            out[path.as_posix()] = None
    print(json.dumps(out))


def install(tar_path, commit, stamp):
    stage = DEPLOY / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    with tarfile.open(tar_path) as tar:
        tar.extractall(stage)
    files = [p for p in stage.rglob("*") if p.is_file()]
    for path in files:
        if path.suffix == ".py":
            py_compile.compile(str(path), doraise=True)
    backup = BACKUP / stamp
    changed = []
    for path in files:
        # the tar stores absolute paths with the drive as C$/ (a single tar
        # root folder); map C$/x/y back to C:/x/y
        parts = path.relative_to(stage).parts
        target = Path(parts[0][:-1] + ":/").joinpath(*parts[1:])
        if target.exists():
            keep = backup / path.relative_to(stage)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, keep)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        changed.append(target.as_posix())
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in changed}
    old = {}
    try:
        old = json.loads(RECORD.read_text()).get("files", {})
    except (OSError, json.JSONDecodeError):
        pass
    old.update(hashes)
    RECORD.write_text(json.dumps({
        "commit": commit, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "backup": stamp, "files": old}, indent=1))
    shutil.rmtree(stage)
    os.remove(tar_path)
    # import smoke test: a file can compile and still import an API the
    # installed wheels do not have; on failure undo this install entirely
    import subprocess
    probe = subprocess.run(
        [sys.executable, "-c",
         "import chisurf.plugins.core.acq.gui.record_app"],
        capture_output=True, text=True,
        cwd=r"C:\phacq\src\chisurf")
    if probe.returncode != 0:
        for path in backup.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(backup).parts
            target = Path(parts[0][:-1] + ":/").joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        print(json.dumps({"failed": "import probe", "rolled back to": stamp,
                          "error": probe.stderr.strip().splitlines()[-1]}))
        sys.exit(1)
    print(json.dumps({"installed": len(changed), "backup": stamp}))


def rollback():
    try:
        stamp = json.loads(RECORD.read_text())["backup"]
    except (OSError, KeyError):
        print(json.dumps({"error": "no backup recorded"}))
        return
    root = BACKUP / stamp
    restored = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if not parts[0].endswith("$"):
            continue
        target = Path(parts[0][:-1] + ":/").joinpath(*parts[1:])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        restored += 1
    print(json.dumps({"restored": restored, "backup": stamp}))


if __name__ == "__main__":
    {"record": record, "hash": lambda: do_hash(sys.argv[2]),
     "install": lambda: install(sys.argv[2], sys.argv[3], time.strftime("%Y%m%d_%H%M%S")),
     "rollback": rollback}[sys.argv[1]]()
'''


def _render_phacq_init() -> tuple[str, bytes]:
    """phacq's __init__.py from the template, with the version substituted."""
    template = (PHACQ / "ext/python/phacq_init.py.in").read_text(encoding="utf-8")
    version = "0.1.0.dev"
    pyproject = PHACQ / "pyproject.toml"
    if pyproject.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.M)
        if m:
            version = m.group(1)
    return "__init__.py", template.replace("@PROJECT_VERSION@", version).encode()


def _local_files() -> dict[str, bytes]:
    """Every file this tool owns: absolute remote path (C:/ posix) -> content."""
    out: dict[str, bytes] = {}
    for root, pattern, remote_root in MANIFEST:
        for path in sorted(root.glob(pattern)):
            if "__pycache__" in path.parts or path.is_dir():
                continue
            out[str(Path(remote_root) / path.relative_to(root)).replace("\\", "/")] = \
                path.read_bytes()
    name, content = _render_phacq_init()
    out[str(Path(REMOTE_SITE_PACKAGES) / "phacq" / name).replace("\\", "/")] = content
    return out


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _remote(command: str, *, check: bool = True) -> str:
    result = subprocess.run(SSH + [command], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"remote command failed: {command}\n{result.stderr.strip()}")
    return (result.stdout or "").strip()


def _ensure_helper():
    """The helper travels with this tool; refresh it whenever it changes."""
    local = hashlib.sha256(HELPER.encode()).hexdigest()
    have = _remote(f"{REMOTE_PY} -c \"import hashlib; "
                   f"print(hashlib.sha256(open(r'{REMOTE_HELPER}','rb').read()).hexdigest())"
                   f" if __import__('os').path.exists(r'{REMOTE_HELPER}') else 0\"",
                   check=False)
    if have != local:
        _remote("if not exist C:\\phacq\\deploy mkdir C:\\phacq\\deploy")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(HELPER)
            tmp = f.name
        subprocess.run(["scp", "-i", KEY, "-o", "LogLevel=ERROR", tmp,
                        f"{HOST}:{REMOTE_HELPER}"], check=True, capture_output=True)
        os.unlink(tmp)


def _remote_hashes(paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    _ensure_helper()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(paths))
        tmp = f.name
    subprocess.run(["scp", "-i", KEY, "-o", "LogLevel=ERROR", tmp,
                    f"{HOST}:C:/phacq/deploy/_list.txt"], check=True, capture_output=True)
    os.unlink(tmp)
    raw = _remote(f"{REMOTE_PY} {REMOTE_HELPER} hash C:/phacq/deploy/_list.txt", check=False)
    line = [l for l in raw.splitlines() if l.startswith("{")]
    return json.loads(line[-1]) if line else {}


def _deploy_record() -> dict:
    _ensure_helper()
    raw = _remote(f"{REMOTE_PY} {REMOTE_HELPER} record", check=False)
    line = [l for l in raw.splitlines() if l.startswith("{")]
    return json.loads(line[-1]) if line else {}


def _scoped(args) -> dict[str, bytes]:
    """The managed files, filtered to the requested substrings (all if none).

    Patterns match the path BELOW its remote root (the repository-relative
    name), so "record_app" or "acq/" mean what they say -- the absolute
    remote path always contains "phacq" and must not make every pattern
    match everything.
    """
    local = _local_files()
    patterns = getattr(args, "patterns", None) or []
    if patterns:
        roots = [remote_root for _root, _pattern, remote_root in MANIFEST]

        def tail(path: str) -> str:
            for root in roots:
                if path.startswith(root + "/"):
                    return path[len(root) + 1:]
            return path

        local = {p: c for p, c in local.items()
                 if any(s in tail(p) or s in p.split("/")[-1] for s in patterns)}
    return local


def cmd_status(args) -> int:
    local = _scoped(args)
    record = _deploy_record()
    remote = _remote_hashes(list(local))
    print(f"deployed by: {record.get('commit', '?')} at {record.get('time', '?')}")
    drifted, missing = [], []
    for path, content in sorted(local.items()):
        want = _sha256(content)
        have = remote.get(path)
        if have is None:
            missing.append(path)
        elif have != want:
            drifted.append(path)
    print(f"{len(local)} managed files: {len(local) - len(drifted) - len(missing)} in sync")
    for label, items in (("DRIFTED (differs from this checkout)", drifted),
                         ("MISSING on the instrument", missing)):
        if items:
            print(f"\n{label}: {len(items)}")
            for item in items[:20]:
                print("  ", item)
            if len(items) > 20:
                print(f"   ... and {len(items) - 20} more")
    wheels = _remote(
        f"{REMOTE_PY} -m pip show phacq tttrlib 2>nul | findstr /i \"name version\"",
        check=False)
    print("\nwheels:\n", wheels or "  (pip query failed)")
    return 0 if not (drifted or missing) else 1


def _worktree(ref: str):
    """A clean git worktree of this repo at *ref* (a branch, tag or commit).

    Deploys source from a worktree, never the shared working tree: the
    worktree is exactly one coherent committed state, so no other lane's
    uncommitted files can ride along and no committed file can arrive
    without the files it depends on."""
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="mt200-worktree-"))
    result = subprocess.run(["git", "worktree", "add", "--detach", str(tmp), ref],
                            cwd=HERE, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git worktree add {ref} failed: {result.stderr.strip()}")
    return tmp


def cmd_push(args) -> int:
    local = _scoped(args)
    if getattr(args, "from_ref", None):
        tree = _worktree(args.from_ref)
        global HERE
        real_here = HERE
        try:
            from pathlib import Path as _P
            # re-source the chisurf manifest from the worktree
            replaced = {}
            wt_chisurf = tree / "chisurf"
            for path, content in local.items():
                if path.startswith(REMOTE_CHISURF + "/chisurf/"):
                    rel = path[len(REMOTE_CHISURF + "/chisurf/"):]
                    wt_file = wt_chisurf / rel
                    replaced[path] = wt_file.read_bytes() if wt_file.exists() else content
                else:
                    replaced[path] = content
            local = replaced
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)],
                           cwd=real_here, capture_output=True)
    if getattr(args, "from_ref", None) is None and not getattr(args, "patterns", None):
        # a full or pattern push without --from would read the shared working
        # tree -- never deploy dirty state to the instrument
        args.from_ref = "HEAD" if getattr(args, "all", False) else None
    if not getattr(args, "all", False) and not getattr(args, "patterns", None) \
            and not getattr(args, "from_ref", None):
        print("refusing to push the whole tree implicitly -- this checkout is shared "
              "and carries other lanes' work in progress;\n"
              "name the files (substring patterns), pass --from REF (a clean worktree), "
              "or --all deliberately")
        return 2
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "chisurf"], cwd=HERE,
                           capture_output=True, text=True).stdout
    if dirty:
        print("note: this working tree has uncommitted chisurf changes; the deploy "
              "record names the commit, not file states")
    remote = _remote_hashes(list(local))
    changed = [p for p, c in sorted(local.items()) if remote.get(p) != _sha256(c)]
    if not changed:
        print("nothing to push; the instrument matches this checkout (scoped)")
    else:
        _ensure_helper()
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.tar"
            with tarfile.open(bundle, "w") as tar:
                for path in changed:
                    # absolute remote path with the drive as C$/ so the tar
                    # root is a single folder the helper can map back
                    arc_path = path.replace(":", "$", 1)
                    info = tarfile.TarInfo(arc_path)
                    info.size = len(local[path])
                    tar.addfile(info, io.BytesIO(local[path]))
            subprocess.run(["scp", "-i", KEY, "-o", "LogLevel=ERROR", str(bundle),
                            f"{HOST}:C:/phacq/deploy/bundle.tar"], check=True,
                           capture_output=True)
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                capture_output=True, text=True).stdout.strip() or "nogit"
        raw = _remote(f"{REMOTE_PY} {REMOTE_HELPER} install C:/phacq/deploy/bundle.tar "
                      f"{commit}", check=False)
        print(raw or "remote install produced no output")
    running = _remote("tasklist | findstr /i python.exe", check=False)
    if running:
        print("the app is RUNNING -- restart it to load the new files")
        if args.restart:
            _remote("taskkill /f /im python.exe", check=False)
            print("app stopped; relaunch PhAcq")
    else:
        print("app not running; launch PhAcq when ready")
    return 0


def cmd_rollback(_args) -> int:
    _ensure_helper()
    raw = _remote(f"{REMOTE_PY} {REMOTE_HELPER} rollback", check=False)
    print(raw or "rollback produced no output")
    return 0


def cmd_wheels(args) -> int:
    source = Path(args.dir) if args.dir else HERE / "dist"
    wheels = sorted(source.glob("*.whl"))
    if not wheels:
        print(f"no wheels in {source}")
        return 1
    for wheel in wheels:
        subprocess.run(["scp", "-i", KEY, "-o", "LogLevel=ERROR", str(wheel),
                        f"{HOST}:C:/phacq/wheels/"], check=True, capture_output=True)
        print(f"installed {wheel.name}")
        _remote(f"{REMOTE_PY} -m pip install --no-deps --force-reinstall "
                f"C:/phacq/wheels/{wheel.name} 2>&1 | findstr /i \"successfully\"")
    print("wheels installed; a push afterwards restores the phacq overlay")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="what runs on the instrument, what drifted")
    status.add_argument("patterns", nargs="*", help="restrict to paths containing these")
    status.add_argument("--all", action="store_true", help="ignore patterns")
    push = sub.add_parser("push", help="deploy changed files (scoped; --all for everything)")
    push.add_argument("patterns", nargs="*", help="restrict to paths containing these")
    push.add_argument("--all", action="store_true",
                      help="push every managed file (deliberate: includes other lanes' work)")
    push.add_argument("--from", dest="from_ref", metavar="REF",
                      help="source the chisurf files from a clean git worktree at REF "
                           "(commit/branch/tag; default with --all: HEAD)")
    push.add_argument("--restart", action="store_true", help="stop the app after pushing")
    sub.add_parser("rollback", help="undo the last push")
    wheels = sub.add_parser("wheels", help="install wheels (release)")
    wheels.add_argument("dir", nargs="?", help="directory with .whl files")
    args = parser.parse_args(argv)
    return {"status": cmd_status, "push": cmd_push,
            "rollback": cmd_rollback, "wheels": cmd_wheels}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
