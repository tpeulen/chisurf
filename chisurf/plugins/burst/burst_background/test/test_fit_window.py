"""The seeded fit window, and what happens when it misses a detector.

One window is shared by every detector -- it is one band the user drags, and a
background rate is a property of the measurement rather than of a channel. That
makes *where it is seeded* load-bearing in a way it is not for a per-detector
rule: a seed outside one detector's data gives that detector a background of
exactly 0.0 kHz, which is not an error, does not look like one, and travels
into every corrected FRET efficiency downstream.
"""

from __future__ import annotations

import numpy as np
import pytest


def _model(streams: dict[str, np.ndarray]):
    """A view model holding *streams* as if they had just been read."""
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    model = BackgroundViewModel(show_channel_definition=False, show_files=False)
    model.files = ["/synthetic.ptu"]
    model.channels_provider = lambda: {name: {"chs": [0]} for name in streams}
    model._interphoton = {"/synthetic.ptu": streams}
    model._seed_fit_window()
    model.refit()
    return model


def _exponential(rate_khz: float, n: int, seed: int) -> np.ndarray:
    """*n* inter-photon times (ms) from a Poisson stream of the given rate."""
    return np.random.default_rng(seed).exponential(1.0 / rate_khz, n)


def test_the_window_lands_inside_every_detector():
    """The seed must give the *shortest* stream bins to fit, not just the longest.

    The regression this pins: the window was seeded at a fraction of the longest
    inter-photon time found in *any* detector. That time is the single largest
    gap in the file, so on real ALEX data (green 5.0 ms, red 8.8, yellow 10.9)
    the window opened at 8.7 ms -- past the end of green's data entirely.
    """
    streams = {
        "green": _exponential(4.0, 60_000, 1),
        "red": _exponential(2.0, 60_000, 2),
        "yellow": _exponential(8.0, 60_000, 3),
    }
    model = _model(streams)

    low, high = model.fit_from_ms, model.fit_to_ms
    assert high > low > 0.0
    for name, dt in streams.items():
        assert ((dt >= low) & (dt <= high)).sum() > 0, f"{name} has no data in the window"

    for diags in model.diagnostics.values():
        for name, diag in diags.items():
            assert int(np.asarray(diag.tail_mask).sum()) >= model.MIN_TAIL_BINS, name
            assert diag.rate_khz > 0.0, f"{name} was reported as zero background"


def test_the_slider_still_spans_the_whole_measurement():
    """Seeding narrow must not stop the user dragging out to the far tail."""
    streams = {"green": _exponential(4.0, 40_000, 4), "red": _exponential(1.0, 40_000, 5)}
    model = _model(streams)
    assert model.max_dt_ms == pytest.approx(max(float(s.max()) for s in streams.values()))
    assert model.fit_to_ms <= model.max_dt_ms


def test_a_window_the_user_placed_is_not_moved_by_a_re_estimate():
    """Re-reading with more files must not silently re-seed a chosen window."""
    streams = {"green": _exponential(4.0, 40_000, 6)}
    model = _model(streams)
    model.fit_from_ms, model.fit_to_ms = 0.4, 1.2
    model._seed_fit_window()
    assert (model.fit_from_ms, model.fit_to_ms) == (0.4, 1.2)


def test_a_starved_detector_is_named_rather_than_reported_as_zero():
    """A window with no bins for a detector must say so, not return 0.0 kHz.

    Zero background is not a measurement, it is a missing one -- and it is the
    one value that passes through the corrections without complaint.
    """
    streams = {"green": _exponential(4.0, 40_000, 7)}
    model = _model(streams)
    # Push the window past the end of the data, as the old seed effectively did.
    model.fit_from_ms = float(streams["green"].max()) * 1.5
    model.fit_to_ms = model.fit_from_ms + 1.0
    model.refit()

    assert "green" in model._underdetermined()
    assert "green" in model.status and "⚠" in model.status
