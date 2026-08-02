"""``lighting`` — ChimeraX's presets, and honesty about the ones we cannot do.

Not a PyMOL command: PyMOL has no equivalent outside its ray tracer, so this is
one of the places ChiMOL is deliberately ahead of it. The preset and parameter
names are ChimeraX's, transcribed from ``std_commands/src/lighting.py``.

Two of the preset keys need shadow maps, which are not built. They are kept in
the table rather than dropped, and the command **names what it could not apply** —
a preset that quietly does three of its five things is worse than one that says
so, because `full` without its shadows is a different look and the user should
know which one they got.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(700, 500)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win.viewer, shared, do, messages, errors
    win.close()


def _state(viewer):
    return viewer._renderer.lighting_state()


# --------------------------------------------------------------------------- #
# The presets
# --------------------------------------------------------------------------- #
def test_every_chimerax_preset_is_present():
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    assert set(Cmd.LIGHTING_PRESETS) >= {
        "simple", "full", "soft", "gentle", "flat", "default"
    }


def test_a_preset_changes_the_lighting(session):
    viewer, _shared, do, _messages, errors = session
    before = _state(viewer)
    do("lighting soft")
    assert errors == []
    assert _state(viewer) != before


def test_soft_is_all_ambient_and_no_key_light(session):
    """That is what makes it soft; a key light would defeat the preset."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    state = _state(viewer)
    assert state["key_light_intensity"] == pytest.approx(0.0)
    assert state["fill_light_intensity"] == pytest.approx(0.0)
    assert state["ambient_light_intensity"] > 1.0


def test_simple_has_a_key_and_a_fill_light(session):
    viewer, _shared, do, _messages, _errors = session
    do("lighting simple")
    state = _state(viewer)
    assert state["key_light_intensity"] > 0.5
    assert state["fill_light_intensity"] > 0.0


def test_flat_turns_silhouettes_on(session):
    """Flat shading needs outlines, or the shapes stop reading."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting default")
    assert _state(viewer)["silhouette"] is False
    do("lighting flat")
    assert _state(viewer)["silhouette"] is True


def test_default_restores_a_key_light(session):
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    do("lighting default")
    assert _state(viewer)["key_light_intensity"] > 0.5


# --------------------------------------------------------------------------- #
# What it cannot do, it says
# --------------------------------------------------------------------------- #
def test_a_preset_needing_shadows_says_what_it_skipped(session):
    viewer, _shared, do, messages, errors = session
    messages.clear()
    do("lighting full")
    assert errors == []
    joined = " ".join(messages)
    assert "not applied" in joined
    assert "shadows" in joined and "multishadow" in joined


def test_a_preset_needing_nothing_extra_reports_no_gap(session):
    viewer, _shared, do, messages, _errors = session
    messages.clear()
    do("lighting simple")
    assert not any("not applied" in m for m in messages)


def test_soft_and_gentle_are_identical_until_multishadow_exists(session):
    """Not a bug: in ChimeraX they differ *only* in multishadow map size and
    depth bias, neither of which can be applied yet. Pinned so that when
    multishadow lands, this test fails and forces the difference to be real."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    soft = _state(viewer)
    do("lighting gentle")
    assert _state(viewer) == soft


# --------------------------------------------------------------------------- #
# Reporting and errors
# --------------------------------------------------------------------------- #
def test_with_no_argument_it_reports_the_current_state(session):
    viewer, _shared, do, messages, errors = session
    messages.clear()
    do("lighting")
    assert errors == []
    assert messages and "ambient_light_intensity" in messages[-1]


def test_an_unknown_preset_lists_the_real_ones(session):
    viewer, _shared, do, _messages, errors = session
    do("lighting nosuchpreset")
    assert errors and "nosuchpreset" in errors[-1]
    assert "soft" in errors[-1]


def test_the_state_round_trips_through_the_setter(session):
    """The command layer needs no translation table because the names match."""
    viewer, _shared, _do, _messages, _errors = session
    viewer._renderer.set_lighting(
        key_light_intensity=0.25, ambient_light_intensity=0.75
    )
    state = _state(viewer)
    assert state["key_light_intensity"] == pytest.approx(0.25)
    assert state["ambient_light_intensity"] == pytest.approx(0.75)


# --------------------------------------------------------------------------- #
# Overrides, through the real command line
# --------------------------------------------------------------------------- #
def test_an_override_reaches_the_renderer_through_do(session):
    """The whole ``key=value`` half used to be rejected by the argument binder."""
    viewer, _shared, do, _messages, errors = session
    do("lighting soft, ambient_light_intensity=1.2")
    assert errors == []
    assert _state(viewer)["ambient_light_intensity"] == pytest.approx(1.2)


def test_an_override_applies_after_the_preset(session):
    viewer, _shared, do, _messages, errors = session
    do("lighting simple, key_light_intensity=0.125")
    assert errors == []
    state = _state(viewer)
    assert state["key_light_intensity"] == pytest.approx(0.125)
    assert state["fill_light_intensity"] == pytest.approx(0.5)  # from the preset


def test_a_boolean_override_is_parsed_not_truth_tested(session):
    """``silhouette=0`` is off — ``bool('0')`` would have made it on."""
    viewer, _shared, do, _messages, errors = session
    do("lighting flat")
    assert _state(viewer)["silhouette"] is True
    do("lighting flat, silhouette=0")
    assert errors == []
    assert _state(viewer)["silhouette"] is False
    do("lighting default, silhouette=1")  # the example in guide 44
    assert errors == []
    assert _state(viewer)["silhouette"] is True


def test_an_override_alone_needs_no_preset(session):
    viewer, _shared, do, messages, errors = session
    messages.clear()
    do("lighting depth_jump=0.05")
    assert errors == []
    assert _state(viewer)["depth_jump"] == pytest.approx(0.05)
    assert any("parameters applied" in m for m in messages)


def test_an_unknown_parameter_is_named_not_dropped(session):
    """``set_lighting`` ignores names it does not know; the command must not."""
    viewer, _shared, do, _messages, errors = session
    do("lighting soft, nosuchparam=1")
    assert errors and "nosuchparam" in errors[-1]
    assert "ambient_light_intensity" in errors[-1]


def test_a_malformed_override_value_is_reported(session):
    viewer, _shared, do, _messages, errors = session
    before = _state(viewer)
    do("lighting silhouette=maybe")
    assert errors and "silhouette" in errors[-1]
    assert _state(viewer) == before


# --------------------------------------------------------------------------- #
# The pixels, not the stored state
# --------------------------------------------------------------------------- #
# The tests above read `lighting_state()`, the stored Python attributes. That is
# exactly what let RF-318 ship: the key and fill intensities were computed into a
# shader local nothing read, so every preset test passed while `simple` and
# `default` rendered identically. These two render a real quad into the
# framebuffer and assert the pixels move.
def _framebuffer_frame(qapp, *, ambient, key, fill=0.0, tilt=0.0):
    """Render a quad under *lighting* and return its 8-bit RGB array.

    The quad faces the camera (``tilt=0``) or is turned about the X axis by
    ``tilt`` degrees; ``two_sided`` keeps it visible edge-on. ``key=0, fill=0``
    leaves pure ambient, which is what isolates the ambient coefficient.

    A ``QOpenGLWidget`` needs a real GL context, which the offscreen platform
    cannot create and a session without a window server cannot read back. Both
    cases skip rather than assert on a black image.
    """
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        pytest.skip("a GL context cannot be created on the offscreen platform")
    from qtpy import QtCore, QtGui

    from chisurf.plugins.chimol.chimol.renderer.scene import (
        Geometry,
        Scene,
        SceneObject,
    )
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    view.resize(160, 160)
    view.show()
    try:
        for _ in range(8):
            qapp.processEvents()
        renderer = view._renderer

        th = np.radians(tilt)
        c, s = float(np.cos(th)), float(np.sin(th))
        rot = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
        quad = np.array(
            [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], dtype=np.float32
        ).dot(rot)
        indices = np.array([0, 1, 2, 0, 2, 3])
        geo = Geometry(
            kind="mesh",
            positions=quad,
            indices=indices,
            colors=np.tile(np.array([0.6, 0.6, 0.6, 1.0], dtype=np.float32), (4, 1)),
            meta={"two_sided": True},
        )
        renderer.set_scene(Scene(objects=[SceneObject(id="quad", geometry=geo)]))
        renderer.set_lighting(
            ambient_light_intensity=ambient,
            key_light_intensity=key,
            fill_light_intensity=fill,
        )
        for _ in range(8):
            qapp.processEvents()
        image = renderer.grabFramebuffer()
        if image.isNull():
            pytest.skip("the GL framebuffer came back null -- no window server")
        image = image.convertToFormat(QtGui.QImage.Format_RGBA8888)
        buf = image.bits()
        buf.setsize(image.width() * image.height() * 4)
        return np.frombuffer(buf, dtype=np.uint8).reshape(
            image.height(), image.width(), 4
        )[..., :3].astype(int)
    finally:
        view.close()


def _region_mean(frame: np.ndarray) -> float:
    """Mean brightness over the drawn quad (pixels that are not background)."""
    mask = frame.sum(axis=2) > 40
    if not mask.any():
        return 0.0
    return float(frame[mask].mean())


def test_the_key_light_moves_pixels(qapp):
    """RF-318: the key intensity used to be computed into a dead shader local.

    ``key_light_intensity`` reached the fragment shader, was folded into a
    ``lighting`` value that nothing downstream read, and so could not affect
    ``gl_FragColor``: ``lighting simple`` and ``lighting default`` rendered
    identically. Only the framebuffer can catch that.
    """
    lit = _framebuffer_frame(qapp, ambient=0.5, key=1.0)
    unlit = _framebuffer_frame(qapp, ambient=0.5, key=0.0)
    assert _region_mean(unlit) > 20, "the quad should be visible under pure ambient"
    assert _region_mean(lit) > _region_mean(unlit) + 15, (
        f"the key light changed no pixels "
        f"({_region_mean(lit):.1f} vs {_region_mean(unlit):.1f})"
    )


def test_an_ambient_above_one_clamps_instead_of_inverting(qapp):
    """RF-320: the soft/gentle/flat presets push ambient past 1.

    In the mixing formula an ambient above ``1 / 0.7`` makes the diffuse weight
    negative -- a face turned from the light rendered *brighter* than one facing
    it, and brighter than the same face at ambient 1.0. Clamped, the excess is
    simply not applied, so ambient 1.5 must not brighten a partially lit face.
    """
    low = _framebuffer_frame(qapp, ambient=1.0, key=0.0, tilt=45.0)
    high = _framebuffer_frame(qapp, ambient=1.5, key=0.0, tilt=45.0)
    assert _region_mean(low) > 20, "the tilted quad should be visible"
    assert _region_mean(high) <= _region_mean(low) + 2, (
        f"ambient 1.5 is brighter than 1.0 "
        f"({_region_mean(high):.1f} > {_region_mean(low):.1f}) -- "
        "the diffuse weight went negative"
    )


def test_set_lighting_rejects_an_unknown_name(session):
    """RF-320: the renderer must not silently drop a parameter it cannot apply.

    ``set_lighting`` used to ignore names outside its mapping while the command
    still reported ``lighting: ... applied`` -- the silent-no-op the command
    layer now guards against, and the renderer should too for Python-API callers.
    """
    viewer, _shared, _do, _messages, _errors = session
    with pytest.raises(ValueError, match="unknown parameter 'nosuchparam'"):
        viewer._renderer.set_lighting(nosuchparam=1)
