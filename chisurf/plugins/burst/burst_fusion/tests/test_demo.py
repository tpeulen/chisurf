"""The demo measurement: it must actually contain the problem it teaches.

A demo whose bursts are *not* split would walk a user through the tour and show
them nothing, quietly. These tests pin the three properties the guide depends
on: the search really does cut crossings up, fusing at the threshold the guide
quotes really does recover the declared molecule count, and the answer really is
declared rather than measured after the fact.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from chisurf.core.datastore import column_names, row_count
import pytest

from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings
from chisurf.plugins.burst.burst_fusion.core.fusion import analyze, read_measurements
from chisurf.plugins.burst.burst_fusion.demo import (
    DEMO,
    create_demo,
    demo_detectors,
    demo_directory,
    describe,
)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Build the demo once; it is deterministic, so the module can share it."""
    return create_demo(directory=tmp_path_factory.mktemp("burst_fusion_demo"))


def test_demo_writes_a_real_measurement_and_a_real_burst_folder(demo):
    source = pathlib.Path(demo["source"])
    folder = pathlib.Path(demo["folder"])

    assert source.is_file() and source.suffix == ".ht3"
    assert (folder / "bi4_bur").is_dir()
    assert sorted((folder / "bi4_bur").glob("*.bur"))
    # The reading manifest is what lets the fused folder be regenerated without
    # anyone supplying a detector definition.
    assert (folder / "Info" / "analysis.json").is_file()


def test_the_search_really_splits_the_crossings(demo):
    """Without this the demo teaches nothing: it must contain the defect."""
    truth = demo["truth"]
    assert truth["n_molecules"] == DEMO["n_molecules"]
    assert truth["n_crossings_split"] > 0.4 * truth["n_molecules"]
    # More bursts than molecules is the whole point.
    assert demo["bursts"] > 1.2 * truth["n_molecules"]


def test_fusing_recovers_the_declared_molecule_count(demo):
    """At the threshold the guide quotes, the burst count comes back to the truth."""
    truth = demo["truth"]
    result = analyze(demo["folder"], FusionSettings(threshold=0.7))
    recovered = result.statistics["n_bursts_after"]
    assert abs(recovered - truth["n_molecules"]) < 0.1 * truth["n_molecules"]
    # And it is a genuine repair, not just fewer rows: the width of the (single)
    # FRET population falls, because the fragments' shot noise is removed.
    ratio = result.statistics["proximity_ratio"]
    assert ratio["after"]["std"] < ratio["before"]["std"]
    assert abs(ratio["after"]["mean"] - ratio["before"]["mean"]) < 0.01


def test_a_higher_threshold_under_fuses_and_a_lower_one_overshoots(demo):
    """The three-point story the guide walks through has to hold."""
    truth = demo["truth"]["n_molecules"]
    conservative = analyze(demo["folder"], FusionSettings(threshold=0.9)).statistics
    balanced = analyze(demo["folder"], FusionSettings(threshold=0.7)).statistics
    permissive = analyze(demo["folder"], FusionSettings(threshold=0.5)).statistics

    assert conservative["n_bursts_after"] > truth
    assert permissive["n_bursts_after"] < truth < conservative["n_bursts_after"]
    assert (
        permissive["n_bursts_after"]
        <= balanced["n_bursts_after"]
        <= conservative["n_bursts_after"]
    )


def test_the_gaps_are_inside_the_default_ceiling(demo):
    """The demo must not need its ceiling raised to work."""
    gaps = np.asarray(demo["truth"]["gap_ms"], dtype=float)
    assert gaps.size
    assert float(np.median(gaps)) < 2.0
    # The shipped default is 10 ms; the demo must sit well inside it.
    assert float(np.percentile(gaps, 95)) < 10.0
    assert FusionSettings().max_gap_ms == 10.0


def test_the_demo_is_cached_not_rebuilt(demo, tmp_path):
    """The second press of the button must be instant, and the same folder."""
    again = create_demo(directory=pathlib.Path(demo["source"]).parent)
    assert again["folder"] == demo["folder"]
    assert again["bursts"] == demo["bursts"]

    record = pathlib.Path(demo["source"]).parent / "burst_fusion_demo.json"
    assert record.is_file()
    assert json.loads(record.read_text())["truth"]["n_molecules"] == DEMO["n_molecules"]


def test_the_demo_bursts_are_readable_by_the_ordinary_reader(demo):
    frames = read_measurements(demo["folder"])
    assert frames
    total = sum(row_count(frame) for frame in frames.values())
    assert total == demo["bursts"]
    frame = next(iter(frames.values()))
    for detector in demo_detectors():
        assert f"Number of Photons ({detector})" in column_names(frame)


def test_describe_states_the_truth_next_to_the_result(demo):
    text = describe(demo)
    assert str(demo["truth"]["n_molecules"]) in text
    assert str(demo["bursts"]) in text


def test_demo_directory_is_absolute_even_without_settings(monkeypatch):
    """A relative default would write the demo into the working directory."""
    import chisurf.core.settings as settings_mod

    monkeypatch.setattr(settings_mod, "chisurf_settings_path", "", raising=False)
    assert demo_directory().is_absolute()
