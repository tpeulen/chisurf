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

    QT_QPA_PLATFORM=offscreen \\
    CHISURF_SETTINGS_DIR=/tmp/qa-settings \\
    PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \\
    python build_tools/dev_utils/check_plugin_guide.py \\
        chisurf.plugins.burst.burst_analysis.gui.tool:BurstAnalysisTool /tmp/shots

Pass ``--all`` instead of a target to walk every plugin that ships a tour.
Exit status is non-zero when any check fails, so it can gate a change.

Notes
-----
Waits are satisfied by marking the step satisfied, **not** by pressing the
control: pressing an ``add``-style button opens a modal file dialog and hangs a
headless run. Set ``CHISURF_SETTINGS_DIR`` to a scratch directory so a persisted
dock layout from a previous session cannot restore itself over the authored one.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _gui_plugins_with_tours() -> list[tuple[str, str]]:
    """Return ``(module, class)`` for every plugin shipping a ``guide.json``."""
    found: list[tuple[str, str]] = []
    for manifest in sorted((_ROOT / "chisurf" / "plugins").rglob("manifest.json")):
        if "cookiecutter" in manifest.as_posix():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        entry = (data.get("entrypoints") or {}).get("gui")
        if not entry or ":" not in entry:
            continue
        module = entry.split(":")[0]
        path = _ROOT / pathlib.Path(module.replace(".", "/"))
        directory = (
            path.parent
            if path.with_suffix(".py").is_file()
            else (path / "gui" if (path / "gui").is_dir() else path)
        )
        if (directory / "guide.json").is_file():
            found.append(tuple(entry.split(":", 1)))  # type: ignore[arg-type]
    return found


def check(target: str, out_dir: pathlib.Path, size: tuple[int, int]) -> bool:
    """Walk one tool's tour, writing a PNG per step. True when everything holds."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    module_path, class_name = target.split(":")
    out_dir.mkdir(parents=True, exist_ok=True)

    widget_class = getattr(importlib.import_module(module_path), class_name)
    window = widget_class()
    window.resize(*size)
    window.show()
    for _ in range(8):
        app.processEvents()

    captions = [b.text() for b in window.findChildren(QtWidgets.QToolButton)]
    missing = [name for name in ("Guide", "?") if name not in captions]
    if missing:
        print(f"FAIL {class_name}: no {missing} button — is help.md/guide.json beside the tool?")
        return False
    window.grab().save(str(out_dir / "00_window.png"))

    window._guide_button.click()
    for _ in range(4):
        app.processEvents()
    tour = window._guided_tour

    unresolved: list[str] = []
    truncated: list[str] = []
    for index, step in enumerate(tour._steps):
        tour._index = index
        # Never press the user's buttons: an "add" action opens a modal dialog
        # and a headless run then hangs forever.
        tour._satisfied.add(index)
        tour._show_step()
        for _ in range(3):
            app.processEvents()
        if step.target and tour.resolve_target(step.target) is None:
            unresolved.append(step.title)
        if tour._bubble.body_scroll.verticalScrollBar().maximum() > 0:
            truncated.append(step.title)
        window.grab().save(str(out_dir / f"step_{index + 1:02d}.png"))
    tour.stop()
    window.close()

    ok = not unresolved and not truncated
    print(
        f"{'OK  ' if ok else 'FAIL'} {class_name:28} steps={len(tour._steps):2} "
        f"unresolved={unresolved} scrolled={truncated}"
    )
    return ok


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", help="module.path:ClassName")
    parser.add_argument("out", nargs="?", default="/tmp/guide-shots")
    parser.add_argument("--all", action="store_true", help="walk every tour in the tree")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args(argv)

    out_root = pathlib.Path(args.out)
    size = (args.width, args.height)
    if args.all:
        # One subprocess per tool, deliberately. Constructing every GUI tool in a
        # single process is not survivable — the OpenGL-backed ones abort under
        # the offscreen platform and take the whole sweep down with them, which
        # is the same instability that truncates a full ``test/gui`` run. A fork
        # per tool also guarantees each tour starts from clean Qt state, so a
        # global setting one tool changes cannot alter the next one's rendering.
        import subprocess

        targets = _gui_plugins_with_tours()
        failed: list[str] = []
        for module, name in targets:
            done = subprocess.run(
                [sys.executable, __file__, f"{module}:{name}", str(out_root / name),
                 "--width", str(size[0]), "--height", str(size[1])],
                capture_output=True,
                text=True,
            )
            line = next(
                (ln for ln in done.stdout.splitlines() if ln.startswith(("OK  ", "FAIL"))),
                None,
            )
            if line:
                print(line, flush=True)
            else:
                print(f"FAIL {name:28} did not report — exit {done.returncode}", flush=True)
            if done.returncode != 0 or line is None or line.startswith("FAIL"):
                failed.append(name)
        print(f"\n{len(targets) - len(failed)}/{len(targets)} tours clean")
        if failed:
            print("failed: " + ", ".join(failed))
        return 0 if not failed else 1
    if not args.target:
        parser.error("give a module:Class target, or --all")
    return 0 if check(args.target, out_root, size) else 1


if __name__ == "__main__":
    raise SystemExit(main())
