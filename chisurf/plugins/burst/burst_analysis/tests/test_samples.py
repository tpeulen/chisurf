"""What each file of a burst session is, and what the buffer and reference-dye files give.

Real code paths on a simulated session whose answer is known (:mod:`..demo`): a buffer of known
rate, a fast-rotating reference dye with a known G factor diffusing through a 3-D Gaussian focus
of known w0 / z0, on a one-colour and a two-colour PIE setup.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from chisurf.plugins.burst.burst_analysis import demo, samples


@pytest.fixture(autouse=True)
def _packaged_dye_database(monkeypatch):
    """The dye database as ChiSurf ships it: a test before this one may have configured an empty
    MMFDB, which the database module would read instead (and cache)."""
    from chisurf.core.fluorescence import dyes

    monkeypatch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    yield
    monkeypatch.undo()
    try:
        dyes.reference_dyes(refresh=True)
    except Exception:  # noqa: BLE001 - the next user reloads it
        dyes._CACHE = None


@pytest.fixture(scope="session")
def session_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("samples_demo")
    paths = demo.make_demo(folder)
    paths["red"] = demo.make_red_reference(folder)
    return paths


# -- names ---------------------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, kind",
    [
        ("dsDNA_1nM.ptu", "measurement"),
        ("buffer.ptu", "buffer"),
        ("bg_10min.ptu", "buffer"),
        ("H2O.ptu", "irf"),
        ("water_scatter.ptu", "irf"),
        ("IRF_485.ptu", "irf"),
        ("Rh110_ref.ptu", "reference"),
        ("rhodamine110.ptu", "reference"),
        ("R6G.ptu", "reference"),
        ("dye_green.ptu", "reference"),
        ("A647_1nM.ptu", "reference"),
    ],
)
def test_the_type_is_guessed_from_the_name(name, kind):
    assert samples.guess_sample_type(name) == kind


@pytest.mark.parametrize(
    "name, dye",
    [
        ("Rh110_ref", "Rhodamine 110"),
        ("rhodamine110", "Rhodamine 110"),
        ("R110", "Rhodamine 110"),
        ("Rhodamine_110_1nM", "Rhodamine 110"),
        ("A647", "Alexa Fluor 647"),
        ("Alexa647", "Alexa Fluor 647"),
        ("Atto655", "ATTO 655 (COOH)"),
        ("cy5_ref", "Cy5"),
        ("dsDNA_sample", None),
    ],
)
def test_a_dye_is_found_in_a_name_through_the_dye_database(name, dye):
    assert samples.dye_in_name(name) == dye


def test_the_colour_row_breaks_a_tie():
    # a green row cannot hold Alexa 647: the colour's default instead
    assert samples.infer_dye(["x/A647.ptu"], "G") == ("Rhodamine 110", "default")
    assert samples.infer_dye(["x/A647.ptu"], "R") == ("Alexa Fluor 647", "file name")
    # Rhodamine 6G (yellow) is the green row's dye of a green / red setup
    assert samples.infer_dye(["x/R6G.ptu"], "G", ["G", "R"]) == ("Rhodamine 6G", "file name")
    assert samples.guess_colour("Alexa647_ref.ptu") == "R"
    assert samples.guess_colour("irf_640.ptu") == "R"


def test_a_header_tag_names_the_dye(tmp_path):
    import tttrlib

    path = tmp_path / "calibration_01.ptu"
    stream = tttrlib.TTTR(
        np.arange(100, dtype=np.uint64), np.zeros(100, dtype=np.uint16),
        np.zeros(100, dtype=np.int8), np.zeros(100, dtype=np.int8),
    )
    stream.header.set_macro_time_resolution(demo.MACRO_S)
    stream.header.set_micro_time_resolution(demo.MICRO_S)
    stream.header.set_string_tag("File_Comment", "Rhodamine 110, 1 nM in water")
    assert stream.write(str(path), "PTU")
    assert "Rhodamine 110" in samples.header_text(path)
    assert samples.infer_dye([path], "G") == ("Rhodamine 110", "header")


# -- the dye database ----------------------------------------------------------------------------- #
def test_d_is_the_database_entry_corrected_to_the_temperature():
    from chisurf.core.fluorescence.diffusion import diffusion_at_temperature
    from chisurf.core.fluorescence.dyes import get_dye

    d25 = get_dye("Rhodamine 110")["d25_um2_s"]
    at_25, source = samples.dye_diffusion({"dye": "Rhodamine 110", "temperature_c": 25.0})
    at_20, _ = samples.dye_diffusion({"dye": "Rhodamine 110", "temperature_c": 20.0})
    assert at_25 == pytest.approx(diffusion_at_temperature(d25, 25.0))
    assert at_20 == pytest.approx(diffusion_at_temperature(d25, 20.0))
    assert at_20 < at_25  # colder: slower
    assert "Rhodamine 110" in source and "25 °C" in source
    assert samples.dye_diffusion({"dye": samples.CUSTOM_DYE, "custom_D": 430.0}) == (430.0, "custom D")


# -- rows from the setup ----------------------------------------------------------------------------- #
def test_the_rows_follow_the_setup_and_a_vanished_colour_is_unassigned():
    assert samples.row_keys({}) == ["measurement", "buffer"]
    assert samples.row_keys(demo.SETUP) == ["measurement", "buffer", "irf:G", "reference:G"]
    assert samples.row_keys(demo.SETUP_PIE) == [
        "measurement", "buffer", "irf:G", "irf:R", "reference:G", "reference:R",
    ]
    assert [g["detectors"] for g in samples.colour_groups(demo.SETUP_PIE)] == [["G|G"], ["R|G", "R|R"]]
    assert samples.resolve_row("reference:R", demo.SETUP_PIE) == "reference:R"
    assert samples.resolve_row("reference:R", demo.SETUP) == "unassigned"
    assert samples.resolve_row("irf", {}) == "unassigned"
    assert samples.resolve_row("reference", demo.SETUP_PIE, "Alexa647_ref.ptu") == "reference:R"


# -- the calibrations, against the simulation's answer ------------------------------------------- #
def test_the_buffer_rate_g_factor_and_volume_of_the_simulated_session(session_files):
    truth = demo.TRUTH
    rows = {
        str(session_files["buffer"]): "buffer",
        str(session_files["reference"]): "reference:G",
        str(session_files["measurement"]): "measurement",
    }
    custom = {"G": {"dye": samples.CUSTOM_DYE, "custom_D": truth["D_um2_s"], "how": "user"}}
    result = samples.calibrate(rows, demo.SETUP, dyes=custom)
    assert result["errors"] == []
    rate = result["buffer"]["rates"]["G|G"]["B_kHz"]
    assert rate == pytest.approx(sum(truth["background_khz"]), rel=0.03)
    entry = result["colours"]["G"]
    assert entry["g_factor"]["G|G"]["g"] == pytest.approx(truth["g_factor"], rel=0.015)
    volume = entry["volume"]
    assert volume["w0_um"] == pytest.approx(truth["w0_um"], rel=0.08)
    assert volume["z0_um"] == pytest.approx(truth["z0_um"], rel=0.25)
    assert volume["veff_fl"] == pytest.approx(demo.veff_fl(), rel=0.2)
    assert entry["D_source"] == "custom D"

    # another D (another dye, or temperature) scales the volume as D^(3/2) at the same fit
    faster = samples.calibrate(
        rows, demo.SETUP, dyes={"G": {**custom["G"], "custom_D": 2 * truth["D_um2_s"]}}
    )["colours"]["G"]["volume"]
    assert faster["veff_fl"] / volume["veff_fl"] == pytest.approx(2 ** 1.5, rel=1e-6)
    by_db = samples.calibrate(rows, demo.SETUP)["colours"]["G"]
    assert by_db["dye"]["dye"] == "Rhodamine 110" and by_db["dye"]["how"] == "file name"
    warmer = samples.calibrate(
        rows, demo.SETUP, dyes={"G": {"dye": "Rhodamine 110", "temperature_c": 30.0, "how": "user"}}
    )["colours"]["G"]
    assert warmer["D_um2_s"] > by_db["D_um2_s"]
    assert warmer["volume"]["veff_fl"] > by_db["volume"]["veff_fl"]


def test_each_colour_of_a_pie_setup_gets_its_own_g_and_volume(session_files):
    red = demo.TRUTH_RED
    rows = {
        str(session_files["reference"]): "reference:G",
        str(session_files["red"]): "reference:R",
    }
    dyes = {
        "G": {"dye": samples.CUSTOM_DYE, "custom_D": demo.TRUTH["D_um2_s"], "how": "user"},
        "R": {"dye": samples.CUSTOM_DYE, "custom_D": red["D_um2_s"], "how": "user"},
    }
    result = samples.calibrate(rows, copy.deepcopy(demo.SETUP_PIE), dyes=dyes)
    green, redc = result["colours"]["G"], result["colours"]["R"]
    assert set(green["g_factor"]) == {"G|G"}
    # R|G and R|R share their channels: one G, from the window that saw the red dye (R|R)
    assert set(redc["g_factor"]) == {"R|G", "R|R"}
    assert redc["g_factor"]["R|G"]["g"] == redc["g_factor"]["R|R"]["g"]
    assert redc["g_factor"]["R|R"]["from"] == "R|R"
    assert redc["g_factor"]["R|R"]["g"] == pytest.approx(red["g_factor"], rel=0.02)
    assert redc["volume"]["detector"] == "R|R"
    truth_v = math.pi ** 1.5 * red["w0_um"] ** 2 * red["z0_um"]
    assert redc["volume"]["veff_fl"] == pytest.approx(truth_v, rel=0.2)
    assert redc["volume"]["w0_um"] == pytest.approx(red["w0_um"], rel=0.08)
