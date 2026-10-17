"""Walk a plugin's guided tour headlessly and prove it is not quietly broken.

Three things go wrong with a tour, and **none of them fail a construction test**:

1. the tool ships ``help.md``/``guide.json`` but the buttons never appear;
2. a step's ``target`` does not resolve — the bubble is then shown *centred*
   rather than skipped, so a whole tour can look authored and point at nothing;
3. a step's text is longer than the bubble and gets **cut off mid-sentence**,
   with the buttons drawn neatly underneath, which reads as a step someone wrote
   that way.

All three are invisible to `pytest` and obvious here. This is the tool the
project rule "never implement a GUI blind" means for a guided tour: run it, then
*look at* the PNGs it writes.

Usage
-----
::

    CHISURF_SETTINGS_DIR=/tmp/qa-settings \\
    PYTHONPATH="modules/mmfdb/src:modules/imp-tricks/src:." \\
    python build_tools/dev_utils/check_plugin_guide.py \\
        burst_analysis /tmp/shots

Pass ``--all`` instead of a target to check every native declaration.
Exit status is non-zero when any check fails, so it can gate a change.

Notes
-----
Native checks press only an actual ``load_example`` control. Other awaited
user, file or external actions remain explicit pending gates.
Every --all worker has a timeout and its own scratch settings and report.

"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _resolve_revision(revision: str, live: bool) -> str:
    """Freeze a moving branch name to one immutable committed source snapshot."""
    if live:
        return revision
    import subprocess

    return subprocess.check_output(
        ["git", "-C", str(_ROOT), "rev-parse", "--verify", f"{revision}^{{commit}}"],
        text=True).strip()


def _source_paths(*, revision: str = "HEAD", live: bool = False) -> set[str]:
    """Enumerate declared release files, keeping working-tree diagnostics explicit."""
    if live:
        return {p.relative_to(_ROOT).as_posix()
                for p in (_ROOT / "chisurf/plugins").rglob("*") if p.is_file()}
    import subprocess

    return set(subprocess.check_output(
        ["git", "-C", str(_ROOT), "ls-tree", "-r", "--name-only", revision,
         "--", "chisurf/plugins"], text=True).splitlines())


def _source_text(path: str, *, revision: str, live: bool) -> str:
    """Read one chosen snapshot file without altering the shared working tree."""
    if live:
        return (_ROOT / path).read_text(encoding="utf-8")
    import subprocess

    return subprocess.check_output(
        ["git", "-C", str(_ROOT), "show", f"{revision}:{path}"], text=True)


def _manifest_records(*, revision: str = "HEAD", live: bool = False) -> list[tuple[pathlib.Path, dict]]:
    """Read snapshot manifests without importing any plugin implementation."""
    revision = _resolve_revision(revision, live)
    records = []
    for name in sorted(_source_paths(revision=revision, live=live)):
        manifest = pathlib.Path(name)
        if manifest.name != "manifest.json" or any(
            part in {"cookiecutter", "test", "tests", "__pycache__"} for part in manifest.parts
        ):
            continue
        data = json.loads(_source_text(name, revision=revision, live=live))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest is not an object: {manifest}")
        records.append((manifest, data))
    return records


def _resource_directories(manifest: pathlib.Path, entry: str, paths: set[str]) -> set[str]:
    """Resolve factory-adjacent and plugin-root resource locations in the snapshot."""
    module = pathlib.Path(entry.split(":", 1)[0].replace(".", "/"))
    directory = module.parent if module.with_suffix(".py").as_posix() in paths else module
    return {directory.as_posix(), manifest.parent.as_posix(),
            (manifest.parent / "gui").as_posix()}


def _has_resource(paths: set[str], folders: set[str], *, guide: bool) -> bool:
    """Require a chosen-snapshot help or tour resource beside the declared surface."""
    return any(pathlib.Path(name).parent.as_posix() in folders
               and ("guide" in pathlib.Path(name).name and name.endswith(".json")
                    if guide else "help" in pathlib.Path(name).name and name.endswith(".md"))
               for name in paths)


def _native_plugins(*, revision: str = "HEAD", live: bool = False) -> list[str]:
    """Include all selected native declarations, even when their guide is missing."""
    revision = _resolve_revision(revision, live)
    found = []
    for manifest, data in _manifest_records(revision=revision, live=live):
        entry = (data.get("entrypoints") or {}).get("emtk")
        if entry:
            if not data.get("id") or not isinstance(entry, str) or ":" not in entry:
                raise ValueError(f"Invalid native declaration: {manifest}")
            if data["id"] in found:
                raise ValueError(f"Duplicate native plugin id: {data['id']}")
            found.append(data["id"])
    return found


def _emtk_plugins_with_tours(*, revision: str = "HEAD", live: bool = False) -> list[str]:
    """Find declared native tour resources without importing their factories."""
    revision = _resolve_revision(revision, live)
    paths = _source_paths(revision=revision, live=live)
    found = []
    for manifest, data in _manifest_records(revision=revision, live=live):
        entry = (data.get("entrypoints") or {}).get("emtk")
        if not entry:
            continue
        if not isinstance(entry, str) or ":" not in entry or not data.get("id"):
            raise ValueError(f"Invalid native declaration: {manifest}")
        if _has_resource(paths, _resource_directories(manifest, entry, paths), guide=True):
            found.append(data["id"])
    return found


def _load_native(plugin_id: str, *, revision: str = "HEAD", live: bool = False):
    """Validate snapshot identity, then invoke the canonical nonpersistent factory."""
    revision = _resolve_revision(revision, live)
    from chisurf.emtk.plugins import load_plugin, native_factory

    declarations = [(path, data) for path, data in _manifest_records(revision=revision, live=live)
                    if data.get("id") == plugin_id]
    if len(declarations) != 1:
        raise ValueError(f"Expected one {revision if not live else 'live'} declaration: {plugin_id}")
    manifest, data = declarations[0]
    entry = (data.get("entrypoints") or {}).get("emtk")
    if not isinstance(entry, str) or ":" not in entry:
        raise ValueError(f"No selected native factory: {plugin_id}")
    paths = _source_paths(revision=revision, live=live)
    module = pathlib.Path(entry.split(":", 1)[0].replace(".", "/"))
    if module.with_suffix(".py").as_posix() not in paths and (module / "__init__.py").as_posix() not in paths:
        raise ValueError(f"Factory source absent from selected snapshot: {entry}")
    folders = _resource_directories(manifest, entry, paths)
    if not _has_resource(paths, folders, guide=True):
        raise ValueError(f"Guide resource absent from selected snapshot: {plugin_id}")
    if not _has_resource(paths, folders, guide=False):
        raise ValueError(f"Help resource absent from selected snapshot: {plugin_id}")
    if native_factory(plugin_id) != entry:
        raise ValueError(f"Working-tree factory differs from selected declaration: {plugin_id}")
    return load_plugin(plugin_id, persist=False)


def _surface_owners(app) -> list:
    """Inspect only explicit surface/controller fields, never arbitrary models."""
    owners, frontier = [app], [app]
    for _ in range(2):
        following = []
        for owner in frontier:
            for name in ("tool", "gui", "controller", "control", "owner"):
                child = getattr(owner, name, None)
                if child is not None and not callable(child) and all(child is not o for o in owners):
                    owners.append(child)
                    following.append(child)
        frontier = following
    return owners


def _fresh_draw(driver, owners) -> None:
    """Discard previous-frame target registries before drawing the actual scene."""
    from collections.abc import MutableMapping

    for owner in owners:
        for holder, name in ((owner, "item_rects"), (owner, "_item_rects"),
                             (getattr(owner, "form", None), "rects")):
            registry = getattr(holder, name, None)
            if isinstance(registry, MutableMapping):
                registry.clear()
    driver.draw(2)


def _target_status(tour, key: str, size: tuple[int, int]) -> tuple[str, tuple | None]:
    """Require a current positive target rectangle wholly inside the viewport."""
    import math

    if not key:
        return "none", None
    resolver = getattr(tour, "get_target_rect", None)
    rect = resolver(key) if callable(resolver) else None
    if rect is None:
        return "missing", None
    try:
        x, y, width, height = map(float, rect)
    except (TypeError, ValueError):
        return "invalid", None
    if not all(math.isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
        return "invalid", None
    if x + width <= 0 or y + height <= 0 or x >= size[0] or y >= size[1]:
        return "offscreen", tuple(rect)
    if x < 0 or y < 0 or x + width > size[0] + 1 or y + height > size[1] + 1:
        return "partially-visible", tuple(rect)
    return "visible", tuple(rect)


def _card_truncated(step: dict, width: int) -> bool:
    """Match the native tour renderer's line estimate and fixed card-height cap."""
    from chisurf.emtk.help_guide import _clean_html_text

    per_line = max(20.0, (min(480.0, width - 40.0) - 28.0) / 7.4)
    body = _clean_html_text(str(step.get("text", "")))
    lines = sum(max(1, int(len(part) / per_line) + 1) for part in body.split("\n"))
    expect = step.get("await")
    hint = step.get("hint") or (expect.get("hint") if isinstance(expect, dict) else None)
    if hint:
        lines += int(len(str(hint)) / per_line) + 2
    return 78.0 + 16.0 * lines > 260.0


def check_emtk(plugin_id: str, out_dir: pathlib.Path, size: tuple[int, int],
               *, settle_timeout: float = 30.0, revision: str = "HEAD",
               live: bool = False) -> bool:
    """Inspect native tour frames and prove only actually clicked demo awaits."""
    from emtk.testing import Driver

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"kind": "native", "target": plugin_id, "size": list(size),
              "source": "working-tree-diagnostic" if live else "committed",
              "revision": None if live else revision,
              "runtime_sources": "Current working-tree code/resource bytes; selected release enrollment and source/resource existence validated.",
              "errors": [], "steps": [], "ok": False,
              "scope": "Current targets/card layout and declared waits; only load_example is clicked."}
    app = tour = None
    try:
        revision = _resolve_revision(revision, live)
        report["revision"] = None if live else revision
        app = _load_native(plugin_id, revision=revision, live=live)
        owners = _surface_owners(app)
        report["owners"] = [f"{type(owner).__module__}.{type(owner).__qualname__}"
                            for owner in owners]
        tour = next((getattr(o, "tour", None) for o in owners
                     if getattr(o, "tour", None) is not None), None)
        help_window = next((getattr(o, key, None) for o in owners
                            for key in ("help_window", "help")
                            if getattr(o, key, None) is not None
                            and not callable(getattr(o, key))), None)
        if tour is None or not getattr(tour, "steps", None):
            report["errors"].append("missing-tour")
        if help_window is None or not getattr(help_window, "sections", None):
            report["errors"].append("missing-help")
        if not report["errors"]:
            assert tour is not None
            driver = Driver(app, size)
            _fresh_draw(driver, owners)
            driver.screenshot(out_dir / "00_window.png")
            for index, step in enumerate(tour.steps):
                # Starting a step resets its real wait state and invokes the
                # declared reveal callback; it never fabricates control use.
                tour.start(index)
                _fresh_draw(driver, owners)
                key = tour._target_key(step.get("target"))
                status, rect = _target_status(tour, key, size)
                expect = bool(step.get("await"))
                wired = bool(getattr(tour, "wait_for_controls", False))
                awaiting_before = bool(tour.awaiting)
                row: dict[str, Any] = {"index": index, "title": step.get("title", ""), "target": key,
                       "target_status": status, "target_rect": rect,
                       "truncated": _card_truncated(step, size[0]), "clicked": False,
                       "await_status": "unwired" if expect and not wired else
                       "pending" if expect else "none"}
                report["steps"].append(row)
                (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                if key == "load_example" and status == "visible":
                    driver.click(rect)
                    row["clicked"] = True
                    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                    driver.settle(timeout=settle_timeout)
                    _fresh_draw(driver, owners)
                    if expect and wired and awaiting_before and not tour.awaiting:
                        row["await_status"] = "fulfilled"
                    elif expect and wired:
                        row["await_status"] = "pending"
                driver.screenshot(out_dir / f"step_{index + 1:02d}.png")
                (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            report["ok"] = all(
                row["target_status"] in {"none", "visible"} and not row["truncated"]
                and row["await_status"] in {"none", "fulfilled"}
                for row in report["steps"]
            )
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if tour is not None:
            stop = getattr(tour, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception as exc:
                    report["errors"].append(f"stop: {type(exc).__name__}: {exc}")
        if app is not None:
            close = getattr(app, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    report["errors"].append(f"close: {type(exc).__name__}: {exc}")
        if report["errors"]:
            report["ok"] = False
        (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    states = [row["await_status"] for row in report["steps"]]
    print(f"{'OK  ' if report['ok'] else 'FAIL'} native {plugin_id} "
          f"steps={len(report['steps'])} awaits={states} errors={report['errors']}", flush=True)
    return report["ok"]


def _run_isolated(targets: list[tuple[str, str]], out_root: pathlib.Path,
                  size: tuple[int, int], timeout: float, *, revision: str = "HEAD",
                  live: bool = False) -> list[dict]:
    """Finish a ledger row for every bounded subprocess, including timeouts."""
    import os
    import subprocess

    reports = []
    out_root.mkdir(parents=True, exist_ok=True)
    for index, (kind, target) in enumerate(targets):
        out = out_root / f"{index:03d}-{kind}-{target.rsplit(':', 1)[-1]}"
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ,
                   CHISURF_SETTINGS_DIR=str(out / "settings"),
                   MMFDB_SETTINGS_DIR=str(out / "mmfdb-settings"))
        cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), target, str(out),
               "--width", str(size[0]), "--height", str(size[1]),
               "--settle-timeout", str(min(timeout, 30.0)), "--revision", revision]
        if live:
            cmd.append("--live")
        row: dict[str, Any] = {"kind": kind, "target": target,
                              "source": "working-tree-diagnostic" if live else "committed",
                              "revision": None if live else revision,
                              "report": str(out / "report.json")}
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                    timeout=timeout, cwd=_ROOT)
            row.update(status="passed" if result.returncode == 0 else "failed",
                       returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            if kind == "native":
                try:
                    native_report = json.loads((out / "report.json").read_text())
                    if not native_report.get("ok"):
                        row["status"] = "failed"
                except (OSError, ValueError, AttributeError) as exc:
                    row.update(status="failed", error=f"Missing native report: {exc}")
            if not (out / "report.json").exists():
                # The process result is explicit and never confused with a step ledger.
                (out / "report.json").write_text(json.dumps(row, indent=2) + "\n")
        except subprocess.TimeoutExpired as exc:
            if (out / "report.json").exists():
                try:
                    row["partial_report"] = json.loads((out / "report.json").read_text())
                except (OSError, ValueError):
                    pass
            row.update(status="timeout", timeout=timeout,
                       stdout=(exc.stdout or b"").decode(errors="replace")
                       if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                       stderr=(exc.stderr or b"").decode(errors="replace")
                       if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            (out / "report.json").write_text(json.dumps(row, indent=2) + "\n")
        except OSError as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}")
            (out / "report.json").write_text(json.dumps(row, indent=2) + "\n")
        reports.append(row)
        print(f"{'OK  ' if row['status'] == 'passed' else 'FAIL'} {kind} {target}: "
              f"{row['status']}", flush=True)
        (out_root / "report.json").write_text(json.dumps(reports, indent=2) + "\n")
    return reports


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", help="plugin id")
    parser.add_argument("out", nargs="?", default="/tmp/guide-shots")
    parser.add_argument("--all", action="store_true", help="walk every tour in the tree")
    parser.add_argument("--revision", default="HEAD", help="committed release snapshot")
    parser.add_argument("--live", action="store_true", help="explicit working-tree diagnostic")
    parser.add_argument("--timeout", type=float, default=120.0, help="per-tool subprocess seconds")
    parser.add_argument("--settle-timeout", type=float, default=30.0, help="demo worker seconds")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args(argv)
    args.revision = _resolve_revision(args.revision, args.live)

    out_root = pathlib.Path(args.target if args.all and args.target
                            and args.out == "/tmp/guide-shots" else args.out)
    size = (args.width, args.height)
    if args.all:
        targets = [("native", plugin) for plugin in _native_plugins(revision=args.revision, live=args.live)]
        rows = _run_isolated(targets, out_root, size, args.timeout,
                             revision=args.revision, live=args.live)
        failed = [row for row in rows if row["status"] != "passed"]
        print(f"\n{len(rows) - len(failed)}/{len(rows)} tour checks passed")
        return 1 if failed else 0
    if not args.target:
        parser.error("give a plugin id, or --all")
    return 0 if check_emtk(args.target, out_root, size,
                           settle_timeout=args.settle_timeout,
                           revision=args.revision, live=args.live) else 1


if __name__ == "__main__":
    raise SystemExit(main())
