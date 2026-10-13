"""The emtk shell's session worker never first-imports the server package while the main thread can.

The shell starts its session on a worker thread (``chisurf-shell-session``) and went on building
itself on the main thread. Both imported the server: the worker for its startup stages (through
``chisurf.core.api``), the main thread for the Log dock's call monitor (``chisurf.server.dispatcher``).
When the two *first* imports overlapped, the main thread executed ``dispatcher`` while the worker
was inside the package's ``__init__``; ``dispatcher`` imports ``protocol``, whose module-level
``resources.files("chisurf.server")`` imported the half-initialised package -- the worker's lock --
while the worker waited for ``dispatcher``, the main thread's lock::

    _frozen_importlib._DeadlockError: deadlock detected by _ModuleLock('chisurf.server')

It happened on about one launch in four.

The cure is an ordering plus a broken cycle: :mod:`chisurf.emtk.session` imports the server and
the API facade at module level, so the thread that picks ``start_session`` has imported them before
any worker starts; the shell starts that worker as the last step of its construction; and
``protocol`` reads its method table beside its own file instead of re-importing its package. The test forces the race deterministically: a finder parks the session worker the moment
it asks for the package ``chisurf.server`` (long enough for the main thread to build the shell),
which is exactly the interleaving that deadlocked. With the ordering in place the worker never asks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = textwrap.dedent(
    """
    import importlib.abc, json, sys, threading, time

    asked = []
    released = threading.Event()

    class ParkTheWorker(importlib.abc.MetaPathFinder):
        # Park the session worker inside its first import of the server package.
        def find_spec(self, name, path=None, target=None):
            if name == "chisurf.server" and threading.current_thread().name != "MainThread":
                asked.append(threading.current_thread().name)
                released.wait(3.0)
            return None

    sys.meta_path.insert(0, ParkTheWorker())

    import chisurf.emtk.main_app as main_app

    shell = main_app.make_app(persist=False)
    released.set()
    end = time.monotonic() + 120
    while not shell.data.session_settled and time.monotonic() < end:
        time.sleep(0.05)
    shell.data.poll()
    result = {
        "asked": asked,
        "settled": shell.data.session_settled,
        "session": shell.data.session is not None,
        "error": shell.data.error,
        # What a first fit imports: there when the session has settled (no warm-up thread).
        "unloaded": [m for m in (
            "chisurf.core.fitting", "chisurf.core.models",
            "chisurf.core.models.global_model.globalfit", "chisurf.core.structure",
            "chisurf.emtk.model_editor",
        ) if m not in sys.modules],
    }
    shell.close()
    sys.__stdout__.write("RESULT " + json.dumps(result) + "\\n")
    sys.__stdout__.flush()
    """
)


def _launch(tmp_path: Path) -> dict:
    import json

    env = dict(os.environ)
    env["CHISURF_SETTINGS_DIR"] = str(tmp_path)
    env["EMTK_CANVAS"] = "offscreen"
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, f"the shell did not start (exit {done.returncode}):\n{done.stderr[-4000:]}"
    assert "DeadlockError" not in done.stderr, done.stderr[-4000:]
    return json.loads(lines[-1][len("RESULT ") :])


def test_the_session_worker_never_first_imports_the_server_package(tmp_path):
    result = _launch(tmp_path)
    assert result["asked"] == [], (
        "the session worker imported the package chisurf.server itself, racing the main thread; "
        "chisurf.emtk.session must import the server at module level"
    )
    assert result["settled"] and result["session"], result
    assert not result["error"], result
    assert result["unloaded"] == [], "a first fit would import these on the frame loop"


# -- the class: no worker's first import can meet the main thread's ------------------------------ #

#: Parks a worker inside a package's ``__init__`` while the main thread first-imports into the same
#: package, through each way the shell puts imports on a worker: the session's start, a hosted
#: plugin's build (:meth:`EmtkShellApp.open_plugin`) and the post-show update check. Each worker
#: first imports its own planted package ``<pkg>`` (``__init__`` imports ``a`` then ``b``, and ``b``
#: imports the package by name), and parks inside ``<pkg>.a``: it holds the package's module lock.
#: The main thread then imports ``<pkg>.b``, which needs the package -- the lock-order inversion of
#: the ``chisurf.server`` deadlock, forced. Without the gate (``chisurf._import_gate``) a worker
#: dies with ``_DeadlockError``; with it the main thread waits for the worker's import and finds
#: the package loaded.
SWEEP = textwrap.dedent(
    """
    import importlib, json, os, sys, tempfile, threading, time

    PARK_S = 1.0
    root = tempfile.mkdtemp(prefix="chisurf-import-race-")
    sys.path.insert(0, root)
    parks = {}
    in_b = {}
    steps = {}

    def arm(pkg):
        os.makedirs(os.path.join(root, pkg))
        with open(os.path.join(root, pkg, "__init__.py"), "w") as f:
            f.write("from . import a\\nfrom . import b\\n")
        with open(os.path.join(root, pkg, "a.py"), "w") as f:
            f.write("import sys\\nsys.park_here(%r)\\n" % pkg)
        with open(os.path.join(root, pkg, "b.py"), "w") as f:
            # As ``protocol`` did with ``resources.files("chisurf.server")``: by name, so CPython
            # takes the package's lock instead of handing back the half-made module.
            f.write(
                "import importlib, sys\\nsys.inside_b(%r)\\nimportlib.import_module(%r)\\n"
                % (pkg, pkg)
            )
        parks[pkg] = threading.Event()
        in_b[pkg] = threading.Event()
        steps[pkg] = []

    def park_here(pkg):
        # ``<pkg>.a``'s body on a worker: it holds the package's module lock (and a's, nothing
        # else) until the main thread is inside ``b``; then it imports ``b``, and waits.
        if threading.current_thread() is not threading.main_thread():
            steps[pkg].append("parked on " + threading.current_thread().name)
            parks[pkg].set()
            in_b[pkg].wait(PARK_S)

    def inside_b(pkg):
        # ``<pkg>.b``'s body on the main thread: let the worker block on b's lock, then ask for the
        # package by name -- the order in which the shell's startup deadlocked.
        if threading.current_thread() is threading.main_thread():
            in_b[pkg].set()
            time.sleep(0.3)

    sys.park_here = park_here
    sys.inside_b = inside_b
    importlib.invalidate_caches()

    def worker_imports(pkg):
        try:
            importlib.import_module(pkg)
        except BaseException as exc:
            steps[pkg].append("worker: %s: %s" % (type(exc).__name__, exc))
            raise
        steps[pkg].append("worker imported")

    def main_imports_into(pkg):
        if not parks[pkg].wait(120):
            steps[pkg].append("no worker entered the package")
            return
        try:
            importlib.import_module(pkg + ".b")
        except BaseException as exc:
            steps[pkg].append("main: %s: %s" % (type(exc).__name__, exc))
            return
        steps[pkg].append("main imported")

    for pkg in ("race_session", "race_plugin", "race_update"):
        arm(pkg)

    import chisurf
    try:
        from chisurf._import_gate import installed as gated
    except ImportError:  # a tree from before the gate (the sweep is run there to show it bites)
        gated = lambda: False
    from emtk.testing import Driver
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.post_show import run_post_show
    from chisurf.emtk.session import start_session
    from chisurf.plugins.core.updater import updater

    # The real stages, without asking the update server.
    updater.check_for_updates = lambda *a, **k: (False, None, None)

    def session_factory(**kwargs):
        worker_imports("race_session")
        return start_session(**kwargs)

    def update_check(on_stage):
        worker_imports("race_update")
        return run_post_show(on_stage)

    shell = EmtkShellApp(
        session_factory=session_factory, post_show=update_check,
        console_history=False, console_session_file=False,
    )
    driver = Driver(shell, (1400, 900))
    # 1. the session's worker, parked while the main thread imports and draws
    main_imports_into("race_session")
    end = time.monotonic() + 120
    while not shell.data.session_settled and time.monotonic() < end:
        driver.frame()
        time.sleep(0.02)

    # 2. a hosted plugin's build
    real_loader = shell.loader
    plugin_id = "setup"

    def loader(pid):
        worker_imports("race_plugin")
        return real_loader(pid)

    shell.loader = loader
    hosted = shell.open_plugin(plugin_id)
    main_imports_into("race_plugin")
    end = time.monotonic() + 120
    while hosted.build is not None and time.monotonic() < end:
        driver.frame()
        time.sleep(0.02)

    # 3. the post-show update check (started by the frame once the session is adopted)
    driver.frame()
    main_imports_into("race_update")
    end = time.monotonic() + 120
    while shell.post_show.result is None and time.monotonic() < end:
        driver.frame()
        time.sleep(0.02)

    result = {
        "gated": gated(),
        "steps": steps,
        "session": shell.data.session is not None,
        "session_error": shell.data.error,
        "plugin_app": hosted.app is not None,
        "plugin_error": hosted.error,
        "post_show": shell.post_show.result,
    }
    shell.close()
    sys.__stdout__.write("RESULT " + json.dumps(result, default=str) + "\\n")
    sys.__stdout__.flush()
    """
)


def _run(script: str, tmp_path: Path) -> tuple[dict, str]:
    import json

    env = dict(os.environ)
    env["CHISURF_SETTINGS_DIR"] = str(tmp_path)
    env["EMTK_CANVAS"] = "offscreen"
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, f"the sweep did not finish (exit {done.returncode}):\n{done.stderr[-4000:]}"
    return json.loads(lines[-1][len("RESULT ") :]), done.stderr


def test_no_shell_worker_first_import_can_meet_the_main_threads(tmp_path):
    result, stderr = _run(SWEEP, tmp_path)
    for pkg, steps in result["steps"].items():
        assert any(step.startswith("parked on ") for step in steps), (pkg, steps)
        assert "worker imported" in steps and "main imported" in steps, (pkg, steps)
    assert "DeadlockError" not in stderr, stderr[-4000:]
    assert result["session"] and not result["session_error"], result
    assert result["plugin_app"] and not result["plugin_error"], result
    assert result["post_show"] is not None, result
    assert result["gated"], "importing chisurf must put the import gate in place"
