"""Reading a burst-analysis folder into the arrays a 2D MFD fit consumes.

The subject is a real BH SPC-132 single-molecule DNA measurement shipped with the
burst-selection plugin: ten ``.spc`` files and a burst folder written *before* the
writer learned to emit the mean micro time, which makes it both the milestone
dataset and the compatibility path.

What these tests are actually defending:

* a burst table is a set of pointers into a photon stream, so an unresolvable or
  empty stream must **raise** rather than yield zero photons;
* the photon-index convention differs between folder vintages, and reading one with
  the other's convention shifts every mean micro time by one photon;
* a detector whose channel definition cannot be checked against the count columns is
  unusable, not merely undocumented;
* the nuisance measure holds observation **times**, and excludes nothing silently.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.photons import StreamDef
from chisurf.core.fluorescence.mfd import (
    UnresolvedPhotonSource,
    nuisance_measure,
    photon_bursts,
    prepare_burst_folder,
    resolve_sources,
)
from chisurf.core.fluorescence.mfd.prepare import (
    burst_directory,
    detector_names,
    photon_index_convention,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
DATA = (
    REPO
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)
ANALYSIS = DATA / "burstwise_All 0.1000#15"

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)


@pytest.fixture(scope="module")
def preparation():
    """Return the shipped burst folder, prepared with its photons."""
    return prepare_burst_folder(ANALYSIS, with_photons=True)


# ──────────────────────────────────────────────────────────────────────────────
# Folder layout
# ──────────────────────────────────────────────────────────────────────────────
def test_burst_directory_accepts_all_three_handles():
    """The analysis folder, the bi4_bur directory and a .bur file all resolve."""
    analysis, bur = burst_directory(ANALYSIS)
    assert bur.name == "bi4_bur"
    assert analysis == ANALYSIS

    from_dir = burst_directory(ANALYSIS / "bi4_bur")
    from_file = burst_directory(ANALYSIS / "bi4_bur" / "m000.bur")
    assert from_dir == from_file == (analysis, bur)


def test_detector_names_come_from_the_count_columns():
    """Detector names are read off the table, not configured."""
    from chisurf.core.fluorescence.burst.photons import load_bur_dataframe

    frame = load_bur_dataframe(sorted((ANALYSIS / "bi4_bur").glob("*.bur")))
    assert detector_names(frame) == ("green", "red", "yellow")


# ──────────────────────────────────────────────────────────────────────────────
# The photon-index convention
# ──────────────────────────────────────────────────────────────────────────────
def test_legacy_folder_is_detected_as_exclusive(preparation):
    """This folder counts ``Last - First``; reading it as inclusive adds a photon.

    Not a cosmetic difference: the extra photon enters the mean micro time of every
    burst, and a shifted mean micro time reads as a shifted lifetime.
    """
    assert preparation.convention.inclusive is False
    assert preparation.convention.agreement == pytest.approx(1.0)


def test_convention_detection_is_unanimous_or_reported():
    """The reported agreement is the fraction of rows that actually fit."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "First Photon": [0, 10, 100],
            "Last Photon": [4, 14, 104],
            "Number of Photons": [5, 5, 4],
        }
    )
    convention = photon_index_convention(frame)
    assert convention.inclusive is True
    assert convention.agreement == pytest.approx(2.0 / 3.0)
    assert convention.stop_offset == 1


# ──────────────────────────────────────────────────────────────────────────────
# Source resolution — the loud-failure rule
# ──────────────────────────────────────────────────────────────────────────────
def test_sources_resolve_through_the_mti_sidecar(preparation):
    """A folder with no manifest still finds its photons, and says how."""
    assert len(preparation.sources.paths) == 10
    assert set(preparation.sources.origin.values()) == {"mti"}
    for path in preparation.sources.paths.values():
        assert path.is_file()


def test_unresolvable_source_raises_with_the_places_searched(tmp_path):
    """A burst table pointing at a file that is nowhere is an error, not empty data."""
    bur_dir = tmp_path / "analysis" / "bi4_bur"
    bur_dir.mkdir(parents=True)
    (bur_dir / "x.bur").write_text(
        "First Photon\tLast Photon\tNumber of Photons\tFirst File\n"
        "0\t1\t2\tnowhere.ptu\n",
        encoding="utf-8",
    )
    with pytest.raises(UnresolvedPhotonSource) as excinfo:
        resolve_sources(tmp_path / "analysis", ["nowhere.ptu"])
    message = str(excinfo.value)
    assert "nowhere.ptu" in message
    assert "analysis.json" in message and ".mti" in message


def test_empty_read_raises_rather_than_returning_no_photons(tmp_path):
    """A file that opens with zero photons is the failure this module exists for."""
    from chisurf.core.fluorescence.mfd.prepare import SourceResolution, open_sources

    empty = tmp_path / "empty.ptu"
    empty.write_bytes(b"not a photon file")
    resolution = SourceResolution(
        paths={"empty.ptu": empty}, origin={"empty.ptu": "sibling"},
        container_type={"empty.ptu": None},
    )
    with pytest.raises(UnresolvedPhotonSource, match="zero photons"):
        open_sources(resolution)


# ──────────────────────────────────────────────────────────────────────────────
# The prepared arrays
# ──────────────────────────────────────────────────────────────────────────────
def test_shapes_and_sentinels(preparation):
    """One row per burst, sentinel rows gone, spans in seconds."""
    n = len(preparation)
    assert n == 2980
    assert preparation.summary["n_sentinel_rows"] == 2990
    assert preparation.counts.shape == (n, 3)
    assert preparation.spans.shape == (n, 3)
    assert preparation.mean_micro_time.shape == (n, 3)
    assert preparation.rows.shape == (n,)

    # Spans are seconds and never negative; the -1.0 placeholder is a mask, not a value.
    assert preparation.spans.min() >= 0.0
    assert preparation.spans.max() < 1.0
    assert preparation.span_is_sentinel.any()
    assert np.all(preparation.spans[preparation.span_is_sentinel] == 0.0)


def test_counts_and_spans_agree_with_the_table(preparation):
    """The two descriptions of the same bursts must not disagree."""
    from chisurf.core.fluorescence.burst.photons import load_bur_dataframe
    from chisurf.core.fluorescence.mfd.prepare import (
        is_sentinel_file_reference,
    )

    frame = load_bur_dataframe(sorted((ANALYSIS / "bi4_bur").glob("*.bur")))
    real = ~np.array(
        [is_sentinel_file_reference(v) for v in frame["First File"].to_numpy(object)]
    )
    frame = frame.loc[real].reset_index(drop=True)
    for i, name in enumerate(preparation.channels):
        assert np.array_equal(
            preparation.counts[:, i],
            frame[f"Number of Photons ({name})"].to_numpy(np.int64),
        )


def test_mean_micro_time_matches_the_writer_for_the_same_photons(preparation):
    """The photon fallback reproduces what the writer's column would hold.

    PRD-72 item 2's acceptance: a folder written before the mean-micro-time column
    existed must yield the same ``<t>`` as one written after. Rather than trusting
    that, the writer's own helper is run over the same photon selection.
    """
    from chisurf.core.fio.fluorescence.burst import (
        mean_micro_time_ns,
        micro_time_resolution_ns,
    )
    from chisurf.core.fluorescence.burst.photons import stream_index_arrays

    tttrs = preparation.summary["_tttrs"]
    green = preparation.channel_index("green")
    streams = list(preparation.streams)

    checked = 0
    for row in range(0, len(preparation), 337):
        tttr = tttrs[preparation.file_key[row]]
        lo = int(preparation.first_photon[row])
        hi = int(preparation.last_photon[row]) + 1
        channels = np.asarray(tttr.routing_channels)[lo:hi]
        micro = np.asarray(tttr.micro_times)[lo:hi]
        index = stream_index_arrays(channels, micro, streams)
        expected = mean_micro_time_ns(
            micro, np.nonzero(index == green)[0], micro_time_resolution_ns(tttr)
        )
        got = preparation.mean_micro_time[row, green]
        if expected < 0.0:
            assert np.isnan(got)
        else:
            assert got == pytest.approx(expected, rel=1e-12)
        checked += 1
    assert checked > 5


def test_mean_micro_time_is_nanoseconds_and_within_the_tac_window(preparation):
    """A raw-channel value would be meaningless without the header that made it."""
    green = preparation.mean_micro_time[:, preparation.channel_index("green")]
    finite = green[np.isfinite(green)]
    assert finite.size > 2000
    # BH SPC-132 here: 4096 channels of 3.296 ps -> a 13.5 ns TAC window.
    assert 0.0 < finite.min() and finite.max() < 14.0
    assert 3.0 < np.median(finite) < 8.0


# ──────────────────────────────────────────────────────────────────────────────
# Channel definitions are verified, not assumed
# ──────────────────────────────────────────────────────────────────────────────
def test_inference_recovers_the_delayed_window_and_proves_it(preparation):
    """The acceptor-excitation detector is a micro-time window no *name* conveys.

    It does not have to be named, though: the window is offered by the ``.bur``
    header (``S delayed yellow | 2048-4095``) and accepted only when the counts
    recomputed from the photons reproduce the detector's count column exactly. So
    ``yellow`` verifies here without anyone declaring it -- and it verifies on the
    evidence, not on its name, which is the property that matters.
    """
    assert set(preparation.verified_channels) == {"green", "red", "yellow"}
    assert preparation.summary["unverified_channels"] == ()
    assert preparation.summary["stream_origin"] == "inferred"
    # Verified means reproduced, not merely plausible.
    for name, agreement in preparation.summary["count_agreement"].items():
        assert agreement == pytest.approx(1.0), name
    preparation.require_verified(["green", "red", "yellow"])


def test_a_detector_that_is_not_there_is_refused(preparation):
    """``require_verified`` is the gate everything turning photons into physics uses."""
    with pytest.raises(ValueError, match="does not describe"):
        preparation.require_verified(["infrared"])


def test_explicit_streams_verify_the_delayed_window():
    """Given the real definition, the third detector verifies like the others.

    ``yellow`` is the acceptor channels gated on the *delayed* micro-time window —
    the definition the ``.bur`` header names in its ``S delayed yellow | 2048-4095``
    column but does not record as a detector. It therefore *overlaps* ``red``, which
    is ungated: the same photon is in both, and verification has to allow that.
    """
    streams = [
        StreamDef("green", [0, 8], []),
        StreamDef("red", [1, 9], []),
        StreamDef("yellow", [1, 9], [(2048, 4095)]),
    ]
    prepared = prepare_burst_folder(ANALYSIS, streams=streams, with_photons=True)
    assert prepared.summary["count_agreement"]["yellow"] == pytest.approx(1.0)
    assert prepared.verified_channels == ("green", "red", "yellow")


def test_a_wrong_definition_is_refused_outright():
    """If nothing verifies, the folder does not load at all."""
    streams = [
        StreamDef("green", [77], []),
        StreamDef("red", [78], []),
        StreamDef("yellow", [79], []),
    ]
    with pytest.raises(ValueError, match="no channel definition"):
        prepare_burst_folder(ANALYSIS, streams=streams, with_photons=True)


# ──────────────────────────────────────────────────────────────────────────────
# The nuisance measure
# ──────────────────────────────────────────────────────────────────────────────
def test_nuisance_holds_times_not_counts(preparation):
    """D12 is P(S, t_G, t_R): a signal and two observation spans, in seconds."""
    measure = nuisance_measure(preparation)
    assert len(measure) == 2980
    assert measure.channels == ("green", "red")
    assert measure.spans.shape == (len(measure), 2)
    assert measure.signal.dtype == np.int64
    # The spans are times: milliseconds-scale, and unrelated to the counts.
    assert measure.spans.max() < 0.05
    assert np.corrcoef(measure.signal, measure.spans[:, 0])[0, 1] < 0.99


def test_nuisance_counts_what_it_excludes(preparation):
    """A folder where half the bursts are unusable must not look like a clean one."""
    measure = nuisance_measure(preparation, min_signal=40)
    assert measure.summary["n_input"] == 2980
    assert measure.summary["n_excluded_low_signal"] > 0
    assert (
        measure.summary["n_kept"] + measure.summary["n_excluded_low_signal"]
        == measure.summary["n_input"]
    )
    # Bursts with no red photons have no measurable red span; they are kept, and
    # the fact is reported rather than presented as a zero-length observation.
    assert measure.summary["n_sentinel_spans"]["red"] > 0


def test_nuisance_binning_conserves_the_bursts(preparation):
    """Compressing the measure onto a grid may not lose or invent bursts."""
    measure = nuisance_measure(preparation)
    weights, signal, spans = measure.binned(n_signal_bins=16, n_span_bins=6)
    assert weights.sum() == pytest.approx(len(measure))
    # One entry per channel, plus the whole-burst duration the kinetics needs.
    assert len(spans) == 3
    assert np.all(spans[-1][weights > 0] > 0)
    occupied = weights > 0
    assert signal[occupied].min() >= measure.signal.min()
    assert signal[occupied].max() <= measure.signal.max()


# ──────────────────────────────────────────────────────────────────────────────
# The packed photon layout
# ──────────────────────────────────────────────────────────────────────────────
def test_photon_bursts_agree_with_the_table(preparation):
    """Per-burst offsets must reproduce the counts the .bur reports."""
    bursts, micro, rows = photon_bursts(preparation)
    lengths = np.diff(bursts.offsets)
    green = preparation.channel_index("green")
    red = preparation.channel_index("red")
    expected = (
        preparation.counts[rows, green] + preparation.counts[rows, red]
    )
    assert np.array_equal(lengths, expected)
    assert [m.size for m in micro] == list(lengths)
    assert bursts.n_colors == len(preparation.streams)
    # Times are seconds and non-decreasing within a burst.
    for b in range(0, len(bursts), 501):
        t = bursts.times[bursts.offsets[b] : bursts.offsets[b + 1]]
        assert np.all(np.diff(t) >= 0)


def test_photons_are_refused_when_not_loaded():
    """Asking for photons a preparation does not carry is an error, not a silent []."""
    prepared = prepare_burst_folder(ANALYSIS, with_photons=False)
    with pytest.raises(ValueError, match="with_photons=True"):
        photon_bursts(prepared)
