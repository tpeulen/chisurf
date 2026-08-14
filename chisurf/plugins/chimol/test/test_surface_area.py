"""Surface area, against PyMOL's dot sampling and against analytic geometry.

Solvent accessibility decides where a dye can be attached and how freely it moves,
so ``get_area`` is one of the few numbers a viewer computes that feeds back into
experiment design. That makes it worth checking against geometry rather than
against itself: a dot-sampling bug produces a plausible number, not an obviously
wrong one.

Three levels of check here, in increasing strength:

* the tessellation reproduces PyMOL's, dot for dot, and its weights sum to 4π;
* isolated and touching spheres match closed-form areas;
* a random cluster converges to an independently written Shrake-Rupley using a
  *different* sphere and uniform weights, so a shared mistake in the tessellation
  cannot hide.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.analysis.surface_area import (
    DOT_COUNTS,
    atom_surface_areas,
    geodesic_sphere,
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


# --------------------------------------------------------------------------- #
# The tessellation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("level, expected", list(enumerate(DOT_COUNTS)))
def test_dot_counts_match_pymols(level, expected):
    """``Sphere_nDot`` in layer0/SphereData.h: an icosahedron subdivided 0-4 times."""
    dots, _ = geodesic_sphere(level)
    assert len(dots) == expected


def test_the_dots_are_on_the_unit_sphere():
    dots, _ = geodesic_sphere(3)
    assert np.allclose(np.linalg.norm(dots, axis=1), 1.0)


@pytest.mark.parametrize("level", range(5))
def test_the_weights_sum_to_four_pi(level):
    """``MakeDotSphere`` refuses to build a sphere whose areas do not."""
    _, weights = geodesic_sphere(level)
    assert weights.sum() == pytest.approx(4.0 * np.pi, abs=1e-9)


def test_the_weights_are_not_uniform():
    """The detail a spiral sphere gets wrong.

    On a geodesic sphere the twelve original icosahedron vertices have five
    neighbours where every later vertex has six, so their solid angles differ.
    Using ``4*pi/n`` for all of them is wrong by a few percent.
    """
    _, weights = geodesic_sphere(2)
    assert weights.min() / weights.max() < 0.8


def test_a_sphere_is_built_once():
    """Rebuilding per atom would dominate the cost of the whole calculation."""
    first, _ = geodesic_sphere(2)
    second, _ = geodesic_sphere(2)
    assert first is second


# --------------------------------------------------------------------------- #
# Closed-form geometry
# --------------------------------------------------------------------------- #
def test_an_isolated_atom_has_the_area_of_its_sphere():
    radius = 1.7
    area = atom_surface_areas(np.zeros((1, 3)), np.array([radius]))
    assert area[0] == pytest.approx(4.0 * np.pi * radius**2, rel=1e-12)


def test_the_probe_inflates_the_sphere():
    """`dot_solvent` on measures the accessible surface, at ``r + probe``."""
    radius, probe = 1.7, 1.4
    area = atom_surface_areas(
        np.zeros((1, 3)), np.array([radius]),
        dot_solvent=True, solvent_radius=probe,
    )
    assert area[0] == pytest.approx(4.0 * np.pi * (radius + probe) ** 2, rel=1e-12)


def test_the_probe_is_ignored_when_dot_solvent_is_off():
    """PyMOL's default measures the van der Waals surface."""
    radius = 1.7
    area = atom_surface_areas(
        np.zeros((1, 3)), np.array([radius]), solvent_radius=5.0
    )
    assert area[0] == pytest.approx(4.0 * np.pi * radius**2, rel=1e-12)


@pytest.mark.parametrize(
    "density, tolerance", [(0, 0.08), (2, 0.02), (4, 0.003)]
)
def test_two_overlapping_spheres_lose_their_caps(density, tolerance):
    """Each sphere loses a spherical cap of height ``r - d/2``, exactly."""
    radius, separation = 1.7, 3.0
    areas = atom_surface_areas(
        np.array([[0.0, 0, 0], [separation, 0, 0]]),
        np.array([radius, radius]),
        dot_density=density,
    )
    cap = radius - separation / 2.0
    exact = 4.0 * np.pi * radius**2 - 2.0 * np.pi * radius * cap
    assert areas[0] == pytest.approx(exact, rel=tolerance)
    assert areas[1] == pytest.approx(exact, rel=tolerance)


def test_accuracy_improves_with_density():
    """Which is what ``dot_density`` is for; a level that did not would be a bug."""
    radius, separation = 1.7, 3.0
    cap = radius - separation / 2.0
    exact = 4.0 * np.pi * radius**2 - 2.0 * np.pi * radius * cap
    errors = [
        abs(
            atom_surface_areas(
                np.array([[0.0, 0, 0], [separation, 0, 0]]),
                np.array([radius, radius]),
                dot_density=d,
            )[0]
            - exact
        )
        for d in (0, 2, 4)
    ]
    assert errors[0] > errors[1] > errors[2]


def test_a_fully_buried_atom_has_no_area():
    """A small atom inside a large one contributes nothing."""
    areas = atom_surface_areas(
        np.array([[0.0, 0, 0], [0.0, 0, 0]]), np.array([5.0, 1.0])
    )
    assert areas[1] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Against an independent implementation
# --------------------------------------------------------------------------- #
def _reference_areas(xyz, radii, probe, n_dots=4096):
    """Shrake-Rupley with a golden-spiral sphere and uniform weights.

    Deliberately unlike the implementation under test: a different point set and
    a different weighting, so a mistake shared with the tessellation cannot hide.
    """
    i = np.arange(n_dots) + 0.5
    polar = np.arccos(1.0 - 2.0 * i / n_dots)
    azimuth = np.pi * (1.0 + 5.0**0.5) * i
    dots = np.stack(
        [
            np.cos(azimuth) * np.sin(polar),
            np.sin(azimuth) * np.sin(polar),
            np.cos(polar),
        ],
        axis=1,
    )
    inflated = radii + probe
    out = np.zeros(len(xyz))
    for k in range(len(xyz)):
        surface = xyz[k] + inflated[k] * dots
        distance = np.linalg.norm(surface[:, None, :] - xyz[None, :, :], axis=2)
        distance[:, k] = np.inf
        exposed = ~np.any(distance < inflated[None, :], axis=1)
        out[k] = 4.0 * np.pi * inflated[k] ** 2 * exposed.mean()
    return out


@pytest.fixture(scope="module")
def cluster():
    rng = np.random.default_rng(7)
    return rng.normal(scale=4.0, size=(60, 3)), rng.uniform(1.4, 1.9, size=60)


@pytest.mark.parametrize("dot_solvent, probe", [(False, 0.0), (True, 1.4)])
def test_a_cluster_matches_an_independent_shrake_rupley(cluster, dot_solvent, probe):
    xyz, radii = cluster
    reference = _reference_areas(xyz, radii, probe).sum()
    ours = atom_surface_areas(
        xyz, radii, dot_solvent=dot_solvent, dot_density=4
    ).sum()
    assert ours == pytest.approx(reference, rel=0.01)


def test_the_selection_does_not_change_who_occludes(cluster):
    """The area of an atom *in* a structure is not its area in isolation.

    Computing only the selected atoms but letting only them occlude would be a
    different -- and far less useful -- quantity.
    """
    xyz, radii = cluster
    mask = np.zeros(len(xyz), dtype=bool)
    mask[:5] = True

    partial = atom_surface_areas(xyz, radii, mask=mask)
    whole = atom_surface_areas(xyz, radii)
    assert np.allclose(partial[mask], whole[mask])
    assert np.allclose(partial[~mask], 0.0)


def test_an_isolated_subset_would_have_a_larger_area(cluster):
    """The control for the test above: context genuinely occludes."""
    xyz, radii = cluster
    mask = np.zeros(len(xyz), dtype=bool)
    mask[:5] = True
    in_context = atom_surface_areas(xyz, radii, mask=mask)[mask].sum()
    alone = atom_surface_areas(xyz[mask], radii[mask]).sum()
    assert alone > in_context


# --------------------------------------------------------------------------- #
# Through the command
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.cmd.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    yield cmd, view, messages, errors
    cmd.do("set dot_solvent, off")   # a global setting, restored for other tests


def test_get_area_reports_a_plausible_protein_area(session):
    """T4 lysozyme is ~164 residues; its accessible surface is some 8000 A^2."""
    cmd, _, messages, errors = session
    cmd.do("set dot_solvent, on")
    cmd.do("get_area")
    assert errors == []
    area = float(messages[-1].split()[1])
    assert 6000.0 < area < 10000.0


def test_the_van_der_waals_area_exceeds_the_accessible_one(session):
    """Inflating by the probe buries far more than it adds, for a packed protein."""
    cmd, _, messages, _ = session
    cmd.do("set dot_solvent, off")
    cmd.do("get_area")
    vdw = float(messages[-1].split()[1])
    cmd.do("set dot_solvent, on")
    cmd.do("get_area")
    accessible = float(messages[-1].split()[1])
    assert vdw > accessible


def test_get_area_says_which_surface_it_measured(session):
    """The two differ by a factor of two, so the answer is useless unlabelled."""
    cmd, _, messages, _ = session
    cmd.do("set dot_solvent, off")
    cmd.do("get_area")
    assert "van der Waals" in messages[-1]
    cmd.do("set dot_solvent, on")
    cmd.do("get_area")
    assert "solvent-accessible" in messages[-1]


def test_get_area_honours_a_selection(session):
    cmd, _, messages, errors = session
    cmd.do("get_area resn NAG")
    assert errors == []
    assert "14 atoms" in messages[-1]


def test_load_b_writes_per_atom_areas(session):
    """Which is what makes `spectrum b` colour by accessibility."""
    cmd, view, messages, errors = session
    cmd.do("get_area all, 1, 1")
    assert errors == []
    total = float(messages[-1].split()[1])
    assert float(np.asarray(view._atoms["bfactor"]).sum()) == pytest.approx(
        total, rel=1e-6
    )


def test_the_core_is_buried_and_the_surface_is_not(session):
    """A protein's interior atoms should carry almost no area, its surface plenty.

    Not an exact zero: whether any single atom is *entirely* enclosed depends on
    the structure and the sampling. What must hold is the distribution -- a core
    that is buried and a surface that is exposed.
    """
    cmd, view, _, _ = session
    cmd.do("set dot_solvent, on")
    cmd.do("get_area all, 1, 1")
    areas = np.asarray(view._atoms["bfactor"], dtype=float)

    assert areas.min() >= 0.0
    # A packed protein buries most of itself: over half its atoms should have
    # less than a tenth the area of the most exposed one.
    assert float(np.mean(areas < 0.1 * areas.max())) > 0.5


def test_an_empty_selection_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("get_area resn ZZZ")
    assert errors and "matched no atoms" in errors[-1]


# --------------------------------------------------------------------------- #
# The other queries
# --------------------------------------------------------------------------- #
def test_get_chains_lists_the_chains(session):
    cmd, _, messages, errors = session
    cmd.do("get_chains")
    assert errors == []
    assert messages[-1] == "[E, S]"


def test_get_chains_honours_a_selection(session):
    cmd, _, messages, _ = session
    cmd.do("get_chains resn NAG")
    assert messages[-1] == "[S]"


def test_get_extent_is_the_raw_bounding_box(session):
    """Not the symmetric box `zoom` frames with; this one is the actual extent."""
    cmd, view, messages, errors = session
    cmd.do("get_extent")
    assert errors == []
    xyz = np.asarray(view._atoms["xyz"], dtype=float)
    numbers = [
        float(t) for t in messages[-1].replace("[", " ").replace("]", " ")
        .replace(",", " ").split()
    ]
    assert numbers[:3] == pytest.approx(xyz.min(axis=0), abs=5e-4)
    assert numbers[3:] == pytest.approx(xyz.max(axis=0), abs=5e-4)


def test_get_extent_honours_a_selection(session):
    cmd, view, messages, _ = session
    cmd.do("get_extent resn NAG")
    numbers = [
        float(t) for t in messages[-1].replace("[", " ").replace("]", " ")
        .replace(",", " ").split()
    ]
    names = np.char.strip(view._atoms["res_name"].astype(str))
    ligand = np.asarray(view._atoms["xyz"], dtype=float)[names == "NAG"]
    assert numbers[:3] == pytest.approx(ligand.min(axis=0), abs=5e-4)


def test_get_title_names_the_source(session):
    cmd, _, messages, errors = session
    cmd.do("get_title")
    assert errors == []
    assert "148l" in messages[-1]


# --------------------------------------------------------------------------- #
# `ray` traces what is shown
# --------------------------------------------------------------------------- #
def test_ray_traces_only_what_is_shown(session):
    """`ray` used to trace every atom in every state.

    It called ``get_atom_sphere_data``, whose contract is explicitly "all atoms
    regardless of representation", so ``hide everything`` and
    ``show spheres, resn NAG`` produced the identical picture of the molecule.
    """
    cmd, view, _, _ = session

    cmd.do("hide everything")
    assert view.get_atom_sphere_data(visible_only=True)[0].shape[0] == 0

    cmd.do("show spheres, resn NAG")
    assert view.get_atom_sphere_data(visible_only=True)[0].shape[0] == 14

    cmd.do("hide everything")
    cmd.do("show spheres, all")
    assert view.get_atom_sphere_data(visible_only=True)[0].shape[0] == len(view._atoms)


def test_the_mask_beats_the_flag(session):
    """`show spheres, <sel>` needs the flag *and* the mask, and they say
    different things.

    The flag answers "is this representation drawn at all"; the mask answers
    "for which atoms". A filter that reads only the flag therefore takes the
    whole molecule instead of the selection.

    This test used to assert the flag stayed *False* here, which was true and
    was the bug: the selection branch set the mask and never raised the flag, so
    the scene builder -- which requires both -- drew nothing. Nothing errored,
    and it took a windowed GL render to see it. The flag is now set, so what is
    worth pinning is that the two carry different information rather than that
    one of them is broken.
    """
    cmd, view, _, _ = session
    cmd.do("hide everything")
    cmd.do("show spheres, resn NAG")
    assert bool(view._show_atoms)              # something is drawn...
    shown = int(view.sphere_visible_mask().sum())
    assert shown == 14                         # ...and the mask says which
    assert shown < len(view._atoms), "the flag alone would take every atom"


def test_the_default_view_traces_its_hetero_balls(session):
    """A freshly loaded structure draws its ligands as balls over a cartoon."""
    cmd, view, _, _ = session
    shown = int(view.sphere_visible_mask().sum())
    assert 0 < shown < len(view._atoms)


def test_ray_traces_a_cartoon_rather_than_refusing(session, tmp_path):
    """This used to assert the refusal, and the refusal was the bug.

    Saying "cannot yet trace the cartoon" was better than emitting a picture that
    quietly omitted the molecule -- but the tracer had had triangle meshes for a
    while by then, and the cartoon *is* a triangle mesh. The message survived
    because `ray` decided from the sphere count, which a cartoon leaves at zero.
    Ported rather than deleted, so the case stays covered.
    """
    cmd, _, messages, errors = session
    cmd.do("hide everything")
    cmd.do("show cartoon")
    errors.clear()
    messages.clear()
    out = tmp_path / "x.png"
    cmd.do(f"ray {out}, 80, 60")
    assert errors == [], errors
    assert out.exists(), "the cartoon was not traced"
    assert "mesh" in " ".join(messages)


def test_ray_with_nothing_shown_says_that_instead(session, tmp_path):
    """The two are different problems and only one is the tracer's limitation."""
    cmd, _, messages, errors = session
    cmd.do("hide everything")
    errors.clear()
    messages.clear()
    cmd.do(f"ray {tmp_path / 'x.png'}, 80, 60")
    assert messages and "nothing is shown" in messages[-1]
