"""A per-state decay is only defined within one detection colour.

The panel used to histogram every photon assigned to a state, donor and acceptor
together. That curve is not a decay: its shape is set by the green:red mixing
ratio, which is the FRET efficiency, so two states with *identical* lifetimes but
different efficiencies produced two different "decays". These pin the split.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core.decays import (
    colour_groups,
    decay_table,
    state_decays,
)

GROUPS = [("green", (0,)), ("red", (1,))]


def _photons(n_green, n_red, *, state, green_micro, red_micro, rng):
    """Photons of one state: green on channel 0, red on channel 1."""
    micro = np.concatenate([
        rng.poisson(green_micro, n_green), rng.poisson(red_micro, n_red)
    ])
    chan = np.concatenate([np.zeros(n_green, int), np.ones(n_red, int)])
    strm = chan.copy()
    st = np.full(n_green + n_red, state, dtype=int)
    return micro, chan, strm, st


def test_colours_are_never_summed_together():
    """The green curve must contain green photons and nothing else."""
    rng = np.random.default_rng(0)
    micro, chan, strm, st = _photons(500, 500, state=0, green_micro=40,
                                     red_micro=120, rng=rng)
    d = state_decays(micro, chan, strm, st, n_states=1, groups=GROUPS, n_bins=64)

    green = d.colour_counts[0, 0]
    red = d.colour_counts[0, 1]
    assert green.sum() == 500 and red.sum() == 500
    # Each colour peaks where its own photons are, not at a blend of the two.
    assert d.centers[np.argmax(green)] < d.centers[np.argmax(red)]
    assert abs(d.centers[np.argmax(green)] - 40) < 25
    assert abs(d.centers[np.argmax(red)] - 120) < 25


def test_two_states_with_one_lifetime_give_one_decay_shape():
    """The regression the merged histogram caused, stated directly.

    Both states emit with the same micro-time distribution per colour and differ
    only in how many red photons they produce — i.e. only in FRET efficiency. A
    per-colour decay must therefore have the same *shape* in both states; the
    old all-photons histogram did not.
    """
    rng = np.random.default_rng(1)
    lo = _photons(900, 100, state=0, green_micro=40, red_micro=120, rng=rng)
    hi = _photons(100, 900, state=1, green_micro=40, red_micro=120, rng=rng)
    micro, chan, strm, st = (np.concatenate(a) for a in zip(lo, hi))

    d = state_decays(micro, chan, strm, st, n_states=2, groups=GROUPS, n_bins=64)

    def peak(state, colour):
        return d.centers[np.argmax(d.colour_counts[state, colour])]

    assert abs(peak(0, 0) - peak(1, 0)) < 15, "the green decay must not move with E"
    assert abs(peak(0, 1) - peak(1, 1)) < 15, "nor the red one"

    # …whereas merging the colours does move it, which is why this exists.
    merged = [np.histogram(micro[st == s], bins=d.edges)[0] for s in (0, 1)]
    assert abs(d.centers[np.argmax(merged[0])] - d.centers[np.argmax(merged[1])]) > 40


def test_streams_sharing_a_detector_stay_apart():
    """Under PIE, acceptor and acceptor-excitation share routing channels.

    Merging by routing channel would pour sensitised and directly excited
    acceptor photons into one curve — the same mistake one level down.
    """
    rng = np.random.default_rng(2)
    n = 400
    micro = np.concatenate([rng.poisson(30, n), rng.poisson(150, n)])
    chan = np.ones(2 * n, dtype=int)          # one physical detector
    strm = np.concatenate([np.ones(n, int), np.full(n, 2)])  # red vs yellow
    st = np.zeros(2 * n, dtype=int)

    groups = [("green", (0,)), ("red", (1,)), ("yellow", (2,))]
    d = state_decays(micro, chan, strm, st, n_states=1, groups=groups, n_bins=64)

    assert d.channels.tolist() == [1], "both streams are on the same detector"
    assert d.colour_counts[0, 1].sum() == n
    assert d.colour_counts[0, 2].sum() == n
    assert d.centers[np.argmax(d.colour_counts[0, 1])] < d.centers[
        np.argmax(d.colour_counts[0, 2])
    ]


def test_per_detector_counts_are_kept_not_only_the_merge():
    """The saved primitive is per routing channel, so a merge can be checked."""
    rng = np.random.default_rng(3)
    n = 300
    micro = rng.poisson(50, 3 * n)
    chan = np.concatenate([np.zeros(n, int), np.full(n, 8), np.ones(n, int)])
    strm = np.concatenate([np.zeros(2 * n, int), np.ones(n, int)])  # 0,8 green; 1 red
    st = np.zeros(3 * n, dtype=int)

    d = state_decays(micro, chan, strm, st, n_states=1, groups=GROUPS, n_bins=32)
    assert d.channels.tolist() == [0, 1, 8]
    per_channel = d.channel_counts()[0]
    assert per_channel.sum(axis=1).tolist() == [n, n, n]
    # green is exactly its two detectors, summed — nothing else
    assert d.colour_counts[0, 0].sum() == 2 * n
    assert d.colour_channels["green"] == [0, 8]
    assert d.colour_channels["red"] == [1]


def test_the_written_table_is_numeric_and_per_detector():
    rng = np.random.default_rng(4)
    micro, chan, strm, st = _photons(200, 200, state=0, green_micro=40,
                                     red_micro=120, rng=rng)
    d = state_decays(micro, chan, strm, st, n_states=1, groups=GROUPS, n_bins=16,
                     micro_time_ns=0.032)
    df = decay_table(d)
    assert set(df.columns) == {
        "State", "Stream", "Channel", "Micro Time", "Micro Time (ns)", "Counts"
    }
    assert df["Counts"].sum() == 400
    assert sorted(df["Channel"].unique()) == [0, 1]
    for col in df.columns:
        assert np.issubdtype(df[col].dtype, np.number), f"{col} must be numeric"
    assert np.allclose(df["Micro Time (ns)"], df["Micro Time"] * 0.032)


def test_mismatched_photon_arrays_are_refused():
    with pytest.raises(ValueError, match="same photons"):
        state_decays([1, 2, 3], [0, 0], [0, 0], [0, 0], n_states=1, groups=GROUPS)


def test_colour_groups_names_come_from_the_detectors():
    class _Ana:
        donor_streams = (0,)
        acceptor_streams = (1,)
        aex_streams = (2,)

    class _Stream:
        def __init__(self, name):
            self.name = name

    class _Settings:
        streams = [_Stream("gg"), _Stream("rr"), _Stream("yy")]

    assert colour_groups(_Ana(), _Settings()) == [
        ("gg", (0,)), ("rr", (1,)), ("yy", (2,))
    ]

    class _NoAex(_Ana):
        aex_streams = ()

    assert colour_groups(_NoAex(), _Settings()) == [("gg", (0,)), ("rr", (1,))]
