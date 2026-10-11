"""The PDA reader's inputs and settings, without a window.

What the 2,000-line Qt panel used to own -- which detector a colour row takes,
what a channel or micro-time field means, the time-window list, the file list,
and how ``.bur`` tables and burst folders become photon intervals -- lives in
``chisurf.core.experiments.pda2c.inputs`` and ``.settings`` now. These tests pin
it where it lives, so both the Qt panel and the emtk form inherit it.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.experiments.pda2c import Pda2cReader, inputs
from chisurf.core.experiments.pda2c.settings import NO_SETUP, PdaReaderSettings

DATA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
BURSTS = DATA / "burstwise_All 0.1000#15"

SETUPS = {
    "Confocal": {
        "detectors": {
            "green": {"chs": [0, 2], "micro_time_ranges": [[0, 4095]]},
            "red": {"chs": [1, 3], "micro_time_ranges": [[100, 3000]]},
        },
        "tttr_reading": {"file_type": "SPC-130"},
    },
    "Three": {
        "detectors": {
            "blue": {"chs": [4], "micro_time_ranges": [[0, 10]]},
            "green": {"chs": [0], "micro_time_ranges": [[0, 10]]},
            "red": {"chs": [1], "micro_time_ranges": [[0, 10]]},
        },
    },
}


def _reader(**kw):
    kw.setdefault("channels", [[0, 3], [1, 2]])
    kw.setdefault("micro_time_ranges", [[0, 16000], [0, 16000]])
    return Pda2cReader(**kw)


# ── field text ─────────────────────────────────────────────────────────────────


def test_micro_time_fields_round_trip():
    assert inputs.parse_micro_time_ranges("1-16000; 20-30;bad;") == [[1, 16000], [20, 30]]
    assert inputs.format_micro_time_ranges([[1, 16000], [20, 30]]) == "1-16000;20-30"
    assert inputs.format_micro_time_ranges((0, 8000)) == "0-8000"
    assert inputs.format_micro_time_ranges(7) == "7-7"
    assert inputs.format_micro_time_ranges(None) == ""


def test_channel_fields_skip_what_is_not_a_channel():
    """A stray token is dropped, not a crash in a field's edit handler."""
    assert inputs.parse_channels("0, 3; x, 5") == [0, 3, 5]
    assert inputs.format_channels([1, 2]) == "1, 2"


def test_a_row_takes_the_detector_named_after_its_colour():
    detectors = SETUPS["Confocal"]["detectors"]
    assert inputs.preferred_detectors(detectors, 2) == ["green", "red"]
    # No blue detector: rows fall back to the setup's order, never all to one.
    assert inputs.preferred_detectors(detectors, 3) == ["green", "green", "red"]
    assert inputs.preferred_detectors({}, 2) == ["", ""]


def test_time_windows_drop_duplicates_and_nonsense():
    configs = inputs.add_tw_config([(10, 1e-3)], 10, 1e-3)
    assert configs == [(10, 1e-3)]
    assert inputs.add_tw_config(configs, 0, 1e-3) == configs
    assert inputs.valid_tw_configs([(5, 0.0), ("a", 1), (3, 2e-3)]) == [(3, 2e-3)]
    assert inputs.tw_label(20, 2e-3) == "20 ph @ 2 ms"


# ── the settings a form binds ─────────────────────────────────────────────────


def test_the_setup_fills_the_rows_and_the_routine():
    reader = _reader()
    settings = PdaReaderSettings(reader, setups=SETUPS, routines=["PTU", "SPC-130"])
    assert settings.setup == "Confocal"
    assert reader.channels == [[0, 2], [1, 3]]
    assert reader.micro_time_ranges == [[[0, 4095]], [[100, 3000]]]
    assert reader.reading_routine == "SPC-130"
    settings.detector_0 = "red"
    assert reader.channels[0] == [1, 3]
    # A second form over the same reader keeps what the first chose.
    again = PdaReaderSettings(reader, setups=SETUPS, routines=["PTU"])
    assert again.detector_0 == "red" and reader.channels[0] == [1, 3]


def test_without_a_setup_the_rows_are_typed_by_hand():
    reader = _reader()
    settings = PdaReaderSettings(reader, setups={}, routines=["PTU"])
    assert settings.setup_names() == [NO_SETUP] and settings.setup == NO_SETUP
    settings.setup = NO_SETUP  # the placeholder changes nothing
    assert reader.channels == [[0, 3], [1, 2]]
    settings.channels_1 = "5, 6"
    settings.window_0 = "10-20;30-40"
    assert reader.channels == [[0, 3], [5, 6]]
    assert reader.micro_time_ranges[0] == [[10, 20], [30, 40]]


def test_three_colours_make_the_windows_excitation_periods():
    reader = _reader()
    settings = PdaReaderSettings(reader, setups=SETUPS, routines=["PTU"])
    settings.setup = "Three"
    reader.n_colors = 3
    assert settings.sync() is True and settings.three_colours
    assert reader.detector_names == ["blue", "green", "red"]
    assert reader.channels == [[4], [0], [1]]
    settings.window_0, settings.window_1 = "0-8000", "8000-16000"
    assert reader.micro_time_ranges == [[0, 8000], [8000, 16000]]
    assert len(reader.detection_windows()) == 5
    assert settings.sync() is False


def test_a_form_starts_with_the_usual_time_windows():
    reader = _reader()
    assert reader.tw_configs is None, "a reader without a form reads one window"
    settings = PdaReaderSettings(reader, setups={}, routines=["PTU"])
    assert [row["window"] for row in settings.tw_rows()] == [
        "10 ph @ 1 ms",
        "20 ph @ 2 ms",
        "30 ph @ 3 ms",
    ]
    settings.tw_ms = 4.0
    reader.minimum_number_of_photons = 40
    settings.add_tw()
    settings.add_tw()
    assert reader.tw_configs[-1] == (40, 4e-3) and len(reader.tw_configs) == 4
    rows = settings.tw_rows()
    settings.remove_tw(rows[0])
    assert [row["n_ph"] for row in settings.tw_rows()] == [20, 30, 40]
    assert settings.tw_rows().revision > rows.revision or settings.tw_rows() is rows
    settings.clear_tw()
    assert reader.tw_configs == []


def test_the_file_list_is_the_readers_filename(tmp_path):
    reader = _reader()
    settings = PdaReaderSettings(reader, setups={}, routines=["PTU"])
    spc = tmp_path / "m.spc"
    spc.write_bytes(b"\0")
    junk = tmp_path / "notes.txt"
    junk.write_text("x")
    assert settings.add_paths([str(spc), str(junk), str(tmp_path), str(spc)]) == 2
    assert reader.filename == f"{spc}|{tmp_path}"
    settings.file_edited(settings.file_rows()[1], "use", False)
    assert reader.filename == str(spc) and settings.load_filename() == str(spc)
    settings.remove_file(settings.file_rows()[0])
    assert settings.checked_paths() == []
    reader.filename = f"{spc}|{junk}"
    assert [row["path"] for row in reader.files] == [str(spc), str(junk)]
    settings.clear_files()
    assert reader.files == []


# ── what a read takes ───────────────────────────────────────────────────────────


@pytest.mark.skipif(not BURSTS.is_dir(), reason="burst-analysis fixture missing")
def test_a_burst_folder_stands_for_the_bursts_its_tables_name():
    resolved = inputs.resolve_inputs([str(BURSTS)])
    names = sorted(pathlib.Path(f).name for f in resolved.tttr_files)
    assert names == [f"m00{i}.spc" for i in range(10)]
    assert all(resolved.burst_slices[f] for f in resolved.tttr_files)
    first = resolved.burst_slices[str(DATA / "m000.spc")]
    assert all(a < b for a, b in first) and first == sorted(first)


@pytest.mark.skipif(not BURSTS.is_dir(), reason="burst-analysis fixture missing")
def test_tables_win_over_the_files_given_beside_them():
    """With a table, its files are read; a TTTR file named beside it is not (the table selects)."""
    bur = BURSTS / "bi4_bur" / "m003.bur"
    resolved = inputs.resolve_inputs([str(bur), str(DATA / "m007.spc")])
    assert [pathlib.Path(f).name for f in resolved.tttr_files] == ["m003.spc"]


def test_a_tttr_file_with_a_burst_folder_beside_it_is_read_burst_wise(tmp_path):
    (tmp_path / "a.spc").write_bytes(b"\0")
    (tmp_path / "b.spc").write_bytes(b"\0")
    folder = tmp_path / "bi4_bur"
    folder.mkdir()
    (folder / "a.bur").write_text(
        "First Photon\tLast Photon\tFirst File\tLast File\n0\t9\ta\ta\n10\t19\ta\ta\n"
    )
    resolved = inputs.resolve_inputs([str(tmp_path / "a.spc"), str(tmp_path / "b.spc")], {".spc"})
    assert resolved.burst_slices == {str(tmp_path / "a.spc"): [(0, 20)]}
    assert len(resolved.tttr_files) == 2


def test_nothing_to_read_and_too_many_tables_are_refused(tmp_path):
    with pytest.raises(inputs.PdaInputError) as err:
        inputs.resolve_inputs([str(tmp_path / "missing.ptu")], {".ptu"})
    assert err.value.title == "No files"
    tables = [str(tmp_path / f"{i}.bur") for i in range(3)]
    for t in tables:
        pathlib.Path(t).write_text("First Photon\tLast Photon\tFirst File\tLast File\n")
    with pytest.raises(inputs.PdaInputError, match="BUR files"):
        inputs.resolve_inputs(tables, {".ptu"}, limit=2)
    with pytest.raises(inputs.PdaInputError) as err:
        inputs.resolve_inputs(tables, {".ptu"})
    assert err.value.title == "No TTTR files found"


def test_too_many_files_are_cut_with_a_warning(tmp_path):
    files = []
    for i in range(3):
        files.append(tmp_path / f"{i}.ptu")
        files[-1].write_bytes(b"\0")
    resolved = inputs.resolve_inputs([str(f) for f in files], {".ptu"}, limit=2)
    assert len(resolved.tttr_files) == 2
    assert [title for title, _ in resolved.warnings] == ["Too many files"]


@pytest.mark.skipif(not BURSTS.is_dir(), reason="burst-analysis fixture missing")
def test_the_reader_reads_a_burst_table_it_is_given():
    """A ``.bur`` handed to the reader selects the bursts of the measurement it names."""
    reader = _reader(channels=[[0, 8], [1, 9]], reading_routine="SPC-130")
    reader.minimum_number_of_photons = 20
    group = reader.read(filename=str(BURSTS / "bi4_bur" / "m000.bur"))
    assert len(group) == 1
    curve = group[0]
    assert [f["path"] for f in curve.meta_data["filenames"]] == [str(DATA / "m000.spc")]
    assert curve.pda["s1s2"].sum() > 0
