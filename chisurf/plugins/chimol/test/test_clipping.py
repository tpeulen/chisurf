"""A clipped surface does not look clipped -- it looks broken.

Cutting the near plane into a closed surface opens it, and what you see then is
the *inside*: the cartoon within renders unblended, at full brightness, with
hard edges where the surface was sliced. That reads as transparency having
failed, not as a cut, and it was reported as exactly that -- more than once,
because nothing on screen said the slab had moved and nothing obvious put it
back.

The gesture is one stray shift-scroll away (ctrl-scroll too, and on a trackpad
that is easy to hit by accident). So: say what happened, and make framing the
way back.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def viewer():
    """Return a viewer framed on a 30 Å scene, so the planes have a baseline."""
    from native_window import native_viewer

    view = native_viewer()
    view.renderer.fit_to_radius(30.0)
    yield view
    view.native_window.close()


def test_framing_defines_what_unclipped_means(viewer):
    assert viewer.renderer.clipping_is_default() is True


def test_moving_the_near_plane_is_not_the_default(viewer):
    viewer.clip("near", 8.0)
    assert viewer.renderer.clipping_is_default() is False


def test_clip_reset_restores_the_planes(viewer):
    """The way back for someone who does not know what they pressed."""
    renderer = viewer.renderer
    before = renderer._near_clip

    viewer.clip("near", 8.0)
    viewer.clip("reset", 0.0)

    assert renderer._near_clip == pytest.approx(before)
    assert renderer.clipping_is_default() is True


@pytest.mark.parametrize("spelling", ["reset", "off", "none"])
def test_the_spellings_that_mean_stop_clipping(viewer, spelling):
    """Someone who wants it gone will type one of these, not compute a distance."""
    viewer.clip("near", 6.0)
    viewer.clip(spelling, 0.0)
    assert viewer.renderer.clipping_is_default() is True


def test_framing_the_scene_undoes_a_stray_slice(viewer):
    """`zoom` and `orient` re-frame, and re-framing is what "not clipped" means.

    This matters more than the command: someone whose view has gone strange
    reaches for zoom long before they suspect the clipping planes.
    """
    renderer = viewer.renderer
    viewer.clip("near", 8.0)
    assert renderer.clipping_is_default() is False

    renderer.fit_to_radius(30.0)
    assert renderer.clipping_is_default() is True


def test_the_wheel_says_what_it_did(viewer):
    """A silent, sticky mode change is the actual defect.

    Clipping by mouse wheel left no trace at all: no status line, no visible
    control, nothing in the log. The picture changed and nothing said why.
    """
    from emtk.events import SHIFT_MODIFIER

    messages: list[str] = []
    viewer.statusMessage.connect(messages.append)
    renderer = viewer.renderer

    # One shifted notch at (10, 10), as the host's canvas delivers it.
    renderer.on_wheel(10.0, 10.0, 1, SHIFT_MODIFIER)

    assert messages, "clipping by wheel said nothing"
    assert "clip reset" in messages[-1], "the message must name the way back"


def test_the_message_reports_when_clipping_is_off_again(viewer):
    from emtk.events import SHIFT_MODIFIER

    messages: list[str] = []
    viewer.statusMessage.connect(messages.append)
    renderer = viewer.renderer

    for notches in (1, -1):
        renderer.on_wheel(10.0, 10.0, notches, SHIFT_MODIFIER)

    assert messages[-1] == "Clipping: off"
