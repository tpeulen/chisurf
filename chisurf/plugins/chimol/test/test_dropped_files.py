"""A dropped file opens, on whichever host it was dropped on.

The page took drops from the day it existed: `boot.js` writes the bytes into
the Pyodide filesystem and calls `open_path`, and
`test_browser_demos.py::test_a_dropped_file_opens` pins it. The desktop took
none. Dragging a structure onto the window did **nothing at all** -- no
message, no error, no cursor saying it would not be accepted -- while the same
file dropped on the page opened. That is the one difference between the hosts a
user meets before they have typed anything.

It is one difference for a reason worth keeping straight, and it is the only
one: a browser cannot read the path a user dragged, so the page copies the
bytes in first and passes the path it wrote. Everything after that -- what a
dropped file *means* -- is `CanvasRenderer.on_files_dropped`, which all three
hosts call:

* the page, through `Page.open_path`;
* Qt, through `dropEvent`;
* the toolkit-free window, through glfw's `set_drop_callback`, which
  `rendercanvas` does not wrap and the canvas reaches for itself.

What it means is `load` -- the same command a typed line takes, so a session, a
labelling plan, a map and a structure are dispatched by suffix by the code that
already does that, and the prompt says what happened.
"""

from __future__ import annotations

import pytest
from toolkit_free import probe

SCRIPT = '''
import pathlib, chimol
app = open_app(size=(800, 600))
renderer, gui = app.renderer, app.viewer.gui
demos = pathlib.Path(chimol.__file__).parent / "data" / "demos"
pdb = str(demos / "148l.pdb")

def atoms():
    """How many atoms are loaded, over every object.

    Counted in atoms rather than in objects: a freshly started viewer already
    holds one empty placeholder object, so "how many objects" answers one
    before anything has been opened.
    """
    total = 0
    for _name, entry in app.viewer.objects.items():
        xyz = getattr(entry.state, "all_atom_coords", None)
        total += 0 if xyz is None else len(xyz)
    return total

app.cmd.do("delete all")
emit("before", str(atoms()))
emit("opened", str(renderer.on_files_dropped([pdb])))
emit("after", str(atoms()))

emit("missing_opened", str(renderer.on_files_dropped(["/nope/absent.pdb"])))
emit("folder_opened", str(renderer.on_files_dropped([str(demos)])))
emit("said", " | ".join(entry.text for entry in gui.command_line.log[-3:]))

# Two at once, as a multi-file drag delivers them.
app.cmd.do("delete all")
emit("two", str(renderer.on_files_dropped([pdb, str(demos / "t4l_3gun.pdb")])))
emit("after_two", str(atoms()))

# An offscreen canvas has no window to drop on, and that is not an error.
emit("hooked_offscreen", str(getattr(renderer, "_drop_callback", None) is not None))
'''


@pytest.fixture(scope="module")
def dropped():
    return probe(SCRIPT, timeout=600)


def test_a_dropped_file_opens_on_the_desktop(dropped):
    """The report: dropping on the window did nothing at all."""
    assert int(dropped["before"]) == 0, "the scene was not empty to begin with"
    assert int(dropped["opened"]) == 1
    assert int(dropped["after"]) == 1363, "148L's atoms are not in the scene"


def test_several_files_at_once_all_open(dropped):
    """A drag carries a list; opening the first and dropping the rest is worse."""
    assert int(dropped["two"]) == 2
    assert int(dropped["after_two"]) == 1363 + 1293, "both files' atoms are not there"


def test_what_cannot_be_opened_is_said_rather_than_swallowed(dropped):
    """A drop is a gesture, not a script: it reports and carries on.

    A folder is the case worth naming -- dropping one is easy to do by
    accident, and opening every file inside it because it was dragged is a
    surprise nobody can undo in one step.
    """
    assert int(dropped["missing_opened"]) == 0
    assert int(dropped["folder_opened"]) == 0
    said = dropped["said"]
    assert "no such file" in said, said
    assert "folder" in said, said


def test_a_canvas_with_no_window_is_not_an_error(dropped):
    """Offscreen has nothing to drop on; the hook is simply absent."""
    assert dropped["hooked_offscreen"] == "False"


def test_the_qt_widget_accepts_dropped_files(qtbot):
    """Qt says up front whether a widget takes files, and this one does.

    Without `setAcceptDrops(True)` the drop event never arrives, and the drag
    shows the "no entry" cursor over the viewport -- which tells the user the
    window does not take files, before they have let go.
    """
    pytest.importorskip("qtpy")
    from chimol.hosts.qt.wgpu_view import WgpuRenderer

    widget = WgpuRenderer()
    qtbot.addWidget(widget)
    assert widget.acceptDrops() is True
    for name in ("dragEnterEvent", "dragMoveEvent", "dropEvent"):
        assert callable(getattr(widget, name)), f"Qt will not deliver: no {name}"


def test_the_page_opens_through_the_same_seam():
    """`Page.open_path` must not grow a second answer to "what is a drop".

    It had one -- its own `load` call -- which is how the desktop could have
    none for so long without anything looking wrong on the page.
    """
    import inspect

    from chimol.hosts.web.page import Page

    source = inspect.getsource(Page.open_path)
    assert "on_files_dropped" in source
    assert "cmd.do" not in source, "the page decides what a dropped file is again"


def test_every_host_says_it_takes_drops_and_means_it():
    """A gesture nobody is asked about is a gesture that can go missing.

    `parity.HOST_FEATURES` is the vocabulary the desktop-versus-browser report
    compares hosts in, and it had no entry for a dropped file -- so the report
    said "host gestures the browser does not deliver: 0" while the desktop
    could not take a drop at all. It is in the vocabulary now, and each host's
    claim is checked here rather than believed:

    * the page listens in `boot.js`;
    * Qt answers Qt's own question, `acceptDrops()`;
    * the toolkit-free canvas answers by *asking its canvas* -- the claim is a
      property, not a constant, because the same class is also what an
      offscreen canvas is and that one has no window to drop on.
    """
    from chimol.hosts.native.canvas import CanvasView
    from chimol.hosts.web.page import Page
    from chimol.testing.parity import HOST_FEATURES

    assert "file_drop" in dict(HOST_FEATURES)
    assert "file_drop" in Page.supported_features
    assert "file_drop" not in CanvasView._BASE_FEATURES, (
        "a windowless canvas would claim a drop it cannot take"
    )


def test_the_qt_host_describes_itself_at_all():
    """It declared nothing, being the one host the parity report never asks.

    That is the host most people run. A host with no `supported_features` is
    not "a host with no gestures" to anything reading them -- it is a host
    whose answer is an empty set, which is indistinguishable from a broken one.
    """
    import pytest

    pytest.importorskip("qtpy")
    from chimol.hosts.native.canvas import CanvasView
    from chimol.hosts.qt.wgpu_view import WgpuRenderer

    assert CanvasView._BASE_FEATURES <= WgpuRenderer.supported_features
    assert "file_drop" in WgpuRenderer.supported_features
    # The two overlays only this host rasterises, with a QPainter it alone has.
    assert {"labels", "ray_image"} <= WgpuRenderer.supported_features
