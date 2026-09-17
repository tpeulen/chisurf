"""PyMOL's per-representation colour overrides, and what makes them *live*.

``stick_color``, ``cartoon_color`` and ``surface_color`` each say "draw this
representation in *this* colour, whatever the atoms are". PyMOL implements all
three with one line, repeated in each representation --
``c != cColorDefault ? c : ai->color`` (``RepCylBond.cpp``, ``RepSurface.cpp``,
``RepRibbon.cpp``) -- where ``cColorDefault`` is the sentinel -1 meaning "no
override".

The tests below check the three things that distinguish a setting that *works*
from one that is merely registered, which is the failure mode this settings
table exists to prevent:

* the override reaches the geometry it names,
* it reaches **only** that geometry,
* and clearing it puts the atoms' own colours back.

They read the built scene rather than a pixel, because the geometry is what the
setting produces; shading is applied on top of it and would make an exact colour
comparison a test of the ambient occlusion instead.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)

#: The three overrides, the geometry each must reach, and a colour to set.
CASES = (
    ("cartoon_color", "cartoon", "red", 0),
    ("stick_color", "sticks", "blue", 2),
    ("surface_color", "surface", "green", 1),
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def viewer(qapp):
    """A window with 148L shown as cartoon, sticks and surface at once."""
    from chimol.core.settings.registry import set_setting
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    win.resize(900, 650)
    win.show()
    for _ in range(6):
        qapp.processEvents()

    def run(line: str) -> None:
        win._run_object_menu_command(line)
        for _ in range(4):
            qapp.processEvents()

    run(f"load {PDB}")
    for rep in ("cartoon", "sticks", "surface"):
        run(f"show {rep}")
    yield win, run
    # `_DISPLAY_CONFIG` is one dictionary for the whole process, so a test that
    # leaves an override set does not fail here -- it fails in another file.
    for name, _obj, _value, _channel in CASES:
        set_setting(name, "default")
    win.close()


def _hue(win, geometry_id: str):
    """Mean colour of a geometry, normalised so shading does not matter.

    Ambient occlusion multiplies the vertex colours, so the *brightness* of a
    cartoon says nothing about the setting. The ratio between the channels does.
    """
    for obj in win.viewer.get_current_scene().objects:
        if geometry_id in obj.id and obj.geometry.colors is not None:
            colors = np.asarray(obj.geometry.colors, dtype=float)[:, :3]
            mean = colors.mean(axis=0)
            return mean / max(float(mean.max()), 1e-9)
    return None


@pytest.mark.parametrize("name,geometry_id,value,channel", CASES)
def test_an_override_reaches_the_geometry_it_names(viewer, name, geometry_id, value, channel):
    win, run = viewer
    run(f"set {name}, default")
    before = _hue(win, geometry_id)
    assert before is not None, f"{geometry_id} drew nothing to colour"

    run(f"set {name}, {value}")
    after = _hue(win, geometry_id)
    assert after is not None
    assert int(np.argmax(after)) == channel, (
        f"{name} did not reach {geometry_id}: hue {np.round(after, 2)}"
    )


@pytest.mark.parametrize("name,geometry_id,value,channel", CASES)
def test_clearing_an_override_restores_the_atom_colours(viewer, name, geometry_id, value, channel):
    """`default` is PyMOL's -1, and it has to be reachable by name.

    A one-way setting is worse than none: it looks like a colour control and is
    a colour *trap*.
    """
    win, run = viewer
    run(f"set {name}, default")
    original = _hue(win, geometry_id)
    run(f"set {name}, {value}")
    run(f"set {name}, default")
    restored = _hue(win, geometry_id)
    assert original is not None and restored is not None
    assert np.allclose(original, restored, atol=1e-6), (
        f"{name} did not go back: {np.round(original, 3)} -> {np.round(restored, 3)}"
    )


def test_an_override_reaches_only_its_own_representation(viewer):
    """Three settings, three representations, no leaking between them.

    They are separate because PyMOL's are: one array of per-atom colours feeds
    several representations here, so folding an override into *that* would
    colour every one of them.
    """
    win, run = viewer
    untouched = {
        geometry_id: _hue(win, geometry_id) for _name, geometry_id, _value, _channel in CASES
    }
    run("set stick_color, blue")
    for _name, geometry_id, _value, _channel in CASES:
        now = _hue(win, geometry_id)
        if geometry_id == "sticks":
            assert int(np.argmax(now)) == 2, np.round(now, 2)
        else:
            assert np.allclose(now, untouched[geometry_id], atol=1e-6), (
                f"stick_color changed {geometry_id}"
            )


def test_pymols_own_spelling_of_default_is_accepted():
    """A script carrying `set stick_color, -1` has to keep working."""
    from chimol.core.settings.registry import coerce

    for token in ("-1", "default", "none", "atom"):
        assert coerce(token, "color_or_default") is None, token
    assert coerce("red", "color_or_default") == "red"
