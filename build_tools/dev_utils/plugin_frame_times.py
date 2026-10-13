"""Measure first-frame and steady-frame time of every emtk plugin, plus startup stages.

Each plugin is loaded in its own hermetic subprocess (scratch settings, offscreen
Qt), drawn at 1100x720 through :class:`emtk.testing.Driver` and timed::

    python -m build_tools.dev_utils.plugin_frame_times            # all plugins, markdown table
    python -m build_tools.dev_utils.plugin_frame_times psf_calculator img_flow
    python -m build_tools.dev_utils.plugin_frame_times --startup  # GUI startup stage timings
    python -m build_tools.dev_utils.plugin_frame_times --json out.json

Targets: first frame < 100 ms, steady frame (median of 20 further frames) < 16 ms.
Draws are issued back to back, so a plugin that computes on its own worker thread
is measured while that worker may still be busy; the number is the UI-thread cost.
Work moved off the first frame must not land on a later one, so the five frames
after the first (``next5``) and every frame drawn while worker results land
(``settle``) are reported as maxima too.

``gate wait`` is how long the frames waited, in all, for a worker thread's first import
(:func:`chisurf._import_gate.main_thread_waits`): one thread imports a module for the first time
at a time, so a frame that lazily imports a module while a worker imports pays for the worker's
import. It should be 0; the module named is the one the frame asked for.

Persistent per-user caches (emtk's installed-font table) are shared by the whole
run and warmed once before measuring, as on every launch after the first; each
plugin still gets its own scratch settings and database.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIZE = (1100, 720)
STEADY_FRAMES = 20
FIRST_BUDGET_MS = 100.0
STEADY_BUDGET_MS = 16.0
TIMEOUT_S = 120
SETTLE_S = 8.0


FONT_CACHE = Path(tempfile.gettempdir()) / "chisurf-frames-emtk-cache"


def _env(scratch: str) -> dict:
    """Environment for a hermetic worker."""
    env = dict(os.environ)
    paths = [str(REPO), str(REPO / "modules" / "chinet"), str(REPO / "modules" / "imp-tricks" / "src"),
             str(REPO / "modules" / "mmfdb" / "src")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env.update(
        PYTHONPATH=os.pathsep.join(paths), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg",
        CHISURF_SETTINGS_DIR=str(Path(scratch) / "settings"), MMFDB_SETTINGS_DIR=str(Path(scratch) / "mmfdb"),
        MMFDB_DATABASE_PATH=str(Path(scratch) / "mmfdb.sqlite"),
        MMFDB_OBJECT_STORE_ROOT=str(Path(scratch) / "objects"),
        XDG_CACHE_HOME=str(Path(scratch) / "cache"), LUMIS_QUEST_HOME=str(Path(scratch) / "lumis"),
        EMTK_CACHE_DIR=str(FONT_CACHE),
    )
    return env


def worker(plugin_id: str) -> dict:
    """Load one plugin and time its frames (runs inside the subprocess)."""
    from qtpy.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from emtk.testing import Driver

    from chisurf._import_gate import main_thread_waits
    from chisurf.emtk.plugins import load_plugin

    t0 = time.perf_counter()
    app = load_plugin(plugin_id, persist=False)
    construct = (time.perf_counter() - t0) * 1000
    main_thread_waits(clear=True)
    driver = Driver(app, SIZE)
    t = time.perf_counter()
    driver.frame()
    first = (time.perf_counter() - t) * 1000
    following = []
    for _ in range(5):
        t = time.perf_counter()
        driver.frame()
        following.append((time.perf_counter() - t) * 1000)
    # Let worker-thread computations (debounced volumes, loads) land, so the steady
    # frames are drawn with their results on screen, not with an empty placeholder.
    # The frame that picks a result up is timed too: deferred work must not hide there.
    settle = [0.0]
    end = time.monotonic() + SETTLE_S
    while time.monotonic() < end and getattr(app, "animating", lambda: False)():
        time.sleep(0.02)
        t = time.perf_counter()
        driver.frame()
        settle.append((time.perf_counter() - t) * 1000)
    times = []
    for _ in range(STEADY_FRAMES):
        t = time.perf_counter()
        driver.frame()
        times.append((time.perf_counter() - t) * 1000)
    waits = main_thread_waits()
    return {"plugin": plugin_id, "construct_ms": construct, "first_ms": first,
            "next5_ms": max(following), "settle_ms": max(settle), "steady_ms": statistics.median(times),
            "max_ms": max(times), "gate_wait_ms": sum(w[0] for w in waits),
            "gate_wait_on": max(waits)[1] if waits else "", "status": "ok"}


def warm_caches() -> None:
    """Fill the run-shared persistent caches once, so no plugin is charged for it."""
    with tempfile.TemporaryDirectory(prefix="chisurf-frames-") as scratch:
        subprocess.run([sys.executable, "-c", "from emtk.font_render import _faces; _faces()"], cwd=REPO,
                       env=_env(scratch), capture_output=True, timeout=TIMEOUT_S)


def run_plugin(plugin_id: str) -> dict:
    """Run :func:`worker` in a subprocess; failures become a row, never a crash."""
    with tempfile.TemporaryDirectory(prefix="chisurf-frames-") as scratch:
        code = ("import json,sys;from build_tools.dev_utils.plugin_frame_times import worker;"
                "print('@@'+json.dumps(worker(sys.argv[1])))")
        try:
            done = subprocess.run([sys.executable, "-c", code, plugin_id], cwd=REPO, env=_env(scratch),
                                  capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return {"plugin": plugin_id, "status": "timeout"}
    for line in done.stdout.splitlines():
        if line.startswith("@@"):
            return json.loads(line[2:])
    tail = (done.stderr.strip().splitlines() or ["?"])[-1][:120]
    return {"plugin": plugin_id, "status": f"failed: {tail}"}


def startup_stages() -> dict:
    """Run the real GUI start offscreen and return ``AppStartupServiceManager.timings``."""
    code = r'''
import json, logging
from qtpy.QtWidgets import QApplication
app = QApplication([])
from chisurf.startup.services import AppStartupServiceManager
m = AppStartupServiceManager()
for phase in ("splash", "post_show"):
    try:
        m.start(surface="gui", phase=phase)
    except Exception as exc:
        logging.exception("phase %s failed: %s", phase, exc)
    app.processEvents()
print("@@" + json.dumps(m.timings), flush=True)
import os; os._exit(0)
'''
    with tempfile.TemporaryDirectory(prefix="chisurf-start-") as scratch:
        done = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=_env(scratch),
                              capture_output=True, text=True, timeout=300)
    for line in done.stdout.splitlines():
        if line.startswith("@@"):
            return json.loads(line[2:])
    return {}


def plugin_ids() -> list[str]:
    """Every plugin id with an ``emtk`` entrypoint."""
    sys.path.insert(0, str(REPO))
    from chisurf.emtk.plugins import manifests

    return sorted(i for i, m in manifests().items() if m.get("entrypoints", {}).get("emtk"))


def table(rows: list[dict]) -> str:
    """Markdown table, slowest steady frame first."""
    ok = sorted((r for r in rows if r["status"] == "ok"), key=lambda r: -r["steady_ms"])
    out = ["| plugin | construct ms | first ms | next5 ms | settle ms | steady ms | max ms | gate wait ms "
           "| first<100 | steady<16 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|"]
    for r in ok:
        wait = f"{r['gate_wait_ms']:.0f}" + (f" ({r['gate_wait_on']})" if r["gate_wait_on"] else "")
        out.append(f"| {r['plugin']} | {r['construct_ms']:.0f} | {r['first_ms']:.0f} | {r['next5_ms']:.0f} | "
                   f"{r['settle_ms']:.0f} | {r['steady_ms']:.1f} | "
                   f"{r['max_ms']:.1f} | {wait} | {'yes' if r['first_ms'] < FIRST_BUDGET_MS else 'NO'} | "
                   f"{'yes' if r['steady_ms'] < STEADY_BUDGET_MS else 'NO'} |")
    out += [f"| {r['plugin']} | - | - | - | - | - | - | - | {r['status']} | |" for r in rows if r["status"] != "ok"]
    return "\n".join(out)


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plugins", nargs="*")
    ap.add_argument("--startup", action="store_true", help="print GUI startup stage timings and exit")
    ap.add_argument("--json", help="also write the rows to this file")
    args = ap.parse_args()
    if args.startup:
        for k, v in sorted(startup_stages().items(), key=lambda kv: -kv[1]):
            print(f"| {k} | {v * 1000:.0f} |")
        return
    warm_caches()
    rows = [run_plugin(p) for p in (args.plugins or plugin_ids())]
    print(table(rows))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
