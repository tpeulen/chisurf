"""A region drawn in one imaging tool must mean the same in the next.

The regions subsystem earns its keep at the seams: paint a cell in CLSM Draw,
save it, and confine a per-pixel FLIM fit to it — or hand it to colocalization,
or measure it. Each tool is tested on its own; these tests pin the *hand-off*,
which is where a coordinate convention or a file-format assumption silently
diverges and nothing fails until a user's numbers are quietly wrong.
"""
from __future__ import annotations

import numpy as np
import pytest


def _clsm_view_model_with_a_painted_region():
    """A CLSM view model holding an image and a painted selection."""
    from chisurf.plugins.microscopy.clsm.gui.view_model import ClsmViewModel

    vm = ClsmViewModel()
    image = np.zeros((24, 24), dtype=np.float64)
    image[6:12, 8:16] = 30.0
    vm.current_image = image
    vm.selection_mask = np.zeros_like(image)
    vm.selection_mask[6:12, 8:16] = 1.0
    return vm


def test_a_region_saved_in_clsm_confines_a_pixel_mle_fit(tmp_path):
    """The workflow guide 24 documents: paint, save, restrict the fit."""
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    clsm = _clsm_view_model_with_a_painted_region()
    clsm.add_roi("cell")
    path = tmp_path / "cell.json"
    # Saving is the shared region editor's job now, so the seam is the
    # collection itself rather than a per-tool save method.
    clsm.regions.save(str(path))
    assert path.exists()

    mle = PixelMleViewModel()
    mle.roi_path = str(path)
    assert mle.roi is not None, mle.status_text

    # The same pixels, on the other side of the file.
    np.testing.assert_array_equal(
        mle.roi.to_mask((24, 24)),
        clsm.regions.roi("cell").to_mask((24, 24)),
    )
    assert mle.roi.to_mask((24, 24)).sum() == 6 * 8


def test_a_segmentation_arrives_as_objects_not_as_one_blob(tmp_path):
    """A label image is one region per object wherever it is loaded.

    Reading it as a plain mask would merge every cell into one — silently,
    because a label image is also a valid mask — and the per-object numbers
    downstream would then describe the whole field.
    """
    tifffile = pytest.importorskip("tifffile")
    from chisurf.core.roi import RegionCollection, regionprops
    from chisurf.plugins.microscopy.clsm.gui.view_model import ClsmViewModel

    labels = np.zeros((24, 24), dtype=np.uint16)
    labels[2:6, 2:6] = 1
    labels[10:16, 10:16] = 2
    labels[18:22, 4:8] = 3
    path = tmp_path / "cells.tif"
    tifffile.imwrite(str(path), labels)

    vm = ClsmViewModel()
    vm.current_image = np.ones((24, 24)) * 5.0
    vm.regions.extend(RegionCollection.load(str(path)))
    assert len(vm.regions) == 3

    # Each arrives with its own size, and measures the same as it does in the
    # label image it came from.
    measured = {p.label: p.area for p in regionprops(labels)}
    assert sorted(measured.values()) == [16, 16, 36]
    for entry in vm.regions:
        assert entry.roi.to_mask((24, 24)).sum() in measured.values()


def test_a_region_measured_in_one_tool_gates_another():
    """Measurement and selection are the same object seen from two sides.

    A molecule found by the segmentation in one tool becomes a gate in the
    next, without anyone converting anything.
    """
    from chisurf.core.roi import regionprops
    from chisurf.core.fluorescence.imaging.colocalization import pixelwise

    labels = np.zeros((16, 16), dtype=np.int32)
    labels[4:8, 4:8] = 1
    image_a = np.zeros((16, 16))
    image_a[4:8, 4:8] = 50.0
    image_b = image_a * 0.8

    molecule = regionprops(labels, image_a)[0]
    assert molecule.area == 16
    assert molecule.intensity_mean == 50.0

    result = pixelwise.colocalization_metrics(
        image_a, image_b, threshold_a=1.0, threshold_b=1.0, roi=molecule.to_roi()
    )
    # Only the measured molecule's pixels entered the coefficients.
    assert result.metrics["n_pixels"] == 16


def test_a_phasor_cursor_and_an_image_region_are_the_same_type():
    """The axis-free claim, checked across two unrelated plugins."""
    from chisurf.core.roi import ROI
    from chisurf.plugins.microscopy.img_pixel_phasor import analysis

    cursor = analysis.cursor_roi((0.5, 0.3), "elliptic", radii=(0.2, 0.1), angle=0.3)
    assert isinstance(cursor, ROI)

    # It gates scattered phasor coordinates ...
    g = np.array([0.5, 0.95])
    s = np.array([0.3, 0.95])
    np.testing.assert_array_equal(analysis.mask_from_cursor(g, s, cursor), [True, False])

    # ... and rasterises onto a frame, because nothing about it is phasor-specific.
    assert cursor.to_mask((10, 10), extent=(0.0, 1.0, 0.0, 1.0)).any()
