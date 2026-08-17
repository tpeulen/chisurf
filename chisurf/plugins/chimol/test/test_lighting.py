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
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
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
    return viewer.renderer.lighting_state()


# --------------------------------------------------------------------------- #
# The presets
# --------------------------------------------------------------------------- #
def test_every_chimerax_preset_is_present():
    from chimol.commands.command import Cmd

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
    viewer.renderer.set_lighting(
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

    from chimol.render.scene import Geometry, Scene, SceneObject
    from chimol.core.viewer import MolView

    view = MolView()
    view.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    view.resize(160, 160)
    view.show()
    try:
        for _ in range(8):
            qapp.processEvents()
        renderer = view.renderer

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
        viewer.renderer.set_lighting(nosuchparam=1)


# --------------------------------------------------------------------------- #
# Switching an effect on must not move or erase anything else
# --------------------------------------------------------------------------- #
def _window_with_molecule(qapp):
    """A real window showing 148L, or a skip when GL is unavailable."""
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        pytest.skip("a GL context cannot be created on the offscreen platform")
    from qtpy import QtCore

    from chimol.hosts.qt.window import MolViewPluginWindow

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    window = MolViewPluginWindow()
    window.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    window.resize(1100, 780)
    window.show()
    for _ in range(10):
        qapp.processEvents()
    window._load_structure_from_path(pdb, name="148l")
    for _ in range(20):
        qapp.processEvents()

    # Force a viewport worth measuring. A window restored from a persisted dock
    # layout can hand the 3-D widget 109x350 -- less than the panel's own 220
    # pixel column -- and `scene_width` then clamps to 1. Everything still
    # "works": the effect passes decline, no outline is drawn, and a test that
    # only asked whether pixels moved would report the feature broken. Measured
    # rather than hoped: the assertion below fails instead of skipping, because
    # a guardrail that quietly stands down is the thing this file exists to
    # avoid.
    window.viewer.setMinimumWidth(760)
    window.resize(1100, 780)
    for _ in range(20):
        qapp.processEvents()
    widget = window.viewer.renderer.widget()
    assert widget.scene_width() >= 200, (
        f"the 3-D viewport is {widget.scene_width()} px wide; the window was "
        "never laid out, so nothing below would be measuring the renderer"
    )
    return window


def _frame(window, qapp) -> np.ndarray:
    """Repaint and read the framebuffer back as ``(H, W, 3)`` uint8."""
    widget = window.viewer.renderer.widget()
    for _ in range(8):
        qapp.processEvents()
    widget.makeCurrent()
    widget.paintGL()
    image = widget.grabFramebuffer()
    widget.doneCurrent()
    width, height = image.width(), image.height()
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    arr = np.frombuffer(bits, np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    return arr[:, :width, :3].copy()


def test_an_effect_pass_leaves_the_rest_of_the_frame_alone(qapp):
    """Turning silhouettes on must change edges, not the whole window.

    Two defects, both invisible to every existing test and both obvious in a
    screenshot. `_render_overlay` paints with QPainter, which targets the
    *widget's* framebuffer rather than the bound one, so running it before the
    composite meant the blit erased it -- the sequence strip vanished the moment
    any effect was switched on. And the offscreen buffer was given the window's
    full height while the direct path reserves a band for that strip, so the
    molecule was rendered centred in a taller frame and visibly jumped.

    Together they moved **10.28 %** of the pixels. A real outline moves 0.15 %.
    That ratio is the assertion: an effect pass is a local change, and anything
    that repaints most of the window is not an outline.
    """
    window = _window_with_molecule(qapp)
    try:
        from chimol.commands.command import Cmd

        cmd = Cmd(window)
        cmd.set_message_callback(lambda _m: None)
        cmd.set_error_callback(lambda _m: None)
        cmd.do("as cartoon")

        before = _frame(window, qapp)
        cmd.do("lighting silhouette=on")
        assert window.viewer.renderer._post.silhouette is True
        after = _frame(window, qapp)

        assert after.shape == before.shape
        moved = int((np.abs(after.astype(int) - before.astype(int)).max(axis=2) > 8).sum())
        fraction = moved / before[..., 0].size

        assert moved > 0, "the silhouette pass drew nothing at all"
        assert fraction < 0.02, (
            f"switching silhouettes on repainted {fraction:.2%} of the window; "
            "an outline is a local change, so this is the overlay being erased "
            "or the scene being shifted"
        )
    finally:
        window.close()


def test_the_sequence_strip_survives_an_effect_pass(qapp):
    """The strip is drawn by QPainter and was blitted over.

    Checked where the strip actually is -- the band above the 3-D viewport --
    rather than over the whole frame, because the molecule legitimately changes
    underneath it and a whole-frame comparison could not tell the two apart.
    """
    window = _window_with_molecule(qapp)
    try:
        from chimol.commands.command import Cmd

        cmd = Cmd(window)
        cmd.set_message_callback(lambda _m: None)
        cmd.set_error_callback(lambda _m: None)
        cmd.do("as cartoon")

        widget = window.viewer.renderer.widget()
        strip_logical = widget._internal_gui.sequence_height()
        if strip_logical <= 0:
            pytest.skip("this window shows no sequence strip")

        before = _frame(window, qapp)
        ratio = before.shape[0] / max(widget.height(), 1)
        band = max(1, int(strip_logical * ratio))

        cmd.do("lighting silhouette=on")
        after = _frame(window, qapp)

        # Ink coverage, not pixel equality. The strip is *there* or it is not,
        # and erasure takes this to nearly zero; exact equality would fail on a
        # difference nobody can see -- painting after a composite leaves QPainter
        # different GL state, which moves glyph antialiasing by at most 12/255
        # (mean 0.38) while the two crops are indistinguishable side by side.
        def ink(frame_band):
            return int((frame_band.max(axis=2) > 32).sum())

        ink_before, ink_after = ink(before[:band]), ink(after[:band])
        assert ink_before > 1000, "the strip band was already blank before the effect"
        assert ink_after / ink_before > 0.95, (
            f"the sequence strip lost {100 * (1 - ink_after / ink_before):.0f} % of "
            "its ink when an effect was switched on; the composite blit is "
            "covering the band it is drawn in"
        )
        assert np.abs(
            after[:band].astype(int) - before[:band].astype(int)
        ).max() < 40, "the strip band changed visibly, not just in antialiasing"
    finally:
        window.close()


# --------------------------------------------------------------------------- #
# The viewport depth cue
# --------------------------------------------------------------------------- #
def test_the_viewport_depth_cue_grades_instead_of_dimming(qapp):
    """`depth_cue` must fade the far side and leave the near side alone.

    PyMOL's `depth_cue`, `fog` and `fog_start` are **global**: `SceneSetFog`
    applies them to the viewport, and the tracer follows unless
    `ray_trace_fog` overrides. chimol had only ever applied them to the tracer
    -- the shader's `fogDensity` uniform was initialised to 0.0 and assigned
    from nowhere -- so the interactive view had no depth cue at all while `ray`
    did, and the two pictures disagreed.

    The assertion is a pair, not a single number, and that is the point. The
    tracer's own fog was once normalised over a plane fitted to nothing and
    fogged *every* pixel 24-69 %: brightness fell, every naive check passed, and
    what it produced was a dimmer. So this asserts both that something is fogged
    **and** that something is not.
    """
    window = _window_with_molecule(qapp)
    try:
        from chimol.commands.command import Cmd

        cmd = Cmd(window)
        cmd.set_message_callback(lambda _m: None)
        cmd.set_error_callback(lambda _m: None)
        cmd.do("as spheres")   # a solid body, so near and far both have pixels

        cmd.do("set depth_cue, off")
        off = _frame(window, qapp).astype(float)
        cmd.do("set depth_cue, on")
        on = _frame(window, qapp).astype(float)

        lit = off.sum(axis=2) > 40
        assert lit.sum() > 10_000, "the molecule is not on screen"

        ratio = np.ones(off.shape[:2])
        np.divide(on.sum(axis=2), off.sum(axis=2), out=ratio, where=lit)
        values = ratio[lit]

        unfogged = float((values > 0.99).mean())
        fogged = float((values < 0.90).mean())
        assert fogged > 0.005, (
            "nothing was fogged; `depth_cue` reached the viewport but changed "
            "nothing"
        )
        assert unfogged > 0.20, (
            f"only {unfogged:.1%} of the molecule came out unfogged -- the cue "
            "is being normalised over a range the molecule occupies a slice of, "
            "which is a dimmer and not a depth cue"
        )
    finally:
        window.close()


def test_turning_the_depth_cue_off_reaches_the_viewport(qapp):
    """One store, read where it is used.

    `_fog_planes` reads the config on every frame rather than caching it onto
    the renderer, so there is no second copy for `set` to leave stale -- the
    failure mode the silhouette settings still have.
    """
    window = _window_with_molecule(qapp)
    try:
        from chimol.commands.command import Cmd

        cmd = Cmd(window)
        cmd.set_message_callback(lambda _m: None)
        cmd.set_error_callback(lambda _m: None)
        renderer = window.viewer.renderer

        cmd.do("set depth_cue, on")
        _end_on, scale_on = renderer._fog_planes()
        cmd.do("set depth_cue, off")
        _end_off, scale_off = renderer._fog_planes()

        assert scale_on > 0.0, "the cue reports itself off while it is on"
        assert scale_off == 0.0, "`set depth_cue, off` did not reach the renderer"
    finally:
        window.close()
