"""The split changed the architecture and must not have changed the answer.

Molecule-wise MLE used to segment inside its own fit. It now fits regions the
spot finder found, which is a better design and a worse one if the numbers move.
So the pre-split behaviour was captured before the change — the intensity image,
the labels its watershed produced, the per-region VV/VH histograms its gathering
built, and the parameters its estimator returned — and these compare against it.

The baseline cannot be regenerated: the code that produced it is deleted by the
change these tests exist to check, and the simulator it ran on is unseeded. It
is data, in ``test/data``, and it is the only evidence that the two halves still
add up to what the whole used to do.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, column_values
from chisurf.core.fio.image import imread

DATA = Path(__file__).resolve().parent / "data"

pytestmark = pytest.mark.skipif(
    not (DATA / "labels.tif").exists(), reason="no pre-split baseline captured"
)


def _read_csv(name: str):
    from chisurf.core.datastore import read_csv_table

    return read_csv_table(DATA / name)


def _column(table, name) -> np.ndarray:
    return np.asarray(column_values(table, column_names(table).index(name)), dtype=float)


def test_the_spot_finder_reproduces_the_old_segmentation_exactly():
    """The claim the whole split rests on.

    The standard workflow is not a new recipe that happens to look similar: it
    is the pipeline molecule-wise MLE always ran, moved. Label for label, pixel
    for pixel — anything less and every fitted number downstream is being
    compared against a different set of molecules.
    """
    from chisurf.plugins.microscopy.spot_finder.core.spots import detect_labels
    from chisurf.plugins.microscopy.spot_finder.core.workflow import (
        STANDARD,
        request_from_workflow,
    )

    intensity = np.asarray(imread(DATA / "intensity.tif"), dtype=float)
    expected = np.asarray(imread(DATA / "labels.tif"))

    request = request_from_workflow(STANDARD)
    found, _extra = detect_labels(intensity, request.settings)

    assert found.max() == expected.max(), (
        f"the standard workflow found {found.max()} regions where the tool it "
        f"replaces found {expected.max()}"
    )
    np.testing.assert_array_equal(found, expected)


def test_the_estimator_returns_the_same_parameters_for_the_same_histograms():
    """The other half: the fit itself is untouched, and this is what says so."""
    from chisurf.core.fluorescence.mle import Fit2x, Fit2xModel, Fit2xSettings

    irf = _column(_read_csv("irf.csv"), "irf")
    histograms = _read_csv("vv_vh.csv")
    acquisition = _read_csv("acquisition.csv")
    expected = _read_csv("molecules.csv")

    fit2x = Fit2x(
        Fit2xSettings(
            dt=float(_column(acquisition, "dt")[0]),
            period=float(_column(acquisition, "period")[0]),
            irf=np.ascontiguousarray(irf, dtype=np.float64),
            g_factor=1.0,
            p2s_twoIstar=True,
        ),
        model=Fit2xModel.FIT23,
    )
    x0 = np.array([2.0, 0.0, 0.38, 1.0])
    fixed = np.array([0, 0, 1, 1], dtype=np.int16)

    taus = _column(expected, "tau")
    for index, name in enumerate(column_names(histograms)):
        vv_vh = np.asarray(column_values(histograms, index), dtype=float)
        result = fit2x.fit(vv_vh, initial_values=x0, fixed=fixed)
        # The tolerance guards the *estimator*, not the build: a changed model,
        # a changed objective or a changed start vector moves tau by percent.
        # ``rel=1e-9`` instead pinned the last bits of a nonlinear optimiser's
        # output, so recompiling tttrlib (different FMA contraction, different
        # step at the same optimum) reddened this test at |Δ| ~ 2e-8 while the
        # estimator was untouched — a guard that fails for a reason it was not
        # written to detect stops being read.
        assert result.x[0] == pytest.approx(taus[index], rel=1e-6), (
            f"{name}: the estimator now returns {result.x[0]} where it "
            f"returned {taus[index]} before the split"
        )


def test_the_fit_no_longer_segments():
    """A guard on the thing that was actually wrong.

    ``fit_regions`` calling a segmentation was the defect: the preview a user
    tuned was not what got fitted. A settings object with nowhere to get regions
    from must therefore *fail*, and say which tool finds them — an empty result
    would be the same silence in a new place.
    """
    import dataclasses

    from chisurf.plugins.microscopy.region_mle.core import RegionMleSettings, resolve_labels

    settings = RegionMleSettings()
    names = {f.name for f in dataclasses.fields(RegionMleSettings)}
    assert not [n for n in names if n.startswith("seg_")], (
        f"segmentation settings survive the split: {sorted(names)}"
    )

    with pytest.raises(ValueError, match="spot finder"):
        resolve_labels(settings, (32, 32))


def test_what_is_previewed_is_what_is_fitted():
    """Both paths resolve the regions the same way, because it is one call."""
    from chisurf.plugins.microscopy.region_mle.core import RegionMleSettings, resolve_labels
    from chisurf.plugins.microscopy.region_mle.core.region_mle import region_preview

    intensity = np.asarray(imread(DATA / "intensity.tif"), dtype=float)
    labels = np.asarray(imread(DATA / "labels.tif"))

    settings = RegionMleSettings(regions=labels)
    preview = region_preview(intensity, settings)

    np.testing.assert_array_equal(preview.label_image, resolve_labels(settings, intensity.shape))
    np.testing.assert_array_equal(preview.label_image, labels)


def test_regions_can_come_from_the_container_the_spot_finder_writes(tmp_path: Path):
    """The hand-off, end to end: detect, write, read back, fit those."""
    from chisurf.core.fio.image import imwrite
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.microscopy.region_mle.core import RegionMleSettings, resolve_labels
    from chisurf.plugins.microscopy.spot_finder.api.models import SpotFinderRequest
    from chisurf.plugins.microscopy.spot_finder.api.spot_finder import detect_request

    intensity = np.asarray(imread(DATA / "intensity.tif"))
    source = tmp_path / "field.tif"
    imwrite(source, intensity.astype(np.uint32), axes="YX")
    with Measurement.create(source, artifact_kind="image_data"):
        pass

    detect_request(SpotFinderRequest(files=[str(source)], name="spots"))

    settings = RegionMleSettings(regions=str(source), region_set="spots")
    labels = resolve_labels(settings, intensity.shape)

    np.testing.assert_array_equal(labels, np.asarray(imread(DATA / "labels.tif")))
