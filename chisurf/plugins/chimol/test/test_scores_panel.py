"""The scores panel: Chimera's RMF *Features* graph, drawn with quads.

What it replaces
----------------
chimol had an RMF dock built out of Qt widgets: two combo boxes, a
``QPainter`` line plot of one series, and a Refresh button. It was never
placed in the window, it existed only where a toolkit does, and its one engine
call was ``set_visible_resolutions`` -- which is the ``resolution`` command now.

What it is instead
------------------
UCSF Chimera's RMF Viewer is the reference (its source is mirrored under
``junk/chimera-rmf/``; ``libs/rmf/gui.py`` and
``docs/UsersGuide/rmfviewer.html``). Its *Features* section shows a tree of
restraints with each one's **value at the current frame**, plots the selected
ones **across every frame** with a legend, and marks the current frame with a
**dashed vertical line you drag to move through the trajectory**: "moving the
dashed vertical line is one way to control trajectory playback".

That is what this pins, on chimol's own controls: the list is
``emtk.ListView``, the graph is ``emtk.Plot``, and a drag across the graph
issues ``frame N`` -- so it works in the browser and the toolkit-free window
too, and every scrub is echoed at the prompt like a typed command.
"""

from __future__ import annotations

import numpy as np
import pytest
from chimol.plugins.scores.window import ScoresPanel
from chimol.ui.gui import Rect
from emtk.testing import RecordingPainter

BOX = Rect(0.0, 0.0, 520.0, 260.0)
FRAMES = 50


class _State:
    def __init__(self, series):
        self.rmf_frame_series = series
        self.frames = np.zeros((FRAMES, 3, 3), dtype=np.float32)


class _Entry:
    def __init__(self, state):
        self.state = state


class _Viewer:
    """Just the doors the panel reads: the active object, and the frame."""

    def __init__(self, series=None, frame=12):
        self.objects = {
            "a": _Entry(
                _State(
                    series
                    if series is not None
                    else {
                        "Total Score": np.arange(FRAMES, dtype=float),
                        "ConnectivityRestraint": np.sin(np.arange(FRAMES, dtype=float)),
                    }
                )
            )
        }
        self.frame = frame
        self.set_frames: list[int] = []

    def get_active_object_id(self):
        return "a"

    def get_current_frame(self):
        return self.frame

    def set_current_frame(self, frame):
        self.set_frames.append(int(frame))
        self.frame = int(frame)


class _Cmd:
    def __init__(self):
        self.lines: list[str] = []

    def do(self, line):
        self.lines.append(line)


@pytest.fixture
def panel():
    return ScoresPanel(_Viewer(), _Cmd())


def _draw(panel):
    p = RecordingPainter()
    panel.draw(p, BOX)
    return p


def test_every_series_is_listed_with_its_value_at_this_frame(panel):
    """Chimera's "Value" column: what the restraint scores *now*."""
    strings = _draw(panel).strings
    assert "Total Score" in strings
    # frame 12 of `arange` is 12, and of `sin` is sin(12)
    assert "12" in strings
    assert any(s.startswith("-0.5365") for s in strings), strings


def test_the_panel_opens_with_something_plotted(panel):
    """An empty graph reads as a broken panel; Chimera's opens on a selection."""
    _draw(panel)
    assert panel.list.selection.selection() == [0]


def test_choosing_a_series_plots_it(panel):
    _draw(panel)
    row_y = BOX.y + 6.0 + 14.0 + 14.0 + 1.0  # the second row of the list
    panel.press(20.0, row_y, BOX)
    assert panel.list.selection.selection() == [1]
    strings = _draw(panel).strings
    assert "Total Score" in strings  # the legend names it


def test_a_press_in_the_graph_scrubs_the_trajectory(panel):
    """The dashed line is draggable -- the manual calls it playback control."""
    _draw(panel)
    x, y, w, h = panel._plot_box
    panel.press(x + w * 0.5, y + h * 0.5, BOX)
    assert panel.cmd.lines, "a press in the graph issued no command"
    assert panel.cmd.lines[-1].startswith("frame ")
    frame = int(panel.cmd.lines[-1].split()[1])
    assert 0 <= frame < FRAMES


def test_a_drag_keeps_scrubbing_and_a_release_stops(panel):
    _draw(panel)
    x, y, w, h = panel._plot_box
    panel.press(x + 10.0, y + 5.0, BOX)
    panel.drag(x + w - 10.0, y + 5.0, BOX)
    assert len(panel.cmd.lines) >= 2
    last = int(panel.cmd.lines[-1].split()[1])
    assert last > int(panel.cmd.lines[0].split()[1]), "the drag did not move the frame"
    panel.release()
    before = len(panel.cmd.lines)
    panel.drag(x + 20.0, y + 5.0, BOX)
    assert len(panel.cmd.lines) == before, "the drag went on after the release"


def test_the_frame_is_clamped_to_the_trajectory(panel):
    _draw(panel)
    x, y, w, h = panel._plot_box
    panel.press(x + w * 0.5, y + 5.0, BOX)
    panel.drag(x + w * 4, y + 5.0, BOX)  # dragged far past the right edge
    assert int(panel.cmd.lines[-1].split()[1]) == FRAMES - 1
    panel.drag(x - w * 4, y + 5.0, BOX)  # and far past the left one
    assert int(panel.cmd.lines[-1].split()[1]) == 0


def test_without_a_command_object_the_viewer_is_asked_directly():
    viewer = _Viewer()
    panel = ScoresPanel(viewer, None)
    _draw(panel)
    x, y, w, h = panel._plot_box
    panel.press(x + w * 0.9, y + 5.0, BOX)  # not where the frame already is
    assert viewer.set_frames, "nothing moved the frame"


def test_a_wheel_over_the_graph_never_reaches_the_camera(panel):
    _draw(panel)
    x, y, w, h = panel._plot_box
    assert panel.wheel(x + 5.0, y + 5.0, 1, BOX) is True


def test_a_trajectory_with_no_recorded_scores_still_has_something_to_show():
    """The demo everybody opens records none, and an empty graph teaches
    nothing about the panel. What the *motion* says stands in: Rg, RMSD, the
    thickness, and -- where the file stores a radius per frame -- how many
    particles are actually there.
    """
    panel = ScoresPanel(_Viewer(series={}), _Cmd())
    _draw(panel)
    assert panel.rows.names == ["· RMSD to frame 1", "· Rg", "· thickness"]
    assert panel._plot_box is not None


def test_the_computed_series_are_marked_as_computed():
    """A derived quantity must not read as one the file recorded."""
    panel = ScoresPanel(_Viewer(), _Cmd())
    _draw(panel)
    recorded = [n for n in panel.rows.names if not n.startswith("· ")]
    assert set(recorded) == {"Total Score", "ConnectivityRestraint"}
    assert [n for n in panel.rows.names if n.startswith("· ")]


def test_a_single_frame_object_has_no_series_at_all():
    """Nothing to plot over, so the panel says so rather than drawing an axis."""
    viewer = _Viewer(series={})
    viewer.objects["a"].state.frames = np.zeros((1, 3, 3), dtype=np.float32)
    panel = ScoresPanel(viewer, _Cmd())
    strings = _draw(panel).strings
    assert strings == ["This object records no per-frame scores."]
    assert panel._plot_box is None


def test_a_series_that_is_all_nan_is_left_out():
    panel = ScoresPanel(
        _Viewer(
            series={
                "good": np.arange(FRAMES, dtype=float),
                "empty": np.full(FRAMES, np.nan),
            }
        ),
        _Cmd(),
    )
    _draw(panel)
    assert "good" in panel.rows.names
    assert "empty" not in panel.rows.names
