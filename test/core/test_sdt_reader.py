"""Real SDT decays retain their file calibration and all measured curves."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.experiments.tcspc.sdt_reader import SDTReader
from chisurf.core.fio.fluorescence.sdtfile import SdtFile

SDT = Path(__file__).resolve().parents[1] / "data/tcspc/BH_SDT/140507p.sdt"
DT_NS = 0.019537081674680934
REP_MHZ = 1000.0 / 600.0


def test_real_sdt_refreshes_calibration_instead_of_using_reader_defaults():
    """Measured channel spacing and repetition rate override unrelated defaults."""
    reader = SDTReader(dt=9.0, rep_rate=80.0, record_provenance=False)
    group = reader.read(filename=str(SDT))

    assert reader.dt == pytest.approx(DT_NS)
    assert reader.rep_rate == pytest.approx(REP_MHZ)
    assert len(group) == 3
    for curve in group:
        assert len(curve.x) == len(curve.y) == 1024
        assert curve.x[1] - curve.x[0] == pytest.approx(DT_NS)
        assert curve.meta_data["excitation_period_ns"] == pytest.approx(1000.0 / REP_MHZ)


def test_preview_selection_does_not_filter_or_reorder_imported_curves():
    """Choosing the third preview still imports all three measured histograms."""
    reader = SDTReader(curve_nbr=2, record_provenance=False)
    source = SdtFile(str(SDT))
    group = reader.read(filename=str(SDT))

    assert reader.curve_nbr == 2
    assert len(group) == 3
    for index, curve in enumerate(group):
        np.testing.assert_array_equal(curve.y, source.data[index][0])
        np.testing.assert_array_equal(curve.x, source.times[index] * 1e9)
        assert curve.data_reader is reader


def test_reload_replaces_stale_calibration_and_keeps_all_curves(tmp_path):
    """Reloading a copied real file cannot retain edited defaults or lose a curve."""
    copied = tmp_path / "reload.sdt"
    copied.write_bytes(SDT.read_bytes())
    reader = SDTReader(curve_nbr=1, record_provenance=False)
    original = reader.read(filename=str(SDT))
    reader.dt, reader.rep_rate = 7.0, 40.0
    reloaded = reader.read(filename=str(copied))

    assert reader.dt == pytest.approx(DT_NS)
    assert reader.rep_rate == pytest.approx(REP_MHZ)
    assert reader.curve_nbr == 1
    assert len(reloaded) == 3
    for before, after in zip(original, reloaded):
        np.testing.assert_array_equal(after.x, before.x)
        np.testing.assert_array_equal(after.y, before.y)


def test_each_imported_block_uses_its_own_time_axis_and_excitation_period(monkeypatch):
    """Different block calibrations stay paired with their measured histograms."""
    measured = SdtFile(str(SDT))
    source = SimpleNamespace(
        data=measured.data,
        times=[axis * (index + 1) for index, axis in enumerate(measured.times)],
        block_measure_info=lambda index: {"rep_t": np.array([500.0 + 100.0 * index])},
    )
    monkeypatch.setattr("chisurf.core.experiments.tcspc.sdt_reader.SdtFile", lambda _: source)
    reader = SDTReader(curve_nbr=2, record_provenance=False)
    group = reader.read(filename=str(SDT))

    assert reader.dt == pytest.approx(3 * DT_NS)
    assert reader.rep_rate == pytest.approx(1000.0 / 700.0)
    for index, curve in enumerate(group):
        np.testing.assert_array_equal(curve.x, source.times[index] * 1e9)
        assert curve.meta_data["excitation_period_ns"] == pytest.approx(500.0 + 100.0 * index)
    reader.curve_nbr = 0
    assert reader.dt == pytest.approx(DT_NS)
    assert reader.rep_rate == pytest.approx(2.0)
    assert len(group) == 3


def test_restored_headless_reader_can_reimport_all_curves_with_file_calibration():
    """A persisted preview choice retains scientific calibration without a widget."""
    from chisurf.core.experiments.core import Experiment
    from chisurf.core.project.session import capture_session, restore_session

    reader = SDTReader(experiment=Experiment(name="SDT"), curve_nbr=2, record_provenance=False)
    imported = reader.get_data(filename=str(SDT))
    restored = restore_session(capture_session([imported], []))
    restored_reader = restored.datasets[0][0].data_reader

    assert type(restored_reader) is SDTReader
    assert restored_reader.curve_nbr == 2
    assert restored_reader.dt == pytest.approx(DT_NS)
    assert restored_reader.rep_rate == pytest.approx(REP_MHZ)
    reimported = restored_reader.read(filename=str(SDT))
    assert len(reimported) == 3
    for before, after in zip(imported, reimported):
        np.testing.assert_array_equal(after.x, before.x)
        np.testing.assert_array_equal(after.y, before.y)


def test_loaded_preview_tracks_curve_choice_without_importing_anything():
    """The selected preview exposes the actual histogram and measured calibration."""
    source = SdtFile(str(SDT))
    reader = SDTReader(record_provenance=False)
    reader.load_file(str(SDT))
    assert reader.filename == str(SDT)
    assert reader.curve_options() == [0, 1, 2]
    assert "140507p" in reader.file_info
    reader.curve_nbr = 2
    np.testing.assert_array_equal(reader.ph_counts, source.data[2][0])
    np.testing.assert_array_equal(reader.times, source.times[2] * 1e9)
    assert reader.dt == pytest.approx(DT_NS)
    assert reader.rep_rate == pytest.approx(REP_MHZ)


def test_native_sdt_view_retains_source_information_calibration_and_choice():
    """The dedicated settings surface is SDT-specific and uses actual reader fields."""
    from emtk.testing import Driver

    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = SDTReader(record_provenance=False)
    reader.load_file(str(SDT))
    app = ReaderSettingsApp(reader)
    try:
        driver = Driver(app, (760, 580))
        driver.frame(2)
        assert {"filename", "filename.browse", "file_info", "rep_rate", "dt", "curve_nbr"} <= (
            set(app.item_rects)
        )
        assert "col_x" not in app.item_rects
        source = app.sources["filename"]
        assert source.options["filter"] == "SDT files (*.sdt)"
        assert source.options["mmfdb"] is False
        assert next(s for s in app.spec["sections"] if s.get("attr") == "file_info")["lines"] == 9
        driver.click("curve_nbr")
        driver.click("2")
        assert reader.curve_nbr == 2
        group = reader.get_data(filename=reader.filename)
        assert len(group) == 3
    finally:
        app.close()


def test_native_browse_loads_the_selected_sdt_for_preview(tmp_path):
    """The actual file-picker callback reaches the headless scientific owner."""
    from emtk.testing import Driver

    from chisurf.emtk.reader_settings import ReaderSettingsApp

    copied = tmp_path / "preview.sdt"
    copied.write_bytes(SDT.read_bytes())
    reader = SDTReader(record_provenance=False)
    app = ReaderSettingsApp(reader)
    try:
        driver = Driver(app, (920, 640))
        driver.frame(2)
        driver.click("filename.browse")
        assert app.file_dialog is not None
        app.file_dialog.directory = str(tmp_path)
        driver.frame(2)
        driver.click(copied.name)
        driver.click("Open")
        assert reader.filename == str(copied)
        assert reader.curve_options() == [0, 1, 2]
        assert reader.dt == pytest.approx(DT_NS)
        assert reader.rep_rate == pytest.approx(REP_MHZ)
        assert len(reader.get_data()) == 3
    finally:
        app.close()


def test_sdt_native_declaration_validates_against_the_shared_dialect():
    """Native-only source options and text height remain declared and validated."""
    from chisurf.core.dataspec.schema import validate_view_spec

    assert validate_view_spec(SDTReader(record_provenance=False).view_spec()) == []


def test_sdt_source_configuration_stays_lazy_until_import(tmp_path):
    """The generic reader's filename initialization cannot trigger file access."""
    reader = SDTReader(filename=str(tmp_path / "unavailable.sdt"), record_provenance=False)
    assert reader.filename.endswith("unavailable.sdt")
    assert reader.curve_options() == []
    reader.filename = str(SDT)
    assert len(reader.get_data()) == 3
