"""Detector names ``emission|excitation``; the historic green / red / yellow read as aliases."""

from chisurf.core.fluorescence import detector_names as dn


def test_the_default_names_cover_three_colour_fret_in_wavelength_order():
    assert dn.DEFAULT_NAMES == (
        "B|B", "G|B", "Y|B", "R|B", "G|G", "Y|G", "R|G", "Y|Y", "R|Y", "R|R",
    )
    assert dn.TWO_COLOUR == ("G|G", "R|G", "R|R")


def test_historic_names_are_aliases():
    assert [dn.canonical(n) for n in ("green", "Red", "YELLOW", "blue")] == ["G|G", "R|G", "R|R", "B|B"]
    assert dn.canonical("g|r") == "G|R" and dn.canonical("my APD") == "my APD"
    assert dn.find(["green", "red"], "R|G") == "red"
    assert dn.find(["G|G", "R|G"], "red") == "R|G"
    assert dn.canonical_detectors({"green": 1, "G|G": 2, "red": 3}) == {"G|G": 1, "R|G": 3}
    assert (dn.emission("R|G"), dn.excitation("R|G")) == ("R", "G")
    assert dn.emission("red") == "R" and dn.emission("my APD") is None


def test_columns_translate_both_ways_for_the_legacy_export():
    pairs = {
        "Number of Photons (G|G)": "Number of Photons (green)",
        "G|G Count Rate (KHz)": "Green Count Rate (KHz)",
        "R|G Count Rate (KHz)": "Red Count Rate (KHz)",
        "Tau (R|R)": "Tau (yellow)",
        "S prompt R|G (kHz) | 0-2048": "S prompt red (kHz) | 0-2048",
        "Duration (ms)": "Duration (ms)",
    }
    for new, old in pairs.items():
        assert dn.legacy_column(new) == old
        assert dn.column(old) == new


def test_labels_and_file_names():
    assert dn.label("G|G") == "G|G" and dn.label("green") == "Green"
    assert dn.slug("R|G") == "R-G"
