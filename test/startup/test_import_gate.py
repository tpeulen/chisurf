"""``chisurf._import_gate``: one thread at a time imports a module for the first time.

Each case runs in a fresh interpreter: a worker is parked inside a planted package's ``__init__``
(it holds the package's module lock) while the main thread first-imports a submodule that names the
package -- the lock-order inversion that killed the emtk shell's startup. Without the gate CPython
raises ``_DeadlockError``; with it the main thread waits for the worker's import. The shell-level
sweep over the session, plugin and update-check workers is
``test/startup/test_startup_import_race.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RACE = textwrap.dedent(
    """
    import importlib, os, sys, tempfile, threading, time

    if sys.argv[1] == "gated":
        sys.path.insert(0, {root!r})
        import chisurf._import_gate as gate
        gate.install()
        gate.install()  # a second call is harmless
        assert gate.installed()

    root = tempfile.mkdtemp()
    sys.path.insert(0, root)
    os.makedirs(os.path.join(root, "planted"))
    with open(os.path.join(root, "planted", "__init__.py"), "w") as f:
        f.write("from . import a\\nfrom . import b\\n")
    with open(os.path.join(root, "planted", "a.py"), "w") as f:
        f.write("import sys\\nsys.park_here()\\n")
    with open(os.path.join(root, "planted", "b.py"), "w") as f:
        f.write("import importlib, sys\\nsys.inside_b()\\nimportlib.import_module('planted')\\n")
    parked = threading.Event()
    main_in_b = threading.Event()

    def park_here():
        # ``planted.a``'s body on the worker: it holds the package's lock (and a's, nothing else)
        # until the main thread is inside ``b``; then it imports ``b`` and waits for the main thread.
        if threading.current_thread() is not threading.main_thread():
            parked.set()
            main_in_b.wait(1.0)

    def inside_b():
        # ``planted.b``'s body on the main thread: give the worker time to block on b's lock, then
        # ask for the package by name -- the order in which the shell's startup deadlocked.
        if threading.current_thread() is threading.main_thread():
            main_in_b.set()
            time.sleep(0.3)

    sys.park_here = park_here
    sys.inside_b = inside_b
    said = []

    def worker():
        try:
            importlib.import_module("planted")
            said.append("worker ok")
        except BaseException as exc:
            said.append("worker " + type(exc).__name__)

    thread = threading.Thread(target=worker, name="parked")
    thread.start()
    parked.wait(30)
    # A module already loaded never waits for the worker's first import.
    t = time.perf_counter()
    importlib.import_module("os")
    said.append("loaded %.3f" % (time.perf_counter() - t))
    try:
        importlib.import_module("planted.b")
        said.append("main ok")
    except BaseException as exc:
        said.append("main " + type(exc).__name__)
    thread.join()
    print("SAID", " | ".join(said))
    """
).format(root=str(ROOT))


def _race(mode: str) -> str:
    done = subprocess.run(
        [sys.executable, "-c", RACE, mode], capture_output=True, text=True, timeout=120
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("SAID ")]
    assert lines, done.stderr[-3000:]
    return lines[-1]


def test_without_the_gate_the_planted_race_deadlocks():
    """The harness bites: CPython alone raises on this interleaving."""
    said = _race("plain")
    assert "DeadlockError" in said, said


def test_with_the_gate_both_threads_import():
    said = _race("gated")
    assert "worker ok" in said and "main ok" in said, said
    loaded = float(said.split("loaded ")[1].split(" ")[0])
    assert loaded < 0.2, f"a loaded module waited for the worker's import: {said}"


def test_importing_chisurf_installs_the_gate():
    code = "import chisurf, chisurf._import_gate as g; print('GATED', g.installed())"
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert "GATED True" in done.stdout, done.stderr[-3000:]
