"""A gated burst population, turned into a decay and a counting histogram.

``pda.from_bursts`` was the only way to take a sub-population selected in a burst
explorer and analyse its *photons*. These cover the two services that join it —
``tcspc.from_bursts`` and ``pch.from_bursts`` — and in particular the thing that
makes PCH different from the other three: binning only burst interiors changes
what P(k) means, so the service offers both readings and says which one ran.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.server.services import bursts

tttrlib = pytest.importorskip("tttrlib")

#: A real photon stream. Any TTTR file works — the assertions are all relative to
#: the file's own photons, never to absolute counts.
DATA = pathlib.Path(__file__).parents[1] / "data" / "clsm" / "PQ_Olympus_MFIS.ht3"

#: Two disjoint, contiguous photon-index intervals standing in for gated bursts.
INTERVALS = [[1000, 1999], [5000, 5999]]


@pytest.fixture(scope="module")
def photons():
    """The raw arrays, for computing ground truth independently of the service."""
    if not DATA.exists():
        pytest.skip(f"missing test data: {DATA}")
    tttr = tttrlib.TTTR(str(DATA))
    return {
        "path": str(DATA),
        "micro": np.asarray(tttr.micro_times),
        "macro": np.asarray(tttr.macro_times, dtype=np.float64),
        "routing": np.asarray(tttr.routing_channels),
        "macro_dt": float(tttr.header.macro_time_resolution),
        "n_micro_time_channels": int(tttr.header.number_of_micro_time_channels),
    }


@pytest.fixture
def slices(photons):
    """The gate, in the shape the explorer produces."""
    return {photons["path"]: INTERVALS}


def _selected(photons):
    """Photon indices the intervals cover."""
    return np.concatenate([np.arange(a, b + 1) for a, b in INTERVALS])


# ---------------------------------------------------------------- index maths


def test_intervals_are_clipped_to_the_file():
    """A burst table may name photons past the end of a truncated file."""
    index = bursts._selected_indices(50, [(40, 999)])
    assert index[0] == 40 and index[-1] == 49


def test_overlapping_intervals_are_not_double_counted():
    """Overlapping gates must not weight their shared photons twice."""
    index = bursts._selected_indices(100, [(0, 10), (5, 15)])
    assert index.tolist() == list(range(16))


def test_reversed_or_empty_intervals_are_dropped():
    """A ``last < first`` row contributes nothing rather than raising."""
    assert bursts._selected_indices(100, [(10, 5)]).size == 0


# ---------------------------------------------------------------------- TCSPC


def test_decay_equals_a_direct_histogram_of_the_gated_photons(photons, slices):
    """Ground truth: the service must reproduce a hand-computed histogram.

    The decay of a chosen set of photons is just their micro-time histogram —
    there is no modelling step to get wrong, so anything other than an exact
    match is a bug in the photon selection.
    """
    result = bursts.from_bursts_decay(
        None, burst_slices=slices, channels=[[0], [1]], stream_names=["green", "red"]
    )
    assert result["ok"], result

    index = _selected(photons)
    for decay in result["result"]["decays"]:
        channel = decay["channels"][0]
        counts = np.asarray(decay["counts"])
        truth = np.bincount(
            photons["micro"][index][photons["routing"][index] == channel],
            minlength=counts.size,
        )
        assert np.array_equal(counts, truth[: counts.size])
        assert decay["n_photons"] == int(truth.sum())


def test_decay_names_and_axis(photons, slices):
    """Names carry through and the time axis is in nanoseconds."""
    result = bursts.from_bursts_decay(
        None, burst_slices=slices, channels=[[0], [1]], stream_names=["green", "red"]
    )["result"]
    assert [d["name"] for d in result["decays"]] == ["green", "red"]
    axis = np.asarray(result["decays"][0]["time_axis"])
    assert axis[0] == 0.0
    assert np.allclose(np.diff(axis), result["micro_time_resolution_ns"])


def test_coarsening_preserves_the_total(photons, slices):
    """Rebinning moves photons between bins; it must not lose any."""
    fine = bursts.from_bursts_decay(None, burst_slices=slices, channels=[[0]])["result"]
    coarse = bursts.from_bursts_decay(
        None, burst_slices=slices, channels=[[0]], coarsening=8
    )["result"]
    assert coarse["decays"][0]["n_photons"] == fine["decays"][0]["n_photons"]
    assert len(coarse["decays"][0]["counts"]) < len(fine["decays"][0]["counts"])


def test_decay_rejects_an_empty_gate():
    """An empty selection is a bad request, not an empty decay."""
    assert not bursts.from_bursts_decay(None, burst_slices={})["ok"]


# ------------------------------------------------------------ micro-time axis
#
# The axis has to come from the instrument, not from the photons: an axis sized
# by the highest occupied bin is shorter than the TAC range (so it does not line
# up with an IRF measured on the same setup) and differs from file to file (so a
# gate spanning files cannot be summed at all).


def _synthetic(highest_micro_time: int, n_channels: int = 4096, n_photons: int = 2000):
    """Build an in-memory photon stream with a chosen occupied maximum."""
    rng = np.random.default_rng(highest_micro_time)
    micro = rng.integers(0, highest_micro_time, n_photons).astype(np.uint16)
    micro[-1] = highest_micro_time
    tttr = tttrlib.TTTR()
    tttr.append_events(
        np.arange(n_photons, dtype=np.uint64) * 100,
        micro,
        np.zeros(n_photons, dtype=np.int8),
        np.zeros(n_photons, dtype=np.int8),
        shift_macro_time=False,
    )
    header = tttr.header
    header.set_macro_time_resolution(1e-8)
    header.set_micro_time_resolution(1e-11)
    header.set_number_of_micro_time_channels(int(n_channels))
    tttr.set_header(header)
    return tttr


@pytest.fixture
def two_streams(monkeypatch):
    """Two files of the same setup whose occupied micro-time maxima differ."""
    files = {"a.ptu": _synthetic(2998), "b.ptu": _synthetic(4094)}
    monkeypatch.setattr(bursts, "_open", lambda path, routine=None: files[path])
    return files


def test_the_decay_spans_the_tac_range_not_the_occupied_bins(photons, slices):
    """The real file occupies fewer bins than its header declares."""
    result = bursts.from_bursts_decay(None, burst_slices=slices)["result"]
    declared = photons["n_micro_time_channels"]
    assert int(photons["micro"].max()) + 1 < declared  # the premise of the test
    assert len(result["decays"][0]["counts"]) == declared


def test_a_gate_spanning_two_files_is_summed(two_streams):
    """The whole point of ``burst_slices`` being a mapping."""
    gate = {"a.ptu": [[0, 999]], "b.ptu": [[0, 999]]}
    result = bursts.from_bursts_decay(None, burst_slices=gate)
    assert result["ok"], result
    decay = result["result"]["decays"][0]
    assert len(decay["counts"]) == 4096
    assert decay["n_photons"] == 2000
    assert result["result"]["n_files"] == 2


@pytest.mark.parametrize("coarsening", [1, 2, 3, 7, 8, 512])
def test_every_coarsening_keeps_the_two_files_on_one_axis(two_streams, coarsening):
    """Flooring ``n_bins // coarsening`` shortened the axis for some factors."""
    gate = {"a.ptu": [[0, 999]], "b.ptu": [[0, 999]]}
    result = bursts.from_bursts_decay(None, burst_slices=gate, coarsening=coarsening)
    assert result["ok"], result
    decay = result["result"]["decays"][0]
    assert len(decay["counts"]) == -(-4096 // coarsening)
    assert decay["n_photons"] == 2000


def test_files_with_different_tac_ranges_are_refused_clearly(monkeypatch):
    """Summing two setups is a bad request, not a NumPy broadcast error."""
    files = {
        "a.ptu": _synthetic(2998, n_channels=4096),
        "b.ptu": _synthetic(2998, n_channels=32768),
    }
    monkeypatch.setattr(bursts, "_open", lambda path, routine=None: files[path])
    gate = {"a.ptu": [[0, 999]], "b.ptu": [[0, 999]]}
    result = bursts.from_bursts_decay(None, burst_slices=gate)
    assert not result["ok"]
    assert "micro-time axis" in result["error"]
    assert "broadcast" not in result["error"]


# ------------------------------------------------------------------------ PCH


def test_pch_conserves_photons_and_normalises(slices):
    """P(k) must be a probability, and sum(k·counts) must be the photon count."""
    result = bursts.from_bursts_pch(None, burst_slices=slices, bin_time_us=200.0)["result"]
    assert abs(sum(result["p_exp"]) - 1.0) < 1e-9
    assert sum(k * c for k, c in zip(result["k_vals"], result["counts"])) == result["n_photons"]
    assert result["n_bins"] == sum(result["counts"])


def test_interior_counts_exactly_the_gated_photons(photons, slices):
    """Interior mode must see the gated photons and nothing else."""
    result = bursts.from_bursts_pch(
        None, burst_slices=slices, bin_time_us=200.0, mode="interior"
    )["result"]
    assert result["n_photons"] == len(_selected(photons))


def test_span_includes_the_photons_between_the_bursts(photons, slices):
    """Span mode is the whole trace between first and last gated photon.

    This is the difference that decides whether P(k) can be read as a brightness:
    span keeps the quiet stretches, so the low-k side of the histogram is real.
    """
    result = bursts.from_bursts_pch(
        None, burst_slices=slices, bin_time_us=200.0, mode="span"
    )["result"]
    first, last = INTERVALS[0][0], INTERVALS[-1][1]
    assert result["n_photons"] == last - first + 1
    assert result["n_photons"] > len(_selected(photons))


def test_span_analyses_more_bins_than_interior(slices):
    """Interior necessarily observes a subset of span's counting bins."""
    span = bursts.from_bursts_pch(None, burst_slices=slices, bin_time_us=200.0)["result"]
    interior = bursts.from_bursts_pch(
        None, burst_slices=slices, bin_time_us=200.0, mode="interior"
    )["result"]
    assert span["n_bins"] >= interior["n_bins"]


def test_interior_says_it_is_biased_and_span_does_not(slices):
    """The warning must travel with the data, not only live in the docs.

    A caller who ignores the docstring and fits brightness to an interior P(k)
    would get a too-high epsilon and a too-low N with nothing to indicate it.
    """
    interior = bursts.from_bursts_pch(
        None, burst_slices=slices, bin_time_us=200.0, mode="interior"
    )["result"]
    span = bursts.from_bursts_pch(
        None, burst_slices=slices, bin_time_us=200.0, mode="span"
    )["result"]

    assert interior["mode"] == "interior"
    assert "selection_bias" in interior
    assert "brightness" in interior["selection_bias"]
    assert span["mode"] == "span"
    assert "selection_bias" not in span


def test_duty_cycle_reports_how_far_apart_the_two_modes_are(slices):
    """The fraction of the span the bursts occupy, in (0, 1].

    Near 1 the two modes nearly agree; near 0 they differ enormously, which is
    exactly when reading an interior P(k) as an absolute brightness misleads.
    """
    result = bursts.from_bursts_pch(None, burst_slices=slices, bin_time_us=200.0)["result"]
    duty = result["burst_duty_cycle"]
    assert duty is not None and 0.0 < duty <= 1.0


def test_pch_rejects_a_bad_mode_and_a_bad_bin_time(slices):
    """Bad requests are refused rather than silently reinterpreted."""
    assert not bursts.from_bursts_pch(None, burst_slices=slices, mode="whatever")["ok"]
    assert not bursts.from_bursts_pch(None, burst_slices=slices, bin_time_us=0)["ok"]
    assert not bursts.from_bursts_pch(None, burst_slices={})["ok"]


def test_bin_shorter_than_a_macro_tick_is_refused(slices, photons):
    """Asking for bins finer than the clock would silently produce nonsense."""
    too_fine = photons["macro_dt"] * 1e6 / 10.0
    result = bursts.from_bursts_pch(None, burst_slices=slices, bin_time_us=too_fine)
    assert not result["ok"]
    assert "macro-time tick" in result["error"]


# -------------------------------------------------------------- reading routine


def test_a_wrong_container_type_still_reads_the_file(slices, photons):
    """A bad routine must not cost the read; the file identifies itself.

    ``tttrlib`` does not report an unknown container type as an error — it
    prints to stderr and returns an object with **zero photons**, which reads
    downstream as an empty measurement rather than a failed one. Callers pass
    routines derived from file extensions all over this codebase (``"SPC"`` for
    ``.spc`` being the one that bit), so the seam resolves the value instead of
    forwarding it, and falls back to detection.
    """
    detected = bursts.from_bursts_decay(
        None, burst_slices=slices, channels=[[0]]
    )
    wrong = bursts.from_bursts_decay(
        None, burst_slices=slices, channels=[[0]], reading_routine="NOT-A-FORMAT"
    )
    assert wrong["ok"], wrong
    assert (
        wrong["result"]["decays"][0]["n_photons"]
        == detected["result"]["decays"][0]["n_photons"]
    )


def test_the_spc_alias_reads_a_bh_file(photons):
    """The exact failure reported: "Container type SPC not supported".

    ``"SPC"`` is not a ``tttrlib`` container type — the real ones are
    ``SPC-130`` and ``SPC-600_*`` — but it was written by hand in a dozen call
    sites and in an extension→routine table. Every one of them produced an
    empty read on Becker & Hickl data.
    """
    spc = pathlib.Path(__file__).parents[1] / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
    if not spc.exists():
        pytest.skip(f"missing test data: {spc}")

    result = bursts.from_bursts_decay(
        None,
        burst_slices={str(spc): [[0, 4999]]},
        channels=[[0], [1]],
        reading_routine="SPC",
    )
    assert result["ok"], result
    assert sum(d["n_photons"] for d in result["result"]["decays"]) > 0


def test_an_empty_routine_means_auto_detect(slices):
    """Callers that have no routine to offer must not have to invent one."""
    for routine in (None, "", "  "):
        result = bursts.from_bursts_decay(
            None, burst_slices=slices, channels=[[0]], reading_routine=routine
        )
        assert result["ok"], routine


# ------------------------------------------------------------------ registration


def test_both_services_are_registered_on_the_wire():
    """A service nothing can call is not reachable, whatever it does."""
    import json
    from importlib import resources

    with resources.files("chisurf.server").joinpath("server_methods.json").open() as fp:
        spec = json.load(fp)
    entries = spec if isinstance(spec, list) else spec.get("methods", [])
    # Not every entry declares a handler (some are event-only).
    registered = {e["rpc"]: e.get("service") for e in entries if "rpc" in e}

    assert registered.get("tcspc.from_bursts") == "bursts.from_bursts_decay"
    assert registered.get("pch.from_bursts") == "bursts.from_bursts_pch"
    assert registered.get("pda.from_bursts") == "pda.from_bursts"
