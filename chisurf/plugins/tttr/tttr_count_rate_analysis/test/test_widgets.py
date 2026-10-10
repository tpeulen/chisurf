import pathlib

import pytest


def test_view_model_compute_and_export(tmp_path):
    pytest.importorskip("tttrlib")
    import tttrlib

    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.view_model import (
        CountRateViewModel,
    )

    ptu = pathlib.Path(__file__).resolve().parents[5] / "test" / "data" / "clsm" / "Leica_SP5.ptu"
    if not ptu.exists():
        pytest.skip("sample PTU not available")

    routing = list(tttrlib.TTTR(str(ptu)).get_used_routing_channels())
    m = CountRateViewModel()
    m.add_files([str(ptu)])
    # Inject a minimal single-channel definition (all detectors, no ranges).
    m.channels_provider = lambda: {
        "all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]
    }
    m.compute()
    rows = m.results_rows()
    assert rows and rows[0]["photons"] > 0
    series = m.count_rate_series()
    assert series and len(series[0]["x"]) == 1

    out = tmp_path / "cr.txt"
    m.save_table(str(out))
    assert out.exists() and "Channel" in out.read_text()
