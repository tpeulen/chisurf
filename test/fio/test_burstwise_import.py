"""Legacy burstwise folder -> PTO.MFDB container import, against real data.

The fixture is a real 2014 T4L burstwise tree (87 measurement stems, pulled
from the deposition server): ``bi4_bur`` bursts, ``bg4``/``br4`` MLE
companions, ``BIDs`` photon indices, an ``Info`` folder, and an ``.mti``
mapping each stem to its original TTTR path and duration.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.burstwise_import import (
    BurstwiseImportError,
    convert_folder,
    dictionary_columns,
    parse_info,
    parse_mti,
    read_legacy_table,
    rename_columns,
    scan_folder,
)

SAMPLE = (
    pathlib.Path.home()
    / ".hermes"
    / "cache"
    / "scratch"
    / "burstwise_samples"
    / "burstwise_All 0.1066#60"
)
pytestmark = pytest.mark.skipif(
    not SAMPLE.is_dir(), reason="pulled burstwise sample not present"
)


# -- the legacy layout is read correctly ----------------------------------------


def test_scan_finds_tables_info_and_mti():
    inv = scan_folder(SAMPLE)
    assert len(inv["tables"]) == 87
    stem = "Split_44_132_75murea_sm-0000"
    roles = inv["tables"][stem]
    assert "bursts" in roles and roles["bursts"].name.endswith(".bur")
    assert roles["mle_green"].name.endswith(".bg4")
    assert roles["mle_red"].name.endswith(".br4")
    assert inv["info"] is not None and inv["info"].name.endswith(".txt")
    assert inv["mti"] is not None


def test_folder_name_parameters_are_parsed():
    inv = scan_folder(SAMPLE)
    # folder name "burstwise_All 0.1066#60"
    assert inv["parameters"]["min_photons"] == 60
    assert inv["parameters"]["threshold"] == pytest.approx(0.1066)


def test_burst_table_deinterleaves_and_keeps_columns():
    inv = scan_folder(SAMPLE)
    table = read_legacy_table(inv["tables"]["Split_44_132_75murea_sm-0000"]["bursts"])
    assert "First Photon" in table and "Number of Photons" in table
    # the legacy interleave doubles physical rows; data rows survive
    n = len(table["First Photon"])
    assert n > 0
    assert (table["Number of Photons"] > 0).sum() >= int(0.5 * n)


def test_info_file_parses_analysis_parameters():
    inv = scan_folder(SAMPLE)
    params = parse_info(inv["info"])
    assert params.get("reading routine") == "PQ TH3R"
    assert "Laser repetition time" in params
    assert "G-factor channels.[0]" in params


def test_mti_maps_stems_to_original_paths():
    inv = scan_folder(SAMPLE)
    mti = parse_mti(inv["mti"])
    assert len(mti) >= 87
    key = [k for k in mti if "75murea_sm-0000" in k]
    assert key, "stem 0000 must be in the mti map"
    assert mti[key[0]] > 1000.0  # durations are ~42000 s-scale? no: seconds
    assert mti[key[0]] > 0.0


# -- renaming to dictionary terms -----------------------------------------------


def test_dictionary_loads_the_45_terms():
    d = dictionary_columns()
    assert len(d) >= 40
    assert "First Photon" in d
    assert d["Tau (green)"]["term"] == "_mmfdb_burst_column.tau_green"


def test_nonconformant_old_names_are_renamed():
    cols = [
        "Mean Macrotime (green) (ms)",  # old spelling
        "Tau  (red)",  # double space; base term not in dict -> flagged, not coined
        "First Photon",  # already conformant
        "Something New",  # unknown
    ]
    renames, unmapped = rename_columns(cols)
    assert renames == {
        "Mean Macrotime (green) (ms)": "Mean Macro Time (green) (ms)",
    }
    assert unmapped == ["Tau  (red)", "Something New"]


# -- conversion -----------------------------------------------------------------


def test_convert_folder_reports_without_source(tmp_path):
    """No resolver: stems are reported, nothing is written, no guessing."""
    report = convert_folder(SAMPLE, out_dir=tmp_path, dry_run=False)
    assert report.stems and not report.containers
    assert all("<no source TTTR>" in v for v in report.unmapped_columns.values())


def test_convert_one_measurement_writes_container(tmp_path):
    """With a resolver returning a real TTTR, one container is written.

    The container is created beside the instrument file (the
    ``write_burst_artifact`` convention), so the fixture TTTR is copied into
    tmp_path first.
    """
    pytest.importorskip("tttrlib")
    raw_src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "data"
        / "clsm"
        / "Leica_SP5.ptu"
    )
    if not raw_src.exists():
        pytest.skip("no instrument fixture")
    raw = tmp_path / "Split_44_132_75murea_sm-0000.ptu"
    raw.write_bytes(raw_src.read_bytes())

    def resolver(stem, mti):
        # only the first stem, to keep the test fast
        return raw if stem == "Split_44_132_75murea_sm-0000" else None

    report = convert_folder(SAMPLE, source_resolver=resolver, out_dir=tmp_path)
    assert len(report.containers) == 1
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(report.containers[0]) as m:
        uid = m._resolve("bursts")
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "burst"
        store = m.get_store("bursts")
        names = [str(n) for n in store.column_names()]
        assert "Mean Macro Time (green) (ms)" in names  # renamed, not the old spelling
        assert "Mean Macrotime (green) (ms)" not in names
        # provenance settings carried
        prov = m.provenance(uid)
        assert prov["operation"] == "burst_selection"
        settings = prov["settings"]
        assert settings["folder_parameters"]["min_photons"] == 60
        assert settings["info"]["reading routine"] == "PQ TH3R"
        assert "Mean Macrotime (green) (ms)" in settings["column_renames"]
