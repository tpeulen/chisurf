"""``ray`` through the command path, on a viewer with a real scene.

The unit tests beside this one cover the tracer. These cover the decision `ray`
makes before it starts: *what is shown, and can it be drawn?* That decision was
made from the sphere count, which is zero on the display PyMOL and chimol both
start with, so `ray` answered a cartoon with "the ray tracer draws spheres, and
cannot yet trace the cartoon" -- a limitation the tracer had already lost.

These render at 120x100 with one sample per pixel: enough to prove a picture of
the molecule came out, cheap enough to run every time.
"""

from __future__ import annotations

import pathlib
import shutil

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    src = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    pdb = tmp_path / "148l.pdb"
    shutil.copyfile(src, pdb)

    win = MolViewPluginWindow()
    win._load_structure_from_path(pdb, name="148l")
    return win


@pytest.fixture
def cmd(window):
    from chisurf.plugins.chimol.chimol import config as chimol_config
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    # One sample per pixel. `_DISPLAY_CONFIG` is process-wide, so it is restored
    # in place rather than replaced -- a dict swapped here changes other files.
    ray_cfg = chimol_config._DISPLAY_CONFIG.setdefault("ray", {})
    before = ray_cfg.get("antialias")
    ray_cfg["antialias"] = 1

    c = Cmd(window)
    messages, errors = [], []
    c.set_message_callback(messages.append)
    c.set_error_callback(errors.append)
    c._test_messages = messages  # type: ignore[attr-defined]
    c._test_errors = errors  # type: ignore[attr-defined]
    yield c

    if before is None:
        ray_cfg.pop("antialias", None)
    else:
        ray_cfg["antialias"] = before


def _ray(cmd, out: pathlib.Path, size: str = "120, 100", timeout: float = 180.0):
    """Run `ray` and wait for the render thread it starts.

    With a window present `ray` renders on a ``QThread`` and returns at once, so
    a test that looks at the file immediately sees nothing. Waiting also matters
    for the *next* test: a render still running when its window is destroyed
    takes the interpreter down with it.
    """
    import time

    from qtpy import QtWidgets

    cmd._test_messages.clear()  # type: ignore[attr-defined]
    cmd._test_errors.clear()  # type: ignore[attr-defined]
    cmd.do(f"ray {out}, {size}")

    app = QtWidgets.QApplication.instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if app is not None:
            app.processEvents()
        if out.exists() or cmd._test_errors:  # type: ignore[attr-defined]
            break
        if any(  # a refusal, which never starts a thread
            "nothing to trace" in m or "does not draw" in m
            for m in cmd._test_messages  # type: ignore[attr-defined]
        ):
            break
        time.sleep(0.02)
    if app is not None:
        app.processEvents()


def _drawn_pixels(path: pathlib.Path) -> int:
    """How many pixels are not background."""
    from PIL import Image

    img = np.asarray(Image.open(path).convert("RGB"))
    return int((img.max(axis=2) > 8).sum())


# --------------------------------------------------------------------------- #
# What gets traced
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "representation", ["cartoon", "sticks", "lines", "spheres"]
)
def test_every_representation_reaches_the_image(cmd, tmp_path, representation):
    """`ray` traces the scene, so whatever the viewport draws comes out."""
    cmd.do(f"as {representation}")
    out = tmp_path / f"{representation}.png"
    _ray(cmd, out)
    assert cmd._test_errors == [], cmd._test_errors  # type: ignore[attr-defined]
    assert out.exists(), f"ray wrote nothing for {representation}"
    assert _drawn_pixels(out) > 200, f"{representation} traced to an empty image"


def test_the_cartoon_no_longer_refuses(cmd, tmp_path):
    """The exact regression: a cartoon-only display used to be turned away."""
    cmd.do("as cartoon")
    out = tmp_path / "cartoon.png"
    _ray(cmd, out)
    assert not any("cannot" in e for e in cmd._test_errors)  # type: ignore[attr-defined]
    assert out.exists()


def test_the_message_names_what_is_being_traced(cmd, tmp_path):
    cmd.do("as cartoon")
    _ray(cmd, tmp_path / "c.png")
    said = " ".join(cmd._test_messages)  # type: ignore[attr-defined]
    assert "mesh" in said, said


# --------------------------------------------------------------------------- #
# What is not traced, and what is not shown
# --------------------------------------------------------------------------- #
def test_labels_are_reported_as_missing_from_the_image(cmd, tmp_path):
    """A label is rasterised glyphs and the tracer has no glyph. Say so."""
    cmd.do("as cartoon")
    cmd.do("label name CA and resi 20-30, resi")
    _ray(cmd, tmp_path / "labelled.png")
    said = " ".join(cmd._test_messages)  # type: ignore[attr-defined]
    assert "not traced" in said and "text" in said, said


def test_nothing_shown_is_reported_and_nothing_is_drawn(cmd, tmp_path):
    """The fallback used to offer the atoms after `hide everything`.

    The scene was empty, the viewport blank, and `ray` drew the 32 ligand atoms
    that ``get_atom_sphere_data(visible_only=True)`` still called visible.
    """
    cmd.do("hide everything")
    out = tmp_path / "empty.png"
    _ray(cmd, out)
    said = " ".join(cmd._test_messages)  # type: ignore[attr-defined]
    assert "nothing" in said.lower(), said
    assert not out.exists(), "ray drew a molecule the viewport was not showing"


# --------------------------------------------------------------------------- #
# Progress reporting
# --------------------------------------------------------------------------- #
def test_the_progress_display_survives_the_whole_qprogressdialog_setup(qapp, window):
    """`ray` drove `ChiSurfProgress` as if it were a ``QProgressDialog``.

    The facade carries most of that surface on purpose, so five of the six calls
    worked and the sixth raised ``'ChiSurfProgress' object has no attribute
    'setMinimumSize'`` -- before a single ray was cast, on every run that had a
    window, which is every run a user makes. Only the headless path, which skips
    the display entirely, ever worked, and that is the path the tests took.

    Both ends are pinned: the facade answers the calls, and `ray` uses its own
    spelling rather than relying on the shim.
    """
    from chisurf.gui.progress import ChiSurfProgress

    progress = ChiSurfProgress(window, "Ray tracing...", 100, title="Rendering")
    try:
        for call, args in (
            ("setWindowTitle", ("Rendering",)),
            ("setMinimumDuration", (0,)),
            ("setValue", (0,)),
            ("setAutoClose", (False,)),
            ("setAutoReset", (False,)),
            ("setMinimumSize", (360, 100)),
        ):
            getattr(progress, call)(*args)
        # What `ray` itself calls.
        progress.set_value(50)
        progress.set_text("Ray tracing... 50%")
        assert progress.was_canceled() is False
    finally:
        progress.close()
    progress.deleteLater()  # a Qt call site closes and then deletes


# --------------------------------------------------------------------------- #
# Transparency
# --------------------------------------------------------------------------- #
def _shell_over_ball(shell_alpha: float):
    """A grey shell in front of a red ball, traced. Returns the centre pixel.

    Built here rather than from a molecule because a molecular scene colours the
    surface from the *atoms*: `color red` reddens the shell as well as what is
    inside it, so "is there red in the image" stops separating the two cases.
    Two spheres make the question exact -- red can only reach the centre pixel
    by passing through the shell.
    """
    import numpy as np
    from chisurf.plugins.chimol.chimol.renderer.raytracer import (
        RayCamera,
        Sphere,
        trace,
    )

    camera = RayCamera(
        origin=np.array([0.0, 0.0, 12.0]),
        forward=np.array([0.0, 0.0, -1.0]),
        up=np.array([0.0, 1.0, 0.0]),
        fov_degrees=45.0,
    )
    spheres = [
        Sphere(np.array([0.0, 0.0, 0.0]), 3.0, np.array([0.8, 0.8, 0.9]), shell_alpha),
        Sphere(np.array([0.0, 0.0, -1.0]), 1.0, np.array([1.0, 0.1, 0.1]), 1.0),
    ]
    img = trace(
        spheres, camera, np.array([[0.3, 0.6, 0.7]]),
        width=160, height=120, ssaa=1, shadow=False, background=(0, 0, 0),
    )
    return img[60, 80].astype(int)


def test_a_translucent_surface_shows_what_is_behind_it():
    """The ray walks through the shell instead of stopping at it."""
    r, g, b = _shell_over_ball(0.35)
    assert r > g + 20 and r > b + 20, f"centre pixel {(r, g, b)} is not red"


def test_an_opaque_surface_still_hides_what_is_behind_it():
    """The other half: compositing must not leak colour through a solid surface."""
    r, g, b = _shell_over_ball(1.0)
    assert not (r > g + 20 and r > b + 20), f"centre pixel {(r, g, b)} leaked red"


def test_a_fully_clear_surface_is_the_ball_alone():
    """At alpha 0 the shell contributes nothing and must not tint what it covers."""
    clear = _shell_over_ball(0.0)
    assert clear[0] > clear[1] + 40, f"centre pixel {tuple(clear)} is not the red ball"


def test_an_opaque_scene_does_not_pay_for_the_layer_walk(cmd, tmp_path):
    """The walk stops at the first solid surface rather than spending its budget.

    Measured on 148L at 300x220: 3.6 s with four layers allowed against 3.8 s
    with one, i.e. free when nothing is translucent. This is a smoke check
    against that early-out disappearing, not a benchmark.
    """
    import time

    cmd.do("hide everything")
    cmd.do("show surface")
    cmd.do("set transparency, 0")
    start = time.time()
    _ray(cmd, tmp_path / "solid.png", size="200, 150")
    elapsed = time.time() - start
    assert (tmp_path / "solid.png").exists()
    assert elapsed < 120.0, f"opaque render took {elapsed:.0f}s"


def test_a_translucent_molecular_scene_renders(cmd, tmp_path):
    """End to end: the command path survives a scene with alpha in it."""
    cmd.do("hide everything")
    cmd.do("show cartoon")
    cmd.do("show surface")
    cmd.do("set transparency, 0.6")
    out = tmp_path / "translucent.png"
    _ray(cmd, out, size="200, 150")
    assert cmd._test_errors == [], cmd._test_errors  # type: ignore[attr-defined]
    assert out.exists()
    assert _drawn_pixels(out) > 200
