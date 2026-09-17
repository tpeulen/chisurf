"""ebFRET file formats, checked against files written by ebFRET itself.

Two kinds of reference, both recorded once and read here without MATLAB or
Octave:

* ``tests/data/io/*_octave.*`` -- ebFRET's own ``+ebfret/+io`` functions run
  under GNU Octave on small inputs (``tests/octave/make_io_fixtures.m``);
* ``tests/data/io/matlab_*`` -- the head of the exports MATLAB wrote for the
  ``simulated-K04-N350`` dataset that ships with ebFRET.

When the full ebFRET checkout is present the last tests repeat the comparison
on the complete dataset.
"""

from __future__ import annotations

import gzip
import json
import pathlib

import numpy as np
import pytest
import scipy.io as sio

from chisurf.plugins.burst.burst_ebfret import io
from chisurf.plugins.burst.burst_ebfret.core.model import (
    Analysis,
    Expect,
    HmmParams,
    Series,
    Viterbi,
)

DATA = pathlib.Path(__file__).parent / "data" / "io"
CHECKOUT = pathlib.Path(__file__).resolve().parents[5] / "junk" / "ebFRET" / "datasets"
ALL_CHANNELS = dict(donor=True, acceptor=True, fret=True, viterbi_state=True, viterbi_mean=True)


def _octave(name: str) -> dict:
    """An Octave-recorded JSON fixture."""
    return json.loads((DATA / name).read_text())


# --------------------------------------------------------------------------- #
# labels and raw traces
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, text",
    [
        (12.0, "12"),
        (7, "7"),
        (176.03321, "1.760332e+02"),
        (-3.5, "-3.500000e+00"),
        (1e10, "10000000000"),
        (float("nan"), "NaN"),
    ],
)
def test_labels_are_formatted_as_matlab_sprintf_d(value, text):
    """MATLAB switches ``%d`` to ``%e`` for a non-integer; sessions carry that."""
    assert io.format_label(value) == text


@pytest.mark.parametrize("stem", ["raw_unstacked", "raw_stacked_gap"])
def test_load_raw_matches_ebfret(stem):
    """Both layouts, label row consumed, the gap in the stacked ids stripped."""
    donors, acceptors, labels = io.load_raw(str(DATA / f"{stem}.dat"))
    ref = _octave(f"{stem}_octave.json")
    assert len(donors) == len(ref["donors"])
    for got, want in zip(donors, ref["donors"]):
        np.testing.assert_array_equal(got, want)
    for got, want in zip(acceptors, ref["acceptors"]):
        np.testing.assert_array_equal(got, want)
    np.testing.assert_array_equal(labels, ref["labels"])


def test_load_raw_without_labels_numbers_the_traces():
    donors, _, labels = io.load_raw(str(DATA / "raw_unstacked.dat"), has_labels=False)
    np.testing.assert_array_equal(labels, [1, 2])
    assert donors[0].size == 5


def test_load_sf_tracer_matches_ebfret():
    donors, acceptors = io.load_sf_tracer(str(DATA / "sf_tracer.tsv"))
    ref = _octave("sf_tracer_octave.json")
    for got, want in zip(donors + acceptors, ref["donors"] + ref["acceptors"]):
        np.testing.assert_array_equal(got, want)


def test_series_from_raw_is_what_load_data_builds():
    donors, acceptors, labels = io.load_raw(str(DATA / "raw_stacked_gap.dat"))
    series = io.series_from_raw("/x/raw_stacked_gap.dat", donors, acceptors, labels, "group 2")
    assert [s.label for s in series] == ["1.760332e+02", "42"]
    s = series[1]
    assert (s.file, s.group, s.crop_min, s.crop_max, s.exclude) == (
        "raw_stacked_gap",
        "group 2",
        1,
        3,
        False,
    )
    np.testing.assert_array_equal(s.time, [1, 2, 3])
    np.testing.assert_array_equal(s.signal, (s.acceptor + io.EPS) / (s.acceptor + s.donor + io.EPS))


def test_file_base_strips_only_the_last_extension():
    assert io.file_base("/a/b/data.json.gz") == "data.json"


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
def test_an_ebfret_session_loads():
    series, analysis, controls = io.load_session(str(DATA / "session_octave.mat"))
    assert [s.group for s in series] == ["group 1", "group 1", "group 2"]
    assert (series[1].crop_min, series[1].crop_max) == (2, 3)
    assert series[2].exclude and not series[0].exclude
    assert sorted(analysis) == [2]
    a = analysis[2]
    np.testing.assert_array_equal(a.prior.A, [[10, 1], [2, 20]])
    np.testing.assert_array_equal(a.posterior[0].mu, [0.15, 0.75])
    assert a.posterior[2] is None and a.expect[2] is None and a.viterbi[2] is None
    np.testing.assert_array_equal(a.expect[0].zz, [[2, 0.5], [0, 0.5]])
    np.testing.assert_array_equal(a.viterbi[0].state, [1, 1, 2, 2])
    np.testing.assert_array_equal(a.lowerbound, [1.5, -2.25, 0])
    np.testing.assert_array_equal(a.restart, [0, 2, 0])
    # all_restarts comes after restarts and wins; init_restarts is ignored
    assert controls.restarts == 4
    assert (controls.show_prior, controls.run_all, controls.scale_plots) == (False, False, False)
    assert (controls.series_value, controls.ensemble_max, controls.crop_margin) == (2, 3, 7)
    assert controls.clip_min == pytest.approx(-0.2)


def _assert_same_session(first, second):
    series_a, analysis_a, controls_a = first
    series_b, analysis_b, controls_b = second
    assert controls_a == controls_b
    assert len(series_a) == len(series_b)
    for s, t in zip(series_a, series_b):
        for name in ("file", "label", "group", "crop_min", "crop_max", "exclude"):
            assert getattr(s, name) == getattr(t, name)
        for name in ("time", "signal", "donor", "acceptor"):
            np.testing.assert_array_equal(getattr(s, name), getattr(t, name))
    assert sorted(analysis_a) == sorted(analysis_b)
    for k in analysis_a:
        a, b = analysis_a[k], analysis_b[k]
        assert a.states == b.states
        np.testing.assert_array_equal(a.lowerbound, b.lowerbound)
        np.testing.assert_array_equal(a.restart, b.restart)
        for p, q in zip([a.prior] + a.posterior, [b.prior] + b.posterior):
            assert (p is None) == (q is None)
            if p is not None:
                for name in ("mu", "beta", "W", "nu", "A", "pi"):
                    np.testing.assert_array_equal(getattr(p, name), getattr(q, name))
        for p, q in zip(a.viterbi, b.viterbi):
            assert (p is None) == (q is None)
            if p is not None:
                np.testing.assert_array_equal(p.state, q.state)
                np.testing.assert_array_equal(p.mean, q.mean)


def test_a_saved_session_reads_back_and_has_ebfrets_layout(tmp_path):
    loaded = io.load_session(str(DATA / "session_octave.mat"))
    path = tmp_path / "session.mat"
    io.save_session(str(path), *loaded)
    _assert_same_session(loaded, io.load_session(str(path)))

    raw = sio.loadmat(str(path))
    assert {"controls", "series", "analysis", "plots"} <= set(raw)
    assert raw["series"].dtype.names == (
        "file",
        "label",
        "group",
        "time",
        "signal",
        "donor",
        "acceptor",
        "crop",
        "exclude",
    )
    assert raw["analysis"].shape == (1, 2)
    assert raw["analysis"][0, 0]["dim"].size == 0  # no 1-state model
    assert raw["analysis"][0, 1]["posterior"].shape == (1, 3)
    assert raw["series"][0, 0]["signal"].shape == (4, 1)  # column vectors


# --------------------------------------------------------------------------- #
# analysis summary
# --------------------------------------------------------------------------- #
def test_write_report_is_byte_identical_to_ebfret(tmp_path):
    report = [
        {
            "Series": {"Label": "all", "Number": 3, "Length": {"Mean": 12.5, "Std": 0.25}},
            "Statistics": {
                "Label": ["all", ""],
                "Num_States": ["2", ""],
                "State": np.array([1, 2]),
                "Occupancy": {"Fraction": np.array([[0.25], [0.75]])},
            },
            "Parameters": {"Transition_Matrix": {"Mean": np.array([[0.9, 0.1], [0.2, 0.8]])}},
        },
        {
            "Series": {
                "Label": "group 1",
                "Number": 1,
                "Length": {"Mean": -1.5e-7, "Std": 1234567},
            },
            "Statistics": {
                "Label": ["group 1", ""],
                "Num_States": ["2", ""],
                "State": np.array([1, 2]),
                "Occupancy": {"Fraction": np.array([0.5, 0.5])},
            },
            "Parameters": {"Transition_Matrix": {"Mean": np.array([[0.7, 0.3], [0.4, 0.6]])}},
        },
    ]
    path = tmp_path / "report.csv"
    io.write_report(str(path), report)
    assert path.read_bytes() == (DATA / "report_octave.csv").read_bytes()


# --------------------------------------------------------------------------- #
# trace export
# --------------------------------------------------------------------------- #
def _series_from_trace_table(table: np.ndarray):
    """Rebuild series and Viterbi paths from a MATLAB trace export."""
    series, paths = [], []
    for n in np.unique(table[:, 0]):
        rows = table[table[:, 0] == n]
        t = rows.shape[0]
        series.append(
            Series(
                file="f",
                label=str(int(n)),
                group="group 1",
                time=np.arange(1.0, t + 1),
                signal=rows[:, 3],
                donor=rows[:, 1],
                acceptor=rows[:, 2],
                crop_min=1,
                crop_max=t,
            )
        )
        paths.append(Viterbi(state=rows[:, 4].astype(int), mean=rows[:, 5]))
    return series, Analysis(states=4, viterbi=paths)


def test_export_traces_dat_is_byte_identical_to_matlab(tmp_path):
    reference = DATA / "matlab_traces_head.dat"
    series, analysis = _series_from_trace_table(np.loadtxt(reference))
    path = tmp_path / "traces.dat"
    io.export_traces(str(path), series, analysis, ALL_CHANNELS)
    assert path.read_bytes() == reference.read_bytes()


def test_export_traces_selects_channels_and_skips_excluded(tmp_path):
    series, analysis = _series_from_trace_table(np.loadtxt(DATA / "matlab_traces_head.dat"))
    series[1].exclude = True
    series[0].crop_min, series[0].crop_max = 3, 5
    analysis.viterbi[0] = Viterbi(state=np.array([1, 2, 3]), mean=np.array([0.1, 0.2, 0.3]))
    table = io.export_traces(
        str(tmp_path / "t.mat"), series, analysis, dict(fret=True, viterbi_state=True)
    )
    assert table.shape == (3 + 45, 3)
    np.testing.assert_array_equal(np.unique(table[:, 0]), [1, 3])
    np.testing.assert_array_equal(table[:3, 2], [1, 2, 3])
    np.testing.assert_array_equal(sio.loadmat(str(tmp_path / "t.mat"))["traces"], table)


# --------------------------------------------------------------------------- #
# SMD
# --------------------------------------------------------------------------- #
def _session_from_smd(smd: dict):
    """Rebuild the series and analysis an SMD export was written from."""
    series, analysis = [], Analysis(states=4, lowerbound=np.zeros(0))
    attr = smd["attr"]
    analysis.prior = HmmParams(
        mu=attr["prior_mu"],
        beta=attr["prior_beta"],
        W=attr["prior_W"],
        nu=attr["prior_nu"],
        A=attr["prior_A"],
        pi=attr["prior_pi"],
    )
    lowerbound, restart = [], []
    for trace in smd["data"]:
        a, v = trace["attr"], trace["values"]
        series.append(
            Series(
                file=a["file"],
                label=a["label"],
                group=a["group"],
                time=trace["index"],
                signal=v[:, 2],
                donor=v[:, 0],
                acceptor=v[:, 1],
                crop_min=int(a["crop_min"]),
                crop_max=int(a["crop_max"]),
            )
        )
        analysis.viterbi.append(Viterbi(state=v[:, 3].astype(int), mean=v[:, 4]))
        analysis.expect.append(
            Expect(
                z=a["suff_stat_z"],
                z1=a["suff_stat_z1"],
                zz=a["suff_stat_zz"],
                x=a["suff_stat_x"],
                xx=a["suff_stat_xx"],
            )
        )
        lowerbound.append(a["lowerbound"])
        restart.append(a["restart"])
    analysis.lowerbound = np.asarray(lowerbound)
    analysis.restart = np.asarray(restart, dtype=int)
    return series, analysis


def _without_ids(text: str) -> list:
    """JSON lines, ids and the format version blanked out."""
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith('"id":') or stripped.startswith('"type":'):
            line = line.split(":")[0]
        out.append(line)
    return out


def test_smd_json_is_laid_out_as_ebfret_writes_it(tmp_path):
    reference = DATA / "matlab_smd_head.json.gz"
    smd = io.load_smd(str(reference))
    series, analysis = _session_from_smd(smd)
    path = tmp_path / "out.json"
    written = io.write_smd(str(path), series, analysis)
    assert written["type"] == "ebFRET_v_1_1_analysis"
    with gzip.open(reference, "rt") as handle:
        expected = handle.read()
    assert _without_ids(path.read_text()) == _without_ids(expected)


@pytest.mark.parametrize("name", ["out.mat", "out.json.gz"])
def test_smd_round_trips(tmp_path, name):
    series, analysis = _session_from_smd(io.load_smd(str(DATA / "matlab_smd_head.json.gz")))
    path = tmp_path / name
    written = io.write_smd(str(path), series, analysis)
    back = io.load_smd(str(path))
    assert back["columns"] == list(io._SMD_COLUMNS)
    assert back["id"] == written["id"] and len(back["id"]) == 32
    assert "num_states" not in back["attr"]  # the reference's typo, kept
    for got, want in zip(back["data"], written["data"]):
        assert got["id"] == want["id"]
        np.testing.assert_allclose(got["values"], want["values"], rtol=1e-9)
        np.testing.assert_array_equal(got["index"], np.ravel(want["index"]))
        # posterior_* holds the prior, as the reference writes it
        np.testing.assert_allclose(got["attr"]["posterior_mu"], analysis.prior.mu, rtol=1e-9)


def test_smd_series_use_the_assigned_channels():
    smd = io.load_smd(str(DATA / "matlab_smd_head.json.gz"))
    as_pair = io.series_from_smd("/d/set.json.gz", smd, dict(donor=1, acceptor=2), "group 1")
    as_fret = io.series_from_smd("/d/set.json.gz", smd, dict(fret=3), "group 2")
    assert as_pair[0].file == "set.json" and as_pair[0].label == smd["data"][0]["id"]
    np.testing.assert_allclose(as_pair[0].signal, smd["data"][0]["values"][:, 2], atol=1e-9)
    np.testing.assert_array_equal(as_fret[1].signal, smd["data"][1]["values"][:, 2])
    assert not as_fret[1].donor.any() and as_fret[1].group == "group 2"


def test_smd_viterbi_path_of_a_series_cropped_at_the_start(tmp_path):
    """The stored path covers the crop; it is written whole, not re-cropped."""
    series, analysis = _session_from_smd(io.load_smd(str(DATA / "matlab_smd_head.json.gz")))
    s = series[1]
    s.crop_min, s.crop_max = 11, 20
    analysis.viterbi[1] = Viterbi(state=np.arange(1, 11), mean=np.linspace(0, 1, 10))
    smd = io.build_smd(series, analysis)
    np.testing.assert_array_equal(smd["data"][1]["values"][:, 3], np.arange(1, 11))
    np.testing.assert_array_equal(smd["data"][1]["values"][:, 0], s.donor[10:20])


def test_savejson_follows_jsonlab():
    text = io.savejson(
        {
            "a": 1.5,
            "row": np.array([1, 2]),
            "col": np.array([[1.0], [np.nan]]),
            "none": np.zeros((0, 0)),
            "s": "x",
            "c": ["p", "q"],
            "st": {"k": 2},
        }
    )
    assert text == (
        '{\n\t"a": 1.5,\n\t"row": [1,2],\n\t"col": [\n\t\t[1],\n\t\t["_NaN_"]\n\t],\n'
        '\t"none": null,\n\t"s": "x",\n\t"c": [\n\t\t"p",\n\t\t"q"\n\t],\n'
        '\t"st": {\n\t\t"k": 2\n\t}\n}\n'
    )


def test_smd_create_splits_a_flat_table_by_id():
    table = np.array([[1, 10, 0.1], [1, 11, 0.2], [2, 12, 0.3]])
    smd = io.smd_create(table, ["id", "index", "fret"])
    assert [t["id"] for t in smd["data"]] == ["1", "2"]
    assert smd["type"] == "id-index-fret" and smd["columns"] == ["fret"]
    np.testing.assert_array_equal(smd["data"][0]["index"], [10, 11])


# --------------------------------------------------------------------------- #
# the complete simulated dataset, when the ebFRET checkout is present
# --------------------------------------------------------------------------- #
needs_checkout = pytest.mark.skipif(
    not (CHECKOUT / "simulated-K04-N350-ebfret-session.mat").exists(),
    reason="ebFRET reference checkout not present",
)


@needs_checkout
def test_full_dataset_raw_load_equals_ebfrets_session():
    session_series, analysis, _ = io.load_session(
        str(CHECKOUT / "simulated-K04-N350-ebfret-session.mat")
    )
    raw = str(CHECKOUT / "simulated-K04-N350-raw-stacked.dat")
    series = io.series_from_raw(raw, *io.load_raw(raw), "group 1")
    assert len(series) == len(session_series) == 350
    for s, t in zip(series, session_series):
        assert (s.file, s.label, s.group) == (t.file, t.label, t.group)
        np.testing.assert_array_equal(s.signal, t.signal)


@needs_checkout
def test_full_dataset_exports_equal_matlabs(tmp_path):
    series, analysis, _ = io.load_session(str(CHECKOUT / "simulated-K04-N350-ebfret-session.mat"))
    io.export_traces(str(tmp_path / "t.dat"), series, analysis[4], ALL_CHANNELS)
    assert (tmp_path / "t.dat").read_bytes() == (
        CHECKOUT / "simulated-K04-N350-traces-K04.dat"
    ).read_bytes()
    io.write_smd(str(tmp_path / "s.json.gz"), series, analysis[4])
    with gzip.open(CHECKOUT / "simulated-K04-N350-smd-K04.json.gz", "rt") as handle:
        expected = handle.read()
    with gzip.open(tmp_path / "s.json.gz", "rt") as handle:
        assert _without_ids(handle.read()) == _without_ids(expected)
