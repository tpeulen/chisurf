"""BVA discovers declared burst tables without decoding binary cache sidecars."""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.fluorescence.burst import read_bur_file
from chisurf.core.fio.fluorescence.burst_companion import write_companion
from chisurf.plugins.burst.burst_bva.core.computation import compute_bva, read_burst_analysis

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)
REAL_BUR = DATA / "burst_analysis_handoff/bi4_bur/m000.bur"


def _real_folder(root):
    """Copy real measured input into a writable, isolated legacy folder."""
    folder = root / "analysis"
    (folder / "bi4_bur").mkdir(parents=True)
    shutil.copy2(REAL_BUR, folder / "bi4_bur/m000.bur")
    shutil.copy2(DATA / "m000.spc", root / "m000.spc")
    return folder


def _assert_same_table(left, right):
    """Compare every logical column, including text, zero and NaN values."""
    assert row_count(left) == row_count(right)
    assert column_names(left) == column_names(right)
    for name in column_names(left):
        np.testing.assert_array_equal(np.asarray(left[name]), np.asarray(right[name]))


def _cache_table(bur):
    """Persist the real physical table in a valid binary PTO sidecar."""
    from chisurf.core.fio.fluorescence.burst_tree import OPERATION
    from chisurf.core.fio.pto import Measurement

    path = bur.with_suffix(".pto")
    with Measurement.create_empty(path) as cache:
        cache.put_table(
            "cached/m000.bur",
            read_bur_file(bur),
            artifact_kind="burst_table",
            operation_type=OPERATION,
            row_grain="burst",
        )
    with Measurement.open(path) as cache:
        assert cache.path == path
    return path


def test_actual_bur_and_valid_binary_cache_preserve_all_rows_and_physics(tmp_path):
    """A valid persisted BUR cache must never be read as a UTF-8 table."""
    folder = _real_folder(tmp_path)
    clean, clean_streams = read_burst_analysis(folder, "SPC-130")
    assert row_count(clean) == 152
    bur = folder / "bi4_bur/m000.bur"
    cache = _cache_table(bur)
    assert cache.exists() and cache.stat().st_size > 0
    binary_before = cache.read_bytes()
    mixed, streams = read_burst_analysis(folder, "SPC-130")
    assert cache.read_bytes() == binary_before
    _assert_same_table(mixed, clean)
    for field in ("macro_times", "micro_times", "routing_channels"):
        np.testing.assert_array_equal(
            getattr(streams["m000.spc"], field), getattr(clean_streams["m000.spc"], field)
        )
    options = dict(
        donor_channels=[0],
        acceptor_channels=[1],
        donor_micro_time_ranges=[(0, 32768)],
        acceptor_micro_time_ranges=[(0, 32768)],
        number_of_photons_per_slice=10,
    )
    _assert_same_table(
        compute_bva(mixed, streams, **options), compute_bva(clean, clean_streams, **options)
    )


def _write_grid(path, rows):
    """Write the legacy zero interleave independently of its reader."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["First File\tFirst Photon\tLast Photon\tObservation", "0\t0\t0\t0"]
    for row in rows:
        lines.extend(["\t".join(map(str, row)), "0\t0\t0\t0"])
    path.write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize("custom_ending", ["s0_bg4", "custom.4"])
def test_companions_case_custom_endings_stems_and_sentinels_keep_position(tmp_path, custom_ending):
    """Canonical ending4 tables align by position without filtering observations."""
    folder = tmp_path / "analysis"
    _write_grid(folder / "bi4_bur/a.BUR", [[0, 0, 0, 0.0], [0, 10, 12, np.nan]])
    _write_grid(folder / "bi4_bur/z.bur", [[0, 20, 22, 7.0]])
    write_companion(folder, "Bg4", "a", ["Background marker"], [[101], [102]])
    path = write_companion(folder, "Bg4", "z", ["Background marker"], [[103]])
    path.rename(path.with_suffix(".BG4"))
    write_companion(folder, custom_ending, "a", ["Custom marker"], [[201], [np.nan]])
    path = write_companion(folder, custom_ending, "z", ["Custom marker"], [[203]])
    path.rename(path.with_name("z." + custom_ending.upper()))
    for directory in ("bi4_bur", "Bg4", custom_ending):
        base = folder / directory
        for filename in (
            "cache.pto",
            "readme.txt",
            "unrelated.csv",
            "metadata.json",
            "settings.yaml",
            "other.other4",
        ):
            (base / filename).write_bytes(b"\x9e\xff binary sidecar")
        (base / "nested").mkdir()
    table, streams = read_burst_analysis(folder, "SPC-130", pattern="*4*")
    assert streams == {}
    assert row_count(table) == 3
    np.testing.assert_array_equal(numeric_column(table, "First Photon"), [0, 10, 20])
    np.testing.assert_array_equal(numeric_column(table, "Observation"), [0, np.nan, 7])
    np.testing.assert_array_equal(numeric_column(table, "Background marker"), [101, 102, 103])
    np.testing.assert_array_equal(numeric_column(table, "Custom marker"), [201, 0, 203])


def test_actual_root_container_and_named_run_are_still_supported(tmp_path):
    """Explicit PTO input keeps shared container dispatch and real photons."""
    from chisurf.core.fio.fluorescence.burst_tree import OPERATION
    from chisurf.core.fio.pto import Measurement

    folder = _real_folder(tmp_path)
    expected, streams = read_burst_analysis(folder, "SPC-130")
    raw_table = read_bur_file(folder / "bi4_bur/m000.bur")
    with Measurement.create(tmp_path / "m000.spc", out_dir=tmp_path) as measurement:
        measurement.put_table(
            "measured/m000.bur",
            raw_table,
            artifact_kind="burst_table",
            operation_type=OPERATION,
            row_grain="burst",
        )
        container = measurement.path
    for path in (container, Path(str(container) + "/measured")):
        result, actual_streams = read_burst_analysis(path, "SPC-130")
        assert row_count(result) == 152
        for name in ("First Photon", "Last Photon", "Duration (ms)"):
            np.testing.assert_array_equal(
                numeric_column(result, name), numeric_column(expected, name)
            )
        for field in ("macro_times", "micro_times", "routing_channels"):
            np.testing.assert_array_equal(
                getattr(actual_streams["m000.spc"], field), getattr(streams["m000.spc"], field)
            )


def test_fresh_bva_core_read_needs_no_gui_libraries(tmp_path):
    """Real legacy folder decoding remains available in a Qt-free process."""
    folder = _real_folder(tmp_path)
    _cache_table(folder / "bi4_bur/m000.bur")
    code = (
        "import sys; from chisurf.plugins.burst.burst_bva.core.computation import read_burst_analysis; "
        "table,streams=read_burst_analysis(sys.argv[1],'SPC-130'); assert table.n_rows()==152; "
        "assert not any(name.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'} for name in sys.modules); "
        # emtk.i18n is the translation seam core code reaches through tr() (plugin manifests);
        # it is text lookup, not a GUI. Everything else of emtk -- painter, layout, widgets -- is.
        "assert not [n for n in sys.modules if n.split('.')[0] == 'emtk' and n.split('.')[1:2] != ['i18n'] and n != 'emtk']"
    )
    subprocess.run([sys.executable, "-c", code, str(folder)], check=True, capture_output=True)
