"""What the burst pipeline writes, the MFD reader must be able to read.

The two halves were developed against each other's *descriptions* rather than each
other's output: the reader was built from what a ``.bur`` folder is documented to
contain, and the writer from what an analysis is supposed to produce. That is
exactly the seam where a format drifts — and it did, twice, in ways nothing caught:

* an **empty micro-time range** meant "accept no photons" to the writer and "accept
  any" to every reader, so a detector defined by routing channels alone wrote an
  all-zero column for every per-detector quantity;
* a detector **name does not determine its definition**, so a reader that guessed
  ``red`` from the name got it right for one analysis and wrong for the next.

So this test runs the real burst pipeline over a real measurement and asserts the
folder it produces loads through the ordinary MFD path — no fixtures, no
hand-written tables, and nothing shared between the two sides but the files.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DATA = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
MEASUREMENT = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(
    not MEASUREMENT.is_file(), reason="the bh_spc132_sm_dna measurement is not present"
)

#: The detector layout of this instrument. ``red`` is deliberately gated to the
#: prompt window and ``yellow`` to the delayed one — the *same channels*, split by
#: micro time — because that is the arrangement a name-based guess cannot recover
#: and the one the reader has to infer.
DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": []},
    "red": {"chs": [1, 9], "micro_time_ranges": [(0, 2048)]},
    "yellow": {"chs": [1, 9], "micro_time_ranges": [(2048, 4096)]},
}
WINDOWS = {"prompt": (0, 2048), "delayed": (2048, 4096)}


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    """Run the real burst pipeline and return the folder it wrote."""
    from chisurf.plugins.burst.burst_selection.api.models import AnalysisSettings
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_file

    out = tmp_path_factory.mktemp("burst-pipeline")
    settings = AnalysisSettings()
    settings.burst_detection.min_photons = 40
    settings.burst_detection.photon_window = 10
    settings.burst_detection.time_window = 0.001

    result = analyze_file(
        MEASUREMENT,
        settings=settings,
        windows=WINDOWS,
        detectors=DETECTORS,
        output_dir=out / "bi4_bur",
        mti_output_dir=out,
    )
    assert result is not None
    return out


def test_the_pipeline_writes_a_folder_the_mfd_reader_accepts(produced):
    """The whole point: producer to consumer, with nothing hand-made in between."""
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data

    data = load_mfd_data(produced, min_green_photons=20)
    preparation = data.preparation

    assert len(preparation) > 100
    assert set(preparation.channels) >= {"green", "red"}
    # Every detector reproduced from the photons — including the two that share
    # routing channels and differ only by micro-time window.
    assert set(preparation.verified_channels) == set(preparation.channels)
    assert data.observed.n_used > 0


def test_the_per_detector_columns_are_not_all_zero(produced):
    """The failure a burst table can carry without looking wrong at all.

    An empty micro-time range used to zero every per-detector column. The table is
    still well-formed, the totals are still right, and only the detectors have
    silently never seen a photon — so the check has to be explicit.
    """
    from chisurf.core.fluorescence.mfd.prepare import prepare_burst_folder

    preparation = prepare_burst_folder(produced, with_photons=True)
    for index, name in enumerate(preparation.channels):
        counts = preparation.counts[:, index]
        assert counts.sum() > 0, f"detector {name} recorded no photons at all"
    # The three detectors together account for the whole burst — but *only* all
    # three. ``red`` is gated to the prompt window, so donor + acceptor alone falls
    # short by exactly the delayed photons, which is what ``yellow`` holds. Getting
    # this wrong the other way (assuming green + red is everything) is how a gated
    # detector silently loses a quarter of the signal.
    green = preparation.channel_index("green")
    red = preparation.channel_index("red")
    yellow = preparation.channel_index("yellow")
    two_colour = preparation.counts[:, green] + preparation.counts[:, red]
    three = two_colour + preparation.counts[:, yellow]
    assert np.all(three <= preparation.total_counts)
    assert float(np.mean(three == preparation.total_counts)) > 0.99
    # And the gate really is doing something: the prompt window is not everything.
    assert float(np.mean(two_colour == preparation.total_counts)) < 0.9


def test_the_reader_infers_the_definitions_the_writer_used(produced):
    """A detector name does not determine its definition, so it is measured.

    ``red`` and ``yellow`` here are the *same routing channels* split by micro-time
    window. No name-based rule can recover that, and guessing wrong is silent: the
    counts simply come out different and every downstream number moves with them.
    """
    from chisurf.core.fluorescence.mfd.prepare import prepare_burst_folder

    preparation = prepare_burst_folder(produced, with_photons=True)
    inferred = preparation.summary.get("inferred_streams")
    assert inferred is not None, "the definitions should have been inferred"

    assert sorted(inferred["green"]["channels"]) == [0, 8]
    assert sorted(inferred["red"]["channels"]) == [1, 9]
    assert sorted(inferred["yellow"]["channels"]) == [1, 9]
    # The two acceptor detectors are distinguished by their windows, not by name.
    assert inferred["red"]["micro_time_ranges"] != inferred["yellow"]["micro_time_ranges"]
    assert inferred["red"]["micro_time_ranges"][0][0] == 0
    assert inferred["yellow"]["micro_time_ranges"][0][0] == 2048


def test_the_produced_folder_fits(produced):
    """A folder that loads but cannot be fitted would not have closed the loop."""
    from chisurf.core.fluorescence.mfd.fit import MfdModel, load_mfd_data
    from chisurf.core.fluorescence.mfd.histogram import HistogramAxes
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    data = load_mfd_data(
        produced,
        axes=HistogramAxes.default(
            n_ratio=30, n_micro_time=30, micro_time_range=(2.0, 8.0)
        ),
        min_green_photons=20,
    )
    model = MfdModel(
        optics=Optics(r0=52.0, tau_d0=1.6, tau_a=3.0, sigma=6.0, alpha=0.03),
        states=[FretState(distance=54.0)],
        donor_only=0.4,
    )
    score = model.score(data)
    assert np.isfinite(score.score)
    assert score.n_points > 50
