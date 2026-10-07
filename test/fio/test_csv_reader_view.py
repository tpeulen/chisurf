"""CSV reader settings drive real files, error columns and fixed-width parsing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.experiments.tcspc.reader import TCSPCReader


def _reader(**kwargs):
    """Keep file/provenance work isolated and scientific calibration explicit."""
    return TCSPCReader(record_provenance=False, skiprows=0, use_header=False, dt=0.25, **kwargs)


def test_fixed_width_reader_imports_the_declared_fields_instead_of_an_empty_group(tmp_path):
    """The visible FWF format choice must decode fixed-width channels and counts."""
    path = tmp_path / "decay.fwf"
    path.write_text("".join(f"{x:5d}{y:7d}\n" for x, y in [(0, 10), (1, 20), (2, 30)]))
    reader = _reader(reading_routine="fwf")
    reader.colspecs = "5, 7"
    group = reader.read(filename=str(path))
    assert len(group) == 1
    np.testing.assert_array_equal(group[0].x, [0, 0.25, 0.5])
    np.testing.assert_array_equal(group[0].y, [10, 20, 30])


def test_fixed_width_explicit_ranges_skip_padding_and_preserve_headers(tmp_path):
    """The legacy colspecs text accepts start/stop slices, not just column widths."""
    path = tmp_path / "ranges.fwf"
    lines = ["preamble\n", f"{'':3s}{'time':5s}{'':2s}{'counts':7s}\n"]
    lines += [f"{'':3s}{x:5d}{'':2s}{y:7d}\n" for x, y in [(0, 10), (1, 20)]]
    path.write_text("".join(lines))
    reader = TCSPCReader(record_provenance=False, reading_routine="fwf", skiprows=1,
                         use_header=True, dt=0.25)
    reader.colspecs = "(3, 8), (10, 17)"
    group = reader.read(filename=str(path))
    assert len(group) == 1
    np.testing.assert_array_equal(group[0].x, [0, 0.25])
    np.testing.assert_array_equal(group[0].y, [10, 20])


def test_supplied_error_columns_are_not_discarded_or_imported_as_extra_decays(tmp_path):
    """X/Y error flags select standard deviations and apply the time-axis calibration."""
    path = tmp_path / "errors.csv"
    np.savetxt(path, [[0, 10, 2, 3], [1, 20, 4, 5], [2, 30, 6, 7]], delimiter=",")
    reader = _reader(reading_routine="csv")
    reader.col_x, reader.col_y, reader.col_ex, reader.col_ey = 0, 1, 2, 3
    reader.error_x_on = reader.error_y_on = True
    group = reader.read(filename=str(path))
    assert len(group) == 1
    np.testing.assert_array_equal(group[0].x, [0, .25, .5])
    np.testing.assert_array_equal(group[0].y, [10, 20, 30])
    np.testing.assert_array_equal(group[0].ex, [.5, 1, 1.5])
    np.testing.assert_array_equal(group[0].ey, [3, 5, 7])


def test_explicit_delimiter_is_forwarded_to_the_owning_csv_reader(tmp_path):
    """A declared delimiter is honored even when it is absent from auto-detection candidates."""
    path = tmp_path / "colon.txt"
    path.write_text("0:10\n1:20\n2:30\n")
    reader = _reader(reading_routine="csv")
    reader.delimiter = ":"
    group = reader.read(filename=str(path))
    assert len(group) == 1
    np.testing.assert_array_equal(group[0].y, [10, 20, 30])


def test_disabled_error_columns_keep_default_counting_noise(tmp_path):
    """Declaring unused error columns never changes established counting statistics."""
    path = tmp_path / "counts.csv"
    np.savetxt(path, [[0, 10, 99, 99], [1, 20, 99, 99], [2, 30, 99, 99]], delimiter=",")
    reader = _reader(reading_routine="csv")
    reader.col_ex, reader.col_ey = 2, 3
    reader.error_x_on = reader.error_y_on = False
    curve = reader.read(filename=str(path))[0]
    np.testing.assert_array_equal(curve.ex, np.zeros(3))
    from chisurf.core.fluorescence.tcspc import counting_noise

    np.testing.assert_array_equal(curve.ey, counting_noise(np.array([10, 20, 30])))


def test_channel_axis_can_be_generated_when_x_values_are_disabled(tmp_path):
    """The existing x-values toggle controls whether the selected X column is used."""
    path = tmp_path / "counts.csv"
    np.savetxt(path, [[99, 10], [88, 20], [77, 30]], delimiter=",")
    reader = _reader(reading_routine="csv")
    reader.x_on = False
    curve = reader.read(filename=str(path))[0]
    np.testing.assert_array_equal(curve.x, [0, .25, .5])
    np.testing.assert_array_equal(curve.y, [10, 20, 30])


def test_csv_column_and_calibration_settings_roundtrip_without_a_gui():
    """All newly effective reading choices belong to trusted scientific reader state."""
    from chisurf.core.project.session import _reader_state, _restore_reader

    reader = _reader(reading_routine="fwf")
    values = {"filename": "measurement.fwf", "colspecs": "5, 7", "delimiter": ":",
              "col_ex": 2, "col_ey": 3, "error_x_on": True, "error_y_on": True,
              "x_on": False, "link_l1_l2": False}
    for name, value in values.items():
        setattr(reader, name, value)
    restored = _restore_reader(_reader_state(reader), None, {})
    assert {name: getattr(restored, name, None) for name in values} == values


def test_declared_csv_view_has_no_custom_leakage_widget_and_preserves_controls():
    """The complete native declaration contains every meaningful legacy control."""
    reader = _reader()
    sections = reader.view_spec().flat_sections()
    attrs = {getattr(section, "attr", "") for section in sections}
    custom = {getattr(section, "key", "") for section in sections}
    assert "tcspc_l1l2" not in custom
    assert {"filename", "reading_routine", "skiprows", "use_header", "colspecs", "delimiter",
            "col_x", "col_y", "col_ex", "col_ey", "error_x_on", "error_y_on", "x_on",
            "dt", "dt_scaled", "rebin_x_key", "rebin_y_key", "rep_rate", "is_vv_vh",
            "polarization", "g_factor", "l1", "l2", "link_l1_l2", "vh_shift"} <= attrs
    buttons = [button for section in sections for button in getattr(section, "buttons", ())]
    assert any(button.get("action") == "open_gfactor" for button in buttons)


def test_structure_reader_source_filename_roundtrips_in_its_trusted_field_map():
    """The sibling native reader's declared source belongs to its scientific configuration."""
    from chisurf.core.experiments.modelling import StructureReader
    from chisurf.core.project.session import _reader_state, _restore_reader

    reader = StructureReader(filename='test/data/atomic_coordinates/pdb_files/148l.pdb',
                             record_provenance=False)
    restored = _restore_reader(_reader_state(reader), None, {})
    assert restored.filename == reader.filename


def test_fitting_package_exposes_its_fit_owner_in_a_cold_process():
    """A cached or not-yet-imported submodule must not depend on another test's imports."""
    import subprocess
    import sys

    code = "import chisurf.core.fitting as package; assert package.fit.FitGroup.__name__ == 'FitGroup'"
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rebinning_does_not_drop_the_only_decay_when_output_has_three_bins(tmp_path):
    """Post-rebin channel counts are not a reason to slice away a dataset row."""
    path = tmp_path / 'six.csv'
    np.savetxt(path, np.column_stack([np.arange(6), np.arange(1, 7) * 10]), delimiter=',')
    reader = _reader(reading_routine='csv', rebin=(1, 2))
    group = reader.read(filename=str(path))
    assert len(group) == 1
    np.testing.assert_array_equal(group[0].y, [30, 70, 110])
