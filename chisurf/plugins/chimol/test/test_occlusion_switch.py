"""The ambient-occlusion switch must darken when on, and do nothing when off.

Why this test exists
--------------------
``occlusion.enabled`` did the opposite of what it says. Only one of six
``_estimate_ambient_occlusion`` call sites consulted it, and that one read it
inverted, so the coarse per-residue fallback -- the only occlusion a cartoon ever
received -- appeared exactly when the user switched occlusion *off*. The other
five shaded regardless of the setting.

Nothing caught it because "is the setting registered" and "does the setting do
anything" are different claims, and only the second one matters. So this test
asserts the second: it renders the same scene twice and compares the pixels.

Two directions have to be asserted, not one. A test that only checks "the image
changed" passes an inverted switch, which is how the defect survived.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

import numpy as np
import pytest

os.environ.setdefault(
    "CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chimol_ao_test_")
)

_PDB = str(
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)

#: Representations that bake ambient occlusion. ``sticks`` is deliberately absent:
#: it has no occlusion path at all (measured: toggling the switch changes zero
#: pixels), which is a missing feature rather than a broken switch.
OCCLUDED_REPRESENTATIONS = ("cartoon", "spheres", "surface")


def _grab(win, app):
    from chisurf.plugins.chimol.test.screenshot import grab_gl

    image = grab_gl(win)
    bits = image.constBits()
    size = image.sizeInBytes() if hasattr(image, "sizeInBytes") else image.byteCount()
    bits.setsize(size)
    arr = np.frombuffer(bits, np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4
    )
    return arr[:, : image.width(), :3].astype(int)


@pytest.fixture(scope="module")
def viewer():
    """A realised viewer with 148L loaded, or a skip when GL is unavailable."""
    pytest.importorskip("qtpy")
    from pathlib import Path

    from chisurf.plugins.chimol.test.screenshot import (
        assert_view_usable,
        ensure_app,
    )

    try:
        app = ensure_app()
    except RuntimeError as exc:  # offscreen platform: no GL context at all
        pytest.skip(str(exc))

    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(1280, 860)
    win.show()
    for _ in range(12):
        app.processEvents()
    win.load_structure_from_path(Path(_PDB))
    for _ in range(25):
        app.processEvents()
    shared.set_window(win)

    # A restored layout can leave the 3-D view a strip for several cycles; a
    # strip makes every pixel assertion below meaningless.
    for _ in range(40):
        try:
            assert_view_usable(win)
            break
        except RuntimeError:
            win.resize(1280, 860)
            for _ in range(10):
                app.processEvents()
    else:
        assert_view_usable(win)

    def render(script):
        for line in script:
            shared.do(line)
            for _ in range(12):
                app.processEvents()
        # The first grab after a rebuild can be a partially initialised buffer
        # -- it comes back as noise and poisons any brightness comparison.
        _grab(win, app)
        for _ in range(8):
            app.processEvents()
        return _grab(win, app)

    render(["hide everything", "show cartoon", "orient"])  # warm the pipeline
    yield render
    win.close()


@pytest.mark.parametrize("representation", OCCLUDED_REPRESENTATIONS)
def test_occlusion_switch_darkens_when_on(viewer, representation):
    """Switching occlusion on must darken the representation, not brighten it."""
    base = ["hide everything", "color grey80", f"show {representation}", "orient"]
    off = viewer(base + ["set occlusion.enabled, off"])
    on = viewer(base + ["set occlusion.enabled, on"])

    changed = int((np.abs(on - off).sum(2) > 0).sum())
    assert changed > 500, (
        f"{representation}: occlusion.enabled changed {changed} pixels; the "
        f"switch is not reaching this representation at all"
    )

    # Compare only lit pixels: the background is most of the frame and dilutes
    # the mean until an inverted switch looks like a rounding difference.
    lit = off.sum(2) > 30
    assert lit.sum() > 1000, "almost nothing is lit; the scene did not render"
    mean_on, mean_off = on[lit].mean(), off[lit].mean()
    assert mean_on < mean_off, (
        f"{representation}: occlusion ON is brighter than OFF "
        f"({mean_on:.2f} vs {mean_off:.2f}) -- the switch is inverted"
    )


def test_occlusion_has_one_enable_key():
    """Exactly one config key may enable occlusion.

    ``sticks.ambient_occlusion`` was a second, dead one: registered, reachable
    through ``set``, stored on change, and read by nothing. Two keys for one
    concept is the shape every silent drift in this codebase has had.
    """
    from chimol.core.settings.config import _DISPLAY_CONFIG

    def walk(node, path=()):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from walk(value, path + (key,))
        else:
            yield ".".join(path)

    enablers = [
        dotted
        for dotted in walk(_DISPLAY_CONFIG)
        if dotted.split(".")[-1] in ("ambient_occlusion",)
        or dotted == "occlusion.enabled"
    ]
    assert enablers == ["occlusion.enabled"], (
        f"expected occlusion.enabled to be the only occlusion switch, found {enablers}"
    )
