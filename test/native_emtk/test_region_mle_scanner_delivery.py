"""Real Region MLE file delivery uses the declared scanner without a CLSM shim."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(scope="module")
def measured_demo(tmp_path_factory):
    """Generate the actual Spot sample/IRF and detect its regions in private settings."""
    from chisurf.plugins.microscopy.region_mle.gui.view_model import RegionMleViewModel

    root = tmp_path_factory.mktemp("region_scanner")
    patch = pytest.MonkeyPatch()
    patch.setenv("CHISURF_SETTINGS_DIR", str(root))
    model = RegionMleViewModel()
    model.load_demo()
    yield model
    patch.undo()


def explicit_reference(model):
    """Fit canonical photons with the producer's explicit documented scanner layout."""
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import clsm_from_scan
    from chisurf.plugins.microscopy.region_mle.core.region_mle import (
        build_irf_vv_vh,
        compute_g_factor,
        fit_regions,
    )

    sample = Path(model.files[0])
    tttr = tttrlib.TTTR(str(sample))
    layout = json.loads(sample.with_suffix(".json").read_text())["scan_layout"]
    clsm = clsm_from_scan(tttr, layout["n_pixel_per_line"], model.settings.detector_chs)
    settings = dataclasses.replace(model.settings)
    irf = tttrlib.TTTR(model.irf_files[0])
    settings.irf, settings.background = build_irf_vv_vh(
        irf, detector_chs=settings.detector_chs,
        micro_time_range=settings.micro_time_range,
        micro_time_binning=settings.micro_time_binning,
    )
    if settings.auto_g_factor:
        settings.g_factor = compute_g_factor(
            irf, settings.detector_chs, settings.micro_time_range, settings.micro_time_binning
        )
    return tttr, clsm, fit_regions(tttr, settings, clsm=clsm, keep_curves=True)


def test_real_file_preview_uses_the_detected_field(measured_demo):
    """Preview reconstructs the real 48×48 field whose four labels the detector saved."""
    from chisurf.plugins.microscopy.region_mle.gui.view_model import RegionMleViewModel

    model = RegionMleViewModel()
    model.files = list(measured_demo.files)
    model.settings = dataclasses.replace(measured_demo.settings)
    model.preview_regions()
    _, _, reference = explicit_reference(measured_demo)
    assert len(model.results) == 1 and model.results[0].n_molecules == 4
    np.testing.assert_array_equal(model.results[0].intensity_image, reference.intensity_image)
    np.testing.assert_array_equal(model.results[0].label_image, reference.label_image)
    assert model.status_text.startswith("Preview: 4 region(s)")


def test_real_filepath_fit23_matches_explicit_scanner(measured_demo):
    """The file workflow preserves canonical region photons and complete Fit23 outputs."""
    from chisurf.core.datastore import rows_from_table
    from chisurf.plugins.microscopy.region_mle.core.region_mle import fit_regions_from_files

    _, _, reference = explicit_reference(measured_demo)
    actual = fit_regions_from_files(
        measured_demo.files[0], measured_demo.irf_files[0],
        dataclasses.replace(measured_demo.settings), keep_curves=True,
    )
    assert actual.n_molecules == reference.n_molecules == 4
    np.testing.assert_array_equal(actual.intensity_image, reference.intensity_image)
    np.testing.assert_array_equal(actual.label_image, reference.label_image)
    np.testing.assert_array_equal(actual.centroids, reference.centroids)
    assert rows_from_table(actual.dataframe) == rows_from_table(reference.dataframe)
    for data, expected, curve, expected_curve in zip(
        actual.vv_vh_vectors, reference.vv_vh_vectors,
        actual.model_curves, reference.model_curves, strict=True,
    ):
        np.testing.assert_array_equal(data, expected)
        np.testing.assert_array_equal(curve, expected_curve)
        np.testing.assert_array_equal(data - curve, expected - expected_curve)


def test_scanner_region_indices_are_real_unique_photons(measured_demo):
    """Every fitted region owns actual photon events, with no padded or shared indices."""
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import clsm_from_file
    from chisurf.plugins.microscopy.region_mle.core.region_mle import region_photon_indices

    tttr, reference_clsm, reference = explicit_reference(measured_demo)
    delivered = clsm_from_file(tttr, measured_demo.files[0], measured_demo.settings.detector_chs)
    actual = region_photon_indices(delivered, reference.label_image)
    expected = region_photon_indices(reference_clsm, reference.label_image)
    assert len(actual) == len(expected) == 4
    events = np.asarray(tttr.event_types)
    for indices, reference_indices in zip(actual, expected, strict=True):
        np.testing.assert_array_equal(indices, reference_indices)
        assert indices.size >= measured_demo.settings.min_photons
        assert np.all((indices >= 0) & (indices < len(tttr)))
        assert np.all(events[indices] == 0)
    joined = np.concatenate(actual)
    assert np.unique(joined).size == joined.size
    assert delivered.__class__ is tttrlib.CLSMImage


@pytest.mark.parametrize("pixels", [None, 0, -1, True, 2.5, "48"])
def test_invalid_recognized_scanner_grid_is_rejected(measured_demo, tmp_path, pixels):
    """A declared producer cannot silently substitute guessed dimensions for invalid metadata."""
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import clsm_from_file

    path = tmp_path / "scan.ptu"
    path.with_suffix(".json").write_text(json.dumps({
        "scan_layout": {"kind": "chisurf-simulated-raster", "n_pixel_per_line": pixels}
    }))
    with pytest.raises(ValueError, match="positive integer"):
        clsm_from_file(tttrlib.TTTR(measured_demo.files[0]), path)


@pytest.mark.parametrize("sidecar", [None, "broken{", "[]", '{"scan_layout": []}',
                                      '{"scan_layout": {"kind": "vendor", "n_pixel_per_line": 48}}'])
def test_ordinary_hardware_keeps_canonical_auto_detection(tmp_path, sidecar):
    """A real Leica measurement is unchanged by absent, unreadable or unrelated sidecars."""
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import clsm_from_file

    source = Path(__file__).resolve().parents[2] / "test/data/clsm/Leica_SP5.ptu"
    assert source.is_file(), source
    tttr = tttrlib.TTTR(str(source))
    metadata_path = tmp_path / "hardware.ptu"
    if sidecar is not None:
        metadata_path.with_suffix(".json").write_text(sidecar)
    actual = clsm_from_file(tttr, metadata_path, channels=[0])
    expected = tttrlib.CLSMImage(tttr, channels=[0], fill=True)
    assert actual.shape == expected.shape
    np.testing.assert_array_equal(actual.intensity, expected.intensity)
    assert np.asarray(actual.intensity).sum() > 0


def test_real_view_model_fit_exports_all_four_regions(measured_demo, tmp_path):
    """The shipping worker adapter delivers four fits and exports their exact numeric columns."""
    from chisurf.core.datastore import column_names, numeric_column, read_csv_table, row_count
    from chisurf.plugins.microscopy.region_mle.gui.view_model import RegionMleViewModel

    model = RegionMleViewModel()
    model.files = list(measured_demo.files)
    model.irf_files = list(measured_demo.irf_files)
    model.settings = dataclasses.replace(measured_demo.settings)
    model.run()
    assert len(model.results) == 1 and model.results[0].n_molecules == 4
    output = tmp_path / "regions.tsv"
    assert model.export_results(str(output)) == str(output)
    table = read_csv_table(output)
    assert row_count(table) == 4
    expected = model.results[0].dataframe
    assert column_names(table) == column_names(expected)
    for name in column_names(expected):
        np.testing.assert_allclose(
            numeric_column(table, name), numeric_column(expected, name), rtol=1e-12, atol=1e-12
        )
    source = Path(model.files[0])
    analysis = source.parent / (source.stem + "_analysis") / "molecule_data.tsv"
    assert row_count(read_csv_table(analysis)) == 4
    assert row_count(read_csv_table(source.parent / "joint_output.tsv")) == 4
