"""Every shipped demo runs, and every shipped tour steps to its end -- with no Qt.

The browser had this check (`test_browser_demos`) and the desktop did not: the
only demo tests here asserted that the menu *lists* them and that `demo <key>`
*resolves*, neither of which runs a line of the script. A demo that referred to
a moved module, a renamed command or a file that stopped shipping would pass
both and fail the moment anyone chose it from the menu -- which is how they are
found, since a demo is the fastest way to tell whether a host works at all.

So this runs each one for real in the toolkit-free host (one child process, one
viewer, every demo in turn), and steps each tour through every step. Qt is made
*unimportable* in the child: a demo, an editor or a tour that quietly needs a
toolkit is exactly what this is here to catch.
"""

from __future__ import annotations

import socket

import pytest
from toolkit_free import probe

pytestmark = pytest.mark.slow


def _online() -> bool:
    """Whether the public repositories a fetching demo needs are reachable."""
    for host in ("files.rcsb.org", "ftp.ebi.ac.uk"):
        try:
            with socket.create_connection((host, 443), timeout=3):
                return True
        except OSError:
            continue
    return False


ONLINE = _online()


def _fetching_demos() -> set[str]:
    """Demos whose script fetches from a public repository.

    Derived from the scripts rather than listed here, so a demo that gains or
    loses a ``fetch`` cannot leave this test asserting the wrong thing offline.
    """
    from chimol.plugins.demos.catalog import DEMOS, read_demo

    return {name for name, _t, _n in DEMOS if "fetch " in read_demo(name)}


def _fetching_tours() -> set[str]:
    """Tours that tell the reader to fetch -- their steps run the command."""
    from chimol.ui.tours import available_tours, load_tour

    out = set()
    for key, _title in available_tours():
        steps = load_tour(key).steps
        if any("fetch " in (getattr(step, "command", "") or "") for step in steps):
            out.add(key)
    return out


#: One child process for the whole module: booting a viewer costs seconds and
#: every case below is a command against the same one.
SCRIPT = """
from chimol.plugins.demos.catalog import DEMOS
from chimol.ui.tours import available_tours

app = open_app(size=(900, 600))
cmd = app.cmd
errors = []
cmd._emit_error = lambda message: errors.append(message)

emit("demo_keys", ",".join(name for name, _t, _n in DEMOS))
emit("tour_keys", ",".join(key for key, _title in available_tours()))

for name, _title, _note in DEMOS:
    errors.clear()
    try:
        cmd.do(f"demo {name}")
    except Exception as exc:
        emit(f"demo:{name}", f"raised {type(exc).__name__}: {exc}")
        continue
    objects = len(list(app.viewer.objects.items()))
    emit(f"demo:{name}", ("errors: " + " | ".join(errors)) if errors
         else f"ok objects={objects}")
    cmd.do("delete all")

for key, _title in available_tours():
    errors.clear()
    gui = app.viewer.gui
    try:
        cmd.do(f"tour {key}")
        started = gui.tour is not None
        steps = 0
        while gui.tour is not None and steps < 50:
            steps += 1
            gui.advance_tour()
        cmd.do("tour stop")
    except Exception as exc:
        emit(f"tour:{key}", f"raised {type(exc).__name__}: {exc}")
        continue
    emit(f"tour:{key}", ("errors: " + " | ".join(errors)) if errors
         else f"ok started={started} steps={steps}")

# The script editor: the Qt shell has its own window, every other host gets the
# in-viewport panel -- and this child has no Qt at all.
errors.clear()
cmd.do("demo_edit")
emit("demo_edit", ("errors: " + " | ".join(errors)) if errors
     else ",".join(sorted(w.key for w in app.viewer.gui.windows)))
errors.clear()
cmd.do("demo_edit new")
emit("demo_edit_new", ("errors: " + " | ".join(errors)) if errors
     else ",".join(sorted(w.key for w in app.viewer.gui.windows)))
"""


@pytest.fixture(scope="module")
def ran():
    return probe(SCRIPT, timeout=600, block_qt=True)


def _keys(ran, name):
    raw = ran.get(name, "")
    return [part for part in raw.split(",") if part]


def test_the_probe_found_demos_and_tours(ran):
    """A guard on the harness: an empty catalogue would pass every case below."""
    assert len(_keys(ran, "demo_keys")) >= 8
    assert len(_keys(ran, "tour_keys")) >= 3


def test_every_demo_runs_and_leaves_a_scene(ran):
    skip = set() if ONLINE else _fetching_demos()
    broken = {}
    for name in _keys(ran, "demo_keys"):
        if name in skip:
            continue
        result = ran.get(f"demo:{name}", "missing")
        if not result.startswith("ok "):
            broken[name] = result
        elif result == "ok objects=0":
            broken[name] = "left the scene empty"
    assert not broken, f"demos that did not run: {broken}"


def test_every_tour_starts_and_reaches_its_end(ran):
    skip = set() if ONLINE else _fetching_tours()
    broken = {}
    for key in _keys(ran, "tour_keys"):
        if key in skip:
            continue
        result = ran.get(f"tour:{key}", "missing")
        if not result.startswith("ok started=True"):
            broken[key] = result
        elif "steps=0" in result or "steps=50" in result:
            # Zero steps is a tour that never opened; fifty is one that never
            # closes, which reads as a hang rather than a lesson.
            broken[key] = result
    assert not broken, f"tours that did not run: {broken}"


def test_the_script_editor_opens_on_a_host_with_no_qt(ran):
    """`demo_edit` used to answer "this host has no script editor" everywhere but Qt."""
    windows = ran.get("demo_edit", "")
    assert "editor:" in windows, windows
    assert "editor:scratch" in ran.get("demo_edit_new", ""), ran.get("demo_edit_new")
