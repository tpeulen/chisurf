"""A picture behind the scene, and mesh normals that point out of the mesh.

These belong together because one exposed the other. Transparency is invisible
against a flat background -- a surface at alpha 0.4 over black is just a darker
surface -- so a backdrop was added to make it legible. It made something else
legible too: the metaball could not be made transparent *at all*, at any alpha,
because every one of its normals pointed **inward**.

That is not a subtle shading error. `fresnel = pow(1 - dot(n, view))` is ~2 for
an inward normal, clamps to 1, and the shader mixes alpha toward opaque with it.
The mesher negated its normals under a comment saying it was making them point
outward, and nothing caught it for as long as the only consumer replaced them
with density-gradient normals anyway.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.core.settings.config import _DISPLAY_CONFIG
from chimol.io.atoms import make_bead_rows
from chimol.render import backdrop
from chimol.core.viewer import MolView


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# --------------------------------------------------------------------------- #
# Normals
# --------------------------------------------------------------------------- #
@pytest.fixture
def blob(_qt_app):
    """Return a viewer showing a metaball over a compact cloud of beads."""
    rng = np.random.default_rng(0)
    xyz = rng.normal(scale=7.0, size=(300, 3))
    view = MolView()
    view.set_coordinates(
        xyz, atoms=make_bead_rows(xyz), atom_radii=np.full(len(xyz), 3.0)
    )
    view.set_metaballs_visible(True)
    view._draft_quality = False
    return view


def _outward_fraction(scene_object) -> float:
    """How many normals point away from the mesh's own centre."""
    normals = np.asarray(scene_object.geometry.normals, dtype=float)
    points = np.asarray(scene_object.geometry.positions, dtype=float)
    outward = points - points.mean(axis=0)
    outward /= np.linalg.norm(outward, axis=1, keepdims=True) + 1e-12
    return float(np.mean(np.einsum("ij,ij->i", normals, outward) > 0.0))


def test_metaball_normals_point_out_of_the_surface(blob):
    """Inward normals make the surface opaque and lit from inside its own body.

    A blob is convex enough that "away from the centroid" is a fair test: the
    broken version scored **0.00** and the fixed one scores near 1.
    """
    obj = blob._update_metaballs(
        np.asarray(blob._coords, dtype=float), _DISPLAY_CONFIG["metaball"], None
    )[0]
    assert _outward_fraction(obj) > 0.9


def test_metaball_normals_are_unit_length(blob):
    obj = blob._update_metaballs(
        np.asarray(blob._coords, dtype=float), _DISPLAY_CONFIG["metaball"], None
    )[0]
    lengths = np.linalg.norm(np.asarray(obj.geometry.normals, dtype=float), axis=1)
    assert np.allclose(lengths, 1.0, atol=1e-3)


def test_a_transparent_metaball_goes_to_the_transparent_pass(blob):
    """Alpha below 1 must reach the renderer as alpha, and as a pass."""
    cfg = dict(_DISPLAY_CONFIG["metaball"], alpha=0.45)
    obj = blob._update_metaballs(np.asarray(blob._coords, dtype=float), cfg, None)[0]

    assert obj.render_mode == "transparent"
    assert np.allclose(np.asarray(obj.geometry.colors)[:, 3], 0.45)


# --------------------------------------------------------------------------- #
# The backdrop
# --------------------------------------------------------------------------- #
def test_the_starfield_has_stars_and_stays_dark():
    """Dark overall, with a sparse scatter of bright points.

    Both halves matter: a bright backdrop competes with the molecule, and one
    with no small sharp features gives the eye nothing to see *through* the
    surface.
    """
    sky = backdrop.starfield(320, 240, seed=3)

    assert sky.shape == (240, 320, 3)
    assert sky.dtype == np.uint8

    luminance = sky.mean(axis=2)
    assert luminance.mean() < 60, "the backdrop must stay dark"
    bright = luminance > 180
    assert 0 < bright.sum() < luminance.size * 0.02, "sparse bright points"


def test_the_starfield_is_reproducible():
    """The same seed gives the same sky.

    A screenshot compared against a previous one must differ because the
    *rendering* changed, not because the sky was re-rolled.
    """
    first = backdrop.starfield(160, 120, seed=11)
    second = backdrop.starfield(160, 120, seed=11)
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, backdrop.starfield(160, 120, seed=12))


def test_the_backdrop_is_rendered_at_the_size_asked_for():
    """Generated per widget size rather than stretched from a fixed image."""
    small = backdrop.render_backdrop("stars", 64, 48)
    large = backdrop.render_backdrop("nebula", 200, 100)
    assert small.shape == (48, 64, 3)
    assert large.shape == (100, 200, 3)


def test_an_unknown_backdrop_name_is_refused():
    """So a typo falls through to the file-path branch instead of drawing noise."""
    assert backdrop.render_backdrop("definitely-not-a-backdrop", 32, 32) is None


@pytest.mark.parametrize("name", sorted(set(backdrop.BACKDROPS)))
def test_every_advertised_backdrop_renders(name):
    """A name offered in the command's help must produce a picture."""
    image = backdrop.render_backdrop(name, 48, 32)
    assert image is not None and image.shape == (32, 48, 3)


# --------------------------------------------------------------------------- #
# Setting it on the renderer
# --------------------------------------------------------------------------- #
@pytest.fixture
def gl_widget(_qt_app):
    """Return the GL widget a viewer owns; it is never realised here.

    Taken from a `MolView` rather than constructed directly, because the widget
    takes the viewer as its controller. No GL context is needed: setting a
    background only resolves the source and marks it dirty.
    """
    return MolView()._renderer


def test_a_named_backdrop_is_accepted_and_reported(gl_widget):
    gl_widget.set_background_image("stars")
    assert gl_widget.get_background_image() == "stars"


def test_turning_it_off_clears_both_the_source_and_the_image(gl_widget):
    gl_widget.set_background_image("stars")
    gl_widget.set_background_image("off")
    assert gl_widget.get_background_image() == "off"
    assert gl_widget._background_image is None


def test_a_path_that_cannot_be_read_is_refused_and_not_recorded(gl_widget, tmp_path):
    """A refused background must not be reported as the current one.

    The source was recorded before the image was resolved, so `bg_image` named a
    picture that had never loaded and was nowhere on screen -- which reads as the
    command having worked and the backdrop being broken.
    """
    gl_widget.set_background_image("stars")
    missing = tmp_path / "not-an-image.png"

    with pytest.raises(ValueError):
        gl_widget.set_background_image(str(missing))

    assert gl_widget.get_background_image() == "stars", "a refused path was recorded"


def test_an_array_can_be_set_directly(gl_widget):
    """So a generated or computed backdrop needs no temporary file."""
    sky = backdrop.starfield(32, 24)
    gl_widget.set_background_image(sky)
    assert gl_widget._background_image is not None
    assert gl_widget._background_image.width() == 32


# --------------------------------------------------------------------------- #
# A path that is not there
# --------------------------------------------------------------------------- #
def test_a_missing_file_is_refused_rather_than_parsed_into_one_atom(tmp_path):
    """`load` of a mistyped path must fail, not produce an empty molecule.

    Found while checking the commands this guide prints: the reader falls back
    to its own PDB parser whenever the core reader cannot handle a file, and a
    path that does not exist took that branch too. The result was a single atom
    at the origin -- `load` reported success, the object panel listed the
    molecule, and the viewport was empty, which reads as a broken *renderer*.
    """
    from chimol.io.structure import load_structure_payload

    with pytest.raises(FileNotFoundError):
        load_structure_payload(tmp_path / "definitely-not-here.pdb")
