"""End-to-end burst-fusion tests on a real burst-analysis folder.

The fixture is the ten-measurement ``bh_spc132_sm_dna`` burst analysis shipped
with the burst-selection plugin: real SPC photon streams with a real ``bi4_bur``
folder beside them, so the emitted folder is exercised through the same readers
every downstream step uses rather than through a mock.
"""

from __future__ import annotations

import json
import pathlib
import shutil

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.burst import read_bur_file, read_bur_with_companions
from chisurf.core.fio.fluorescence.burst_companion import is_companion_dir
from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings
from chisurf.plugins.burst.burst_fusion.core.fusion import (
    FusionError,
    analyze,
    bur_files,
    data_rows,
    fuse_folder,
    read_measurements,
    write_fused_analysis,
)

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
)
ANALYSIS = "burstwise_All 0.1000#15"

#: The fixture folder predates the reading manifest, so the detector definition
#: has to be supplied — exactly as the workflow's channel page supplies it.
DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
    "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
}
WINDOWS = {"prompt": [0, 2048], "delayed": [2048, 4095]}


@pytest.fixture
def folder(tmp_path):
    """Return a private copy of the burst analysis, beside its raw measurements."""
    if not DATA.is_dir():
        pytest.skip("burst-selection test data not available")
    target = tmp_path / "data"
    shutil.copytree(DATA, target)
    return target / ANALYSIS


def test_reads_every_measurement_without_the_zero_rows(folder):
    frames = read_measurements(folder)
    assert len(frames) == 10
    for stem, frame in frames.items():
        raw = read_bur_file(folder / "bi4_bur" / f"{stem}.bur")
        # 2n + 1 interleaved on disk, n bursts in memory.
        assert len(frame) == (len(raw) - 1) // 2
        assert (frame["First File"] == f"{stem}.spc").all()


def test_analyze_reports_a_window_and_fewer_bursts(folder):
    result = analyze(folder, FusionSettings(threshold=0.5))
    stats = result.statistics

    assert stats["n_measurements"] == 10
    assert stats["n_bursts_before"] > stats["n_bursts_after"] > 0
    assert result.window.tau_max_s > 0
    # The gap ceiling binds on this dilute sample: P_same stays high far longer
    # than any single passage lasts.
    assert result.tau_used_s == pytest.approx(0.01)
    assert stats["gap_capped"] is True
    assert stats["photons"]["after"]["mean"] > stats["photons"]["before"]["mean"]


def test_a_threshold_of_one_fuses_nothing(folder):
    result = analyze(folder, FusionSettings(threshold=1.0))
    assert result.statistics["n_bursts_after"] == result.statistics["n_bursts_before"]
    assert result.statistics["n_fused_groups"] == 0


def test_a_lower_threshold_fuses_at_least_as_much(folder):
    strict = analyze(folder, FusionSettings(threshold=0.9)).statistics
    loose = analyze(folder, FusionSettings(threshold=0.2)).statistics
    assert loose["n_bursts_after"] <= strict["n_bursts_after"]


def test_the_gap_ceiling_bounds_the_fused_span(folder):
    tight = analyze(folder, FusionSettings(threshold=0.5, max_gap_ms=0.5))
    loose = analyze(folder, FusionSettings(threshold=0.5, max_gap_ms=50.0))
    assert tight.tau_used_s == pytest.approx(5e-4)
    assert tight.statistics["n_bursts_after"] > loose.statistics["n_bursts_after"]


def test_written_folder_is_a_burst_folder(folder, tmp_path):
    result = analyze(folder, FusionSettings(threshold=0.5))
    out = write_fused_analysis(result, detectors=DETECTORS, windows=WINDOWS)
    target = pathlib.Path(out["output_folder"])

    assert target.parent == folder.parent, "the fused folder is a sibling of its source"
    assert len(sorted((target / "bi4_bur").glob("*.bur"))) == 10
    assert bur_files(target)  # discoverable by the same reader

    # Every emitted table carries the full .bur column set, regenerated from the
    # photons (not copied), and keeps the 2n+1 interleaved layout.
    frame = read_bur_file(target / "bi4_bur" / "m000.bur")
    assert len(frame) % 2 == 1
    for column in ("First Photon", "Number of Photons (green)", "Mean Microtime (red) (ns)"):
        assert column in frame.columns

    rows = data_rows(frame)
    assert (rows["Number of Photons"] == rows["Last Photon"] - rows["First Photon"] + 1).all()
    assert rows["First Photon"].is_monotonic_increasing


def test_fused_bursts_span_their_fragments(folder):
    """A fused burst starts at its first fragment and ends at its last."""
    result = analyze(folder, FusionSettings(threshold=0.5))
    out = write_fused_analysis(result, detectors=DETECTORS, windows=WINDOWS)
    target = pathlib.Path(out["output_folder"])

    source = result.measurements[0].source
    labels = np.asarray(result.measurements[0].labels)
    emitted = data_rows(read_bur_file(target / "bi4_bur" / "m000.bur"))

    for label in range(min(5, labels.max() + 1)):
        group = source[labels == label]
        match = emitted[emitted["First Photon"] == int(group["First Photon"].min())]
        if match.empty:  # a degenerate one-photon burst the writer skips
            continue
        assert int(match.iloc[0]["Last Photon"]) == int(group["Last Photon"].max())


def test_companions_follow_the_contract_and_merge(folder):
    result = analyze(folder, FusionSettings(threshold=0.5))
    out = write_fused_analysis(result, detectors=DETECTORS, windows=WINDOWS)
    target = pathlib.Path(out["output_folder"])

    # Discoverable: a folder reader finds companions by the trailing "4".
    assert is_companion_dir("fu4") and is_companion_dir("fg4")
    assert (target / "fu4" / "m000.fu4").is_file()
    assert (folder / "fg4" / "m000.fg4").is_file()

    # One row per burst, so the positional merge lines up.
    merged = read_bur_with_companions(target / "bi4_bur" / "m000.bur")
    assert "Fused Bursts" in merged.columns
    assert "Fused Gap Photons" in merged.columns
    rows = data_rows(merged)
    assert (rows["Fused Bursts"] >= 1).all()
    assert rows["Fused Bursts"].max() > 1

    source_merged = read_bur_with_companions(folder / "bi4_bur" / "m000.bur")
    assert "Fusion Group" in source_merged.columns
    source_rows = data_rows(source_merged)
    assert len(source_rows) == len(result.measurements[0].source)
    np.testing.assert_allclose(
        source_rows["Fusion Group"].to_numpy(dtype=float),
        np.asarray(result.measurements[0].labels, dtype=float),
    )


def test_the_source_bursts_are_left_alone(folder):
    before = {
        path.name: path.read_bytes() for path in sorted((folder / "bi4_bur").glob("*.bur"))
    }
    fuse_folder(folder, FusionSettings(threshold=0.4), detectors=DETECTORS, windows=WINDOWS)
    after = {
        path.name: path.read_bytes() for path in sorted((folder / "bi4_bur").glob("*.bur"))
    }
    assert before == after


def test_run_is_recorded_for_reproduction(folder):
    result = analyze(folder, FusionSettings(threshold=0.7, max_gap_ms=5.0))
    out = write_fused_analysis(result, detectors=DETECTORS, windows=WINDOWS)
    target = pathlib.Path(out["output_folder"])

    info = json.loads((target / "Info" / "fusion.json").read_text())
    assert info["settings"]["threshold"] == 0.7
    assert info["tau_used_s"] == pytest.approx(0.005)
    assert info["source_folder"] == str(folder)
    assert len(info["p_same_curve"]["tau_s"]) == len(info["p_same_curve"]["p_same"])

    # The reading manifest lets a later step reopen the photons without guessing.
    manifest = json.loads((target / "Info" / "analysis.json").read_text())
    assert manifest["settings"]["burst_fusion"]["threshold"] == 0.7
    assert manifest["sources"], "the raw measurements must be recorded"
    assert (target / "Info").glob("*.mti")


def test_a_second_run_does_not_overwrite_the_first(folder):
    first = fuse_folder(folder, FusionSettings(threshold=0.5), detectors=DETECTORS, windows=WINDOWS)
    second = fuse_folder(folder, FusionSettings(threshold=0.5), detectors=DETECTORS, windows=WINDOWS)
    assert first["output_folder"] != second["output_folder"]
    assert pathlib.Path(first["output_folder"]).is_dir()


def test_missing_detector_definition_is_an_error_not_a_broken_table(folder):
    """Better to refuse than to write a table missing its per-detector columns."""
    result = analyze(folder, FusionSettings(threshold=0.5))
    with pytest.raises(FusionError, match="detector definition"):
        write_fused_analysis(result)


def test_folder_without_bursts_is_reported(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FusionError, match="no .bur"):
        analyze(tmp_path / "empty")


def test_fused_folder_can_itself_be_fused(folder):
    """The output is an ordinary burst folder — including for this step."""
    out = fuse_folder(
        folder, FusionSettings(threshold=0.5, max_gap_ms=1.0),
        detectors=DETECTORS, windows=WINDOWS,
    )
    again = analyze(pathlib.Path(out["output_folder"]), FusionSettings(threshold=0.5))
    assert again.statistics["n_bursts_before"] == out["statistics"]["n_bursts_after"]
