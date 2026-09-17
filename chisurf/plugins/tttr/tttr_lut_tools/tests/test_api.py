"""Unit tests for the tttr_lut_tools pure api (no Qt)."""

import pathlib

import numpy as np
import pytest

from chisurf.plugins.tttr.tttr_lut_tools import api

HERE = pathlib.Path(__file__).resolve().parents[5]  # repo root
SPC = HERE / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def test_build_and_apply_lut_from_synthetic_counts():
    # A DNL-distorted flat histogram: alternating wide/narrow bins.
    rng = np.random.default_rng(0)
    counts = (100 + 40 * np.sin(np.linspace(0, 20, 4096))).astype(float)
    counts += rng.normal(0, 3, counts.size)
    tbl = api.compute.compute_lut_from_counts(counts, 100, 4000, 4096, 0)
    ntac = np.asarray(tbl["NTAC_fract"])
    assert ntac.size == 4096
    assert np.all(np.diff(ntac) >= 0)  # cumulative -> monotone non-decreasing


def test_infer_n_bins_snaps_to_nice():
    micro = np.array([0, 1, 4090, 4095])
    assert api.lut.infer_n_bins(micro, None) == 4096
    assert api.lut.infer_n_bins(micro, 8192) == 8192  # explicit wins


def test_settings_round_trip(tmp_path):
    luts = {0: [0.0, 1.0, 2.5, 4.0], 8: [0.0, 2.0, 4.0]}
    d = api.settings.build_settings_dict(
        luts, {0: 3}, reading_routine="SPC-130", used_channels=[0, 8], created="t0"
    )
    p = tmp_path / "s.tttr.json"
    api.settings.save_settings(str(p), d)
    back = api.settings.load_settings(str(p))
    assert back["reading_routine"] == "SPC-130"
    assert sorted(back["channel_luts"]) == [0, 8]
    assert back["channel_shifts"][0] == 3
    np.testing.assert_allclose(back["channel_luts"][0], [0.0, 1.0, 2.5, 4.0])


def test_load_lut_file_roundtrip(tmp_path):
    ntac = np.linspace(0, 4096, 4096)
    for ext in (".npy", ".txt", ".csv", ".npz"):
        p = tmp_path / f"lut{ext}"
        api.io.save_lut(str(p), {"NTAC_fract": ntac})
        back = api.io.load_lut_file(str(p))
        assert back.size == ntac.size
        np.testing.assert_allclose(back, ntac, rtol=1e-5)


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_compute_lut_from_files_and_apply():
    tbl = api.compute.compute_lut_from_files([str(SPC)])
    assert np.asarray(tbl["NTAC_fract"]).size > 0
    luts = {0: np.asarray(tbl["NTAC_fract"])}
    counts, axis = api.settings.corrected_histogram(str(SPC), 0, luts, {}, "SPC-130")
    assert counts.size > 0 and counts.sum() > 0
