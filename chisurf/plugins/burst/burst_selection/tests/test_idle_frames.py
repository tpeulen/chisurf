"""An idle Burst Selection frame touches no burst arrays.

The step drew its count-rate trace, burst spans and histogram every frame, and each time copied
every macro time of the file (the spans, ~70 ms on 12 M photons) and the burst table two or three
times (the histogram of the visible window, ~120 ms on 21 808 bursts): ~300 ms a frame after a
search. They are memoised per table and window; a new table or window derives them again.
"""

from __future__ import annotations

import time

from chisurf.plugins.emtk_test_input import Driver

from .test_search_ahead import step  # noqa: F401  (fixture)
from .test_emtk_native_app import files  # noqa: F401  (fixture)


def _until(drv, predicate, timeout=120.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        drv.draw(1)
        time.sleep(0.05)
    assert predicate(), "timed out"


def test_idle_frames_derive_nothing_and_a_new_window_derives_again(step, monkeypatch):  # noqa: F811
    from chisurf.plugins.burst.burst_selection.gui import diagnostics as diag_mod
    from chisurf.plugins.burst.burst_selection.gui import model as model_mod

    m = step.model
    drv = Driver(step, (1200, 800))
    step.prefetch()  # the search ahead: its bursts on show, as after a search
    _until(drv, lambda: m.ahead is not None and step.speculation.done
           and (m.diagnostic or {}).get("tttr") is not None and not step.diagnostics_running)
    drv.draw(10)
    starts, _stops = m.burst_spans()
    assert starts.size > 0, "no burst spans in the visible window"

    calls = {"hist": 0, "window": 0, "spans": 0}
    hist, window = diag_mod.histogram_data_from_frame, diag_mod.rows_in_window
    spans = model_mod.BurstSelectionModel._burst_spans

    def count(name, fn):
        def wrapped(*args, **kwargs):
            calls[name] += 1
            return fn(*args, **kwargs)
        return wrapped

    monkeypatch.setattr(diag_mod, "histogram_data_from_frame", count("hist", hist))
    monkeypatch.setattr(diag_mod, "rows_in_window", count("window", window))
    monkeypatch.setattr(model_mod.BurstSelectionModel, "_burst_spans", count("spans", spans))
    drv.draw(5)
    assert calls == {"hist": 0, "window": 0, "spans": 0}, calls

    before = m.window_feature_data(m.hist_feature)
    m.window_start_s = float(m.window_start_s) + 0.5  # another window: derived again, once
    after = m.window_feature_data(m.hist_feature)
    assert calls["window"] == 1 and m.window_feature_data(m.hist_feature) is after
    assert after is not before
