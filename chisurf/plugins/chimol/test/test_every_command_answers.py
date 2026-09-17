"""No command answers with an internal error, whatever the scene holds.

``BaseCmd.do`` has two ways of saying no. A :class:`CommandError` becomes
``name: <what is wrong>`` -- a sentence written for whoever typed the line, and
the right answer to `fitmap` with no map or `show` with no representation. Any
*other* exception becomes ``Error in command 'name': <the exception>``, which is
a Python message leaking into the prompt: an unpacked ``None``, an attribute
that moved, an index that is not there.

The second kind is always a defect, and there is nothing scene-specific about
the sweep that finds it: run every registered command in its bare form and look
for that prefix. `fitmap` was the first catch -- ``_map_named`` returned a bare
``None`` when the scene had no map at all, so the command that exists to say
"no map is loaded" answered "cannot unpack non-iterable NoneType object".

The sweep runs bare forms twice, once with a structure loaded and once on an
empty scene, because the two paths through a command are usually different --
and "nothing is loaded" is the state a viewer starts in.
"""

from __future__ import annotations

import pytest
from toolkit_free import probe

#: Commands the sweep does not call, and why. Kept short on purpose: a command
#: excluded here is a command nothing checks.
SKIP = {
    "quit",
    "exit",  # end the process the sweep is running in
    "system",
    "shell",  # run something outside chimol
    "fetch",  # reaches the network
    "demo",
    "tour",  # covered, and slowly, by test_demos_and_tours
    "plugins",  # re-imports every plugin module
    "sleep",
    "wait",  # block the sweep
}

SCRIPT = f"""
# Bare forms of `movie`, `png`, `save` and friends write their default file
# into the working directory; from the checkout that left orbit.gif and its
# frames in the repository root. The sweep runs somewhere disposable.
import os, tempfile
os.chdir(tempfile.mkdtemp(prefix="every-command-"))
app = open_app(size=(600, 400))
cmd = app.cmd
errors = []
cmd._emit_error = lambda message: errors.append(message)

SKIP = {sorted(SKIP)!r}
names = sorted(set(cmd.command_names()))
emit("count", str(len(names)))

def sweep(tag):
    for name in names:
        if name in SKIP:
            continue
        errors.clear()
        try:
            cmd.do(name)
        except Exception as exc:
            emit(f"{{tag}}:{{name}}", f"raised {{type(exc).__name__}}: {{exc}}")
            continue
        for message in errors:
            if message.startswith("Error in command"):
                emit(f"{{tag}}:{{name}}", message[:160])
        # A command that emptied the scene (`remove`, `delete`) would make
        # every later one report "nothing is loaded" and test nothing.
        if tag == "loaded" and not list(app.viewer.objects.items()):
            cmd.do("load 148l.pdb")

cmd.do("delete all")
sweep("empty")
cmd.do("load 148l.pdb")
sweep("loaded")
emit("done", "yes")
"""


@pytest.fixture(scope="module")
def swept():
    return probe(SCRIPT, timeout=900)


def test_the_sweep_ran(swept):
    """A guard on the harness: no commands swept would pass everything below."""
    assert swept.get("done") == "yes"
    assert int(swept.get("count", "0")) > 150


@pytest.mark.parametrize("scene", ["empty", "loaded"])
def test_no_command_leaks_an_exception(swept, scene):
    leaks = {
        key.split(":", 1)[1]: value for key, value in swept.items() if key.startswith(f"{scene}:")
    }
    assert not leaks, (
        f"these commands answered with an internal error on an {scene} scene "
        f"(a CommandError with a written message is the right answer): {leaks}"
    )
