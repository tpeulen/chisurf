"""Putty cartoons — a tube whose thickness carries a number.

One of the few representations that shows a *quantity* rather than a shape, and
for this group the quantity is rarely a b-factor: it is an accessibility from
``get_area``, a fitted lifetime, a per-residue efficiency, written into the
b-factor field with ``alter`` and then drawn.

The scale factors are transcribed from ``ExtrudeComputeScaleFactors``
(``layer1/Extrude.cpp``). Two details are easy to get wrong and both change the
picture: the clamp is applied **after** the power, and the factors are smoothed
along the chain with a running window that leaves the ends alone.

Verification here is geometric rather than visual — the ray tracer cannot draw a
cartoon, and measuring the tube's actual radius against the property is a stronger
check than looking at a picture anyway.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.analysis.putty import (
    PUTTY_TRANSFORMS,
    putty_scale_factors,
    smooth_scale_factors,
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


# --------------------------------------------------------------------------- #
# The transform, against PyMOL's formula
# --------------------------------------------------------------------------- #
def test_the_default_transform_matches_pymols_formula():
    """``(range + (b - mean)/stdev) / range``, raised to the power, then clamped."""
    values = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    got = putty_scale_factors(values)

    mean, stdev, spread, power = values.mean(), values.std(), 2.0, 1.5
    expected = np.clip(
        np.power(np.maximum((spread + (values - mean) / stdev) / spread, 0.0), power),
        0.6,
        4.0,
    )
    assert np.allclose(got, expected)


def test_the_clamp_comes_after_the_power():
    """Clamping first would change the curve's shape, not only its ends."""
    # One outlier among many equal values, so its z-score is high enough that the
    # powered scale genuinely exceeds the upper clamp -- with a gentler spread it
    # never reaches it and the test would prove nothing.
    values = np.array([0.0] * 11 + [100.0])
    unclamped = putty_scale_factors(values, scale_min=-1.0, scale_max=-1.0)
    clamped = putty_scale_factors(values, scale_min=0.6, scale_max=4.0)
    assert unclamped.max() > 4.0
    assert clamped.max() == pytest.approx(4.0)
    # The interior points are untouched by the clamp, so they must still agree.
    interior = (unclamped > 0.6) & (unclamped < 4.0)
    assert np.allclose(clamped[interior], unclamped[interior])


def test_a_bigger_value_never_gives_a_thinner_tube():
    values = np.linspace(5.0, 95.0, 40)
    scale = putty_scale_factors(values)
    assert np.all(np.diff(scale) >= -1e-12)


def test_a_constant_property_falls_back_to_a_flat_tube():
    """PyMOL's guard against dividing by a zero standard deviation."""
    assert np.allclose(putty_scale_factors(np.full(6, 7.0)), 0.5)


def test_a_zero_range_falls_back_too():
    assert np.allclose(putty_scale_factors(np.arange(6.0), scale_range=0.0), 0.5)


@pytest.mark.parametrize("name", sorted(PUTTY_TRANSFORMS))
def test_every_transform_produces_usable_factors(name):
    scale = putty_scale_factors(np.linspace(1.0, 50.0, 20), transform=name)
    assert scale.shape == (20,)
    assert np.all(np.isfinite(scale))
    assert np.all(scale >= 0.0)


def test_a_transform_can_be_given_by_its_pymol_code():
    by_name = putty_scale_factors(np.arange(1.0, 9.0), transform="normalized_linear")
    by_code = putty_scale_factors(np.arange(1.0, 9.0), transform=4)
    assert np.allclose(by_name, by_code)


def test_the_linear_variant_skips_the_power():
    values = np.linspace(1.0, 50.0, 12)
    linear = putty_scale_factors(values, transform="normalized_linear")
    nonlinear = putty_scale_factors(values, transform="normalized_nonlinear")
    assert not np.allclose(linear, nonlinear)
    # Below 1 the power pushes values up, above 1 it pushes them further up.
    assert np.allclose(
        np.clip(np.power(np.maximum(linear, 0.0), 1.5), 0.6, 4.0),
        np.clip(nonlinear, 0.6, 4.0),
    )


def test_an_unknown_transform_is_refused():
    with pytest.raises((KeyError, ValueError)):
        putty_scale_factors(np.arange(5.0), transform="nonsense")


def test_no_values_gives_no_factors():
    assert putty_scale_factors([]).shape == (0,)


# --------------------------------------------------------------------------- #
# Smoothing
# --------------------------------------------------------------------------- #
def test_smoothing_softens_a_spike():
    """A single outlying residue should bulge the tube, not bead it."""
    smoothed = smooth_scale_factors(np.array([1.0, 1.0, 9.0, 1.0, 1.0]), window=1)
    assert smoothed[2] < 9.0
    assert smoothed[1] > 1.0        # the bulge spreads to its neighbours


def test_smoothing_leaves_the_ends_alone():
    """PyMOL clamps the window at the ends, so it skips the terminal points."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    smoothed = smooth_scale_factors(values, window=1)
    assert smoothed[0] == values[0]
    assert smoothed[-1] == values[-1]


def test_smoothing_conserves_the_general_level():
    values = np.random.default_rng(3).uniform(0.6, 4.0, 50)
    smoothed = smooth_scale_factors(values, window=2)
    assert smoothed.mean() == pytest.approx(values.mean(), rel=0.1)


def test_a_short_chain_is_left_alone():
    values = np.array([1.0, 2.0])
    assert np.allclose(smooth_scale_factors(values), values)


# --------------------------------------------------------------------------- #
# The tube it produces
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import Viewer

    view = Viewer()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def refresh_objects(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    errors: list[str] = []
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(errors.append)
    cmd.do("hide everything")
    cmd.do("show cartoon")
    yield cmd, view, errors
    cmd.do("cartoon automatic")     # a global setting, restored for other tests


def _tube_radii(view) -> np.ndarray | None:
    """Measure the drawn tube's radius at each ring of the extrusion.

    Stronger than looking at a picture: the ring vertices of an extruded tube sit
    at exactly the radius the code chose, so this reads the geometry back.
    """
    scene = view.get_current_scene()
    mesh = None
    for obj in (scene.objects if scene else []):
        geometry = obj.geometry
        positions = getattr(geometry, "positions", None)
        if getattr(geometry, "kind", "") != "mesh" or positions is None:
            continue
        if mesh is None or len(positions) > len(mesh):
            mesh = np.asarray(positions)
    if mesh is None:
        return None

    total = len(mesh)
    for segments in (18, 14, 12, 20, 24, 16, 8, 6):
        if (total - 2) % segments:
            continue
        rings = mesh[: (total - 2)].reshape(-1, segments, 3)
        centres = rings.mean(axis=1, keepdims=True)
        return np.linalg.norm(rings - centres, axis=2).mean(axis=1)
    return None


def test_a_plain_tube_has_one_radius(session):
    cmd, view, errors = session
    cmd.do("cartoon tube")
    radii = _tube_radii(view)
    assert radii is not None
    assert np.ptp(radii) < 1e-6


def test_a_putty_tube_varies(session):
    cmd, view, errors = session
    cmd.do("alter all, b = resi")
    cmd.do("cartoon putty")
    assert errors == []
    radii = _tube_radii(view)
    assert radii is not None
    assert np.ptp(radii) > 1e-3


def test_the_radius_follows_the_property(session):
    """A monotone b-factor ramp must give a monotone tube."""
    cmd, view, _ = session
    cmd.do("alter all, b = resi")
    cmd.do("cartoon putty")
    radii = _tube_radii(view)
    assert np.all(np.diff(radii) > -1e-6)
    ramp = np.linspace(0.0, 1.0, len(radii))
    assert float(np.corrcoef(ramp, radii)[0, 1]) > 0.9


def test_the_thinnest_point_is_the_clamp(session):
    """Radius times scale_min, exactly -- which pins both settings at once."""
    cmd, view, _ = session
    cmd.do("alter all, b = resi")
    cmd.do("cartoon putty")
    radii = _tube_radii(view)
    scale = float(view._scale_factor)
    assert radii.min() == pytest.approx(0.4 * scale * 0.6, rel=1e-6)


def test_a_structure_without_b_factors_still_draws(session):
    """A uniform tube is the right answer, not an error."""
    cmd, view, errors = session
    cmd.do("alter all, b = 0")
    cmd.do("cartoon putty")
    assert errors == []
    assert _tube_radii(view) is not None


def test_putty_is_reported_as_a_cartoon_type(session):
    cmd, _, errors = session
    cmd.do("cartoon putty")
    assert errors == []
    cmd.do("cartoon nonsense")
    assert errors and "Unsupported cartoon type" in errors[-1]
