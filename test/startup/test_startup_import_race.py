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
