"""The Inspected burst tab is drawn every frame; its histogram is made once per burst.

Slicing the photon stream and converting the burst table's columns each frame was part of what
made every frame slow after a fit of tens of thousands of bursts."""

from __future__ import annotations

import numpy as np

from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel


def test_the_inspected_histogram_is_made_once_per_burst_and_window(monkeypatch):
    model = MleViewModel()
    session = model.session
    session.df_bursts = {"First Photon": np.arange(5.0), "Last Photon": np.arange(5.0) + 1,
                         "First File": np.array(["a.ptu"] * 5, dtype=object)}
    session.tttrs = {"a": object()}
    made = []
    monkeypatch.setattr(session, "inspect_burst",
                        lambda idx: made.append(idx) or {"G|G": np.full(4, float(idx))})
    for _ in range(3):  # three frames, one burst
        assert model.inspected_burst()["G|G"][0] == 0.0
    assert made == [0]
    model.nav_burst = 3
    assert model.inspected_burst()["G|G"][0] == 3.0 and made == [0, 3]
    det = next(iter(session.detectors))
    session.settings_of(det).micro_time_binning += 1  # another binning: made again
    model.inspected_burst()
    assert made == [0, 3, 3]
    session.df_bursts = dict(session.df_bursts)  # a new burst table: made again
    model.inspected_burst()
    assert made == [0, 3, 3, 3]
    assert model.inspected_file_name() == "a.ptu"
