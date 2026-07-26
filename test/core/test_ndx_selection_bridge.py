"""ndXplorer's gates and ChiSurf's regions are the same thing, checked against it.

The claim these tests defend is not "the bridge runs" but "the bridge agrees":
for every selection kind, the region collection excludes exactly the points
ndXplorer's own ``get_mask`` excludes. Asserting that against the real
implementation is the only way to know the two conventions were reconciled
rather than merely described — ``get_mask`` returns ``True`` for *excluded*
where a region answers *inside*, and getting that backwards is silent.
"""

from __future__ import annotations

import numpy as np
import pytest

ndx = pytest.importorskip("ndxplorer.core.data_source")

from chisurf.core.roi.selections import (  # noqa: E402
    collection_from_selections,
    ellipse_from_covariance,
    excluded_mask,
    roi_from_selection,
)


@pytest.fixture
def cloud():
    """A three-parameter cloud: two correlated axes and one unrelated."""
    rng = np.random.default_rng(5)
    n = 2000
    x = rng.normal(10.0, 2.0, n)
    y = 0.8 * x + rng.normal(0.0, 1.0, n)
    z = rng.uniform(0.0, 1.0, n)
    return np.vstack([x, y, z])


def _agrees(selections, data, axes=(0, 1)):
    """Whether the bridge and ndXplorer exclude the same points."""
    theirs = np.zeros(data.shape, dtype=bool)
    for selection in selections:
        theirs |= selection.get_mask(data)
    ours = excluded_mask(collection_from_selections(selections, axes=axes), data, axes)
    return theirs, ours


def test_a_1d_interval_excludes_the_same_points(cloud):
    selection = ndx.RectangularDataSelection(parameter_idx=0, lower=8.0, upper=12.0)
    theirs, ours = _agrees([selection], cloud)
    np.testing.assert_array_equal(ours, theirs)
    assert theirs.any() and not theirs.all(), "the gate must actually cut"


def test_an_inverted_interval_excludes_the_same_points(cloud):
    selection = ndx.RectangularDataSelection(
        parameter_idx=1, lower=6.0, upper=10.0, invert=True
    )
    theirs, ours = _agrees([selection], cloud)
    np.testing.assert_array_equal(ours, theirs)


def test_a_disabled_selection_excludes_nothing_on_either_side(cloud):
    selection = ndx.RectangularDataSelection(
        parameter_idx=0, lower=8.0, upper=12.0, enabled=False
    )
    theirs, ours = _agrees([selection], cloud)
    np.testing.assert_array_equal(ours, theirs)
    assert not ours.any()


def test_a_mahalanobis_ellipse_excludes_the_same_points(cloud):
    """The covariance's eigenvectors are the ellipse's axes."""
    xy = cloud[:2]
    mu = xy.mean(axis=1)
    cov = np.cov(xy)
    selection = ndx.Gaussian2DSelection(
        parameter_idx1=0, parameter_idx2=1, mu=mu, cov=cov, sigma=1.5
    )
    theirs, ours = _agrees([selection], cloud)

    # Boundary points can fall either side of a floating-point tie; agreement to
    # a few points in two thousand is the ellipse, not a convention error.
    disagree = int((ours != theirs).sum() / cloud.shape[0])
    assert disagree <= 3, f"{disagree} points disagree"
    assert theirs.any() and not theirs.all()


def test_an_inverted_ellipse_excludes_the_same_points(cloud):
    xy = cloud[:2]
    selection = ndx.Gaussian2DSelection(
        parameter_idx1=0, parameter_idx2=1, mu=xy.mean(axis=1), cov=np.cov(xy),
        sigma=1.0, invert=True,
    )
    theirs, ours = _agrees([selection], cloud)
    assert int((ours != theirs).sum() / cloud.shape[0]) <= 3


def test_several_selections_combine_the_way_ndxplorer_combines_them(cloud):
    """A point survives only if no enabled selection excludes it — an AND."""
    selections = [
        ndx.RectangularDataSelection(parameter_idx=0, lower=8.0, upper=12.0),
        ndx.RectangularDataSelection(parameter_idx=1, lower=5.0, upper=11.0),
    ]
    theirs, ours = _agrees(selections, cloud)
    np.testing.assert_array_equal(ours, theirs)
    assert theirs.any() and not theirs.all()


def test_a_selection_on_a_parameter_off_this_plane_is_skipped_not_guessed(cloud):
    """A wrong gate is worse than a missing one."""
    selection = ndx.RectangularDataSelection(parameter_idx=2, lower=0.2, upper=0.8)
    collection = collection_from_selections([selection], axes=(0, 1))
    assert len(collection) == 0
    assert not excluded_mask(collection, cloud, (0, 1)).any()


def test_a_painted_histogram_mask_becomes_a_region():
    """ndXplorer's brush paints bins; the region gates the values they stand for."""
    mask = np.zeros((16, 16), dtype=bool)
    mask[4:8, 2:6] = True
    edges1 = np.linspace(0.0, 16.0, 17)
    edges2 = np.linspace(0.0, 8.0, 17)
    selection = ndx.MaskDataSelection(
        idx1=0, idx2=1, mask=mask, edges1=edges1, edges2=edges2
    )
    roi = roi_from_selection(selection, axes=(0, 1))
    assert roi is not None
    # A point in a painted bin is inside; one in an unpainted bin is not.
    inside = roi.contains(np.array([[3.0, 2.5], [12.0, 6.5]]))
    assert inside[0] != inside[1]

    # And it is skipped, not misapplied, when the plane is a different pair.
    assert roi_from_selection(selection, axes=(1, 2)) is None


def test_a_painted_mask_excludes_the_same_points_as_ndxplorer(cloud):
    """The one selection kind whose bins have to be mapped back to values."""
    x, y = cloud[0], cloud[1]
    edges1 = np.linspace(x.min(), x.max(), 25)
    edges2 = np.linspace(y.min(), y.max(), 25)
    mask = np.zeros((24, 24), dtype=bool)
    mask[6:16, 6:16] = True
    selection = ndx.MaskDataSelection(
        idx1=0, idx2=1, mask=mask, edges1=edges1, edges2=edges2
    )
    theirs, ours = _agrees([selection], cloud)
    disagree = int((ours != theirs).sum() / cloud.shape[0])
    assert disagree <= 3, f"{disagree} points disagree"
    assert theirs.any() and not theirs.all()


# --- what the round trip buys ------------------------------------------------
def test_every_shape_survives_a_save_and_reload(tmp_path, cloud):
    """ndXplorer's own loader rebuilds only rectangles; a collection keeps all.

    That is the concrete gain from sharing the type: a saved ellipse or painted
    population currently disappears on reload, silently, and the analysis
    afterwards is over a different set of points than the one on screen.
    """
    from chisurf.core.roi import EllipseROI, RegionCollection

    xy = cloud[:2]
    selections = [
        ndx.RectangularDataSelection(parameter_idx=0, lower=8.0, upper=12.0, name="x band"),
        ndx.Gaussian2DSelection(
            parameter_idx1=0, parameter_idx2=1, mu=xy.mean(axis=1), cov=np.cov(xy),
            sigma=1.0, name="cluster", invert=True,
        ),
    ]
    collection = collection_from_selections(selections, axes=(0, 1))
    path = str(tmp_path / "gates.json")
    collection.save(path)

    back = RegionCollection.load(path)
    assert back.names == ["x band", "cluster"]
    assert isinstance(back.roi("cluster"), EllipseROI)
    assert back["cluster"].invert is True
    assert back.combine == "and"

    np.testing.assert_array_equal(
        excluded_mask(back, cloud, (0, 1)), excluded_mask(collection, cloud, (0, 1))
    )


def test_the_ellipse_axes_come_from_the_covariance():
    """A circle stays a circle; an elongated covariance gives an elongated ellipse."""
    circle = ellipse_from_covariance([0.0, 0.0], [[4.0, 0.0], [0.0, 4.0]], sigma=1.0)
    assert circle.rx == pytest.approx(2.0)
    assert circle.ry == pytest.approx(2.0)

    elongated = ellipse_from_covariance([1.0, 2.0], [[9.0, 0.0], [0.0, 1.0]], sigma=2.0)
    assert (elongated.cx, elongated.cy) == (1.0, 2.0)
    assert elongated.rx == pytest.approx(6.0)     # 2 * sqrt(9)
    assert elongated.ry == pytest.approx(2.0)     # 2 * sqrt(1)
    assert elongated.angle == pytest.approx(0.0, abs=1e-9)
