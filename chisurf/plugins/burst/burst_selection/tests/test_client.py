"""``BurstSelectionClient``: what it forwards to the backend and how it reads a file for the diagnostics.

(Two tests of the retired Qt tool's test module that only ever touched the client, not the widget.)
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from chisurf.plugins.burst.burst_selection.api.models import AnalysisSettings
from chisurf.plugins.burst.burst_selection.gui.client import BurstSelectionClient


def test_client_analyze_files_passes_detector_setup_context() -> None:
    """Detector setup context must be forwarded to the RPC analyze method."""

    class FakeClient:
        """Minimal client stub that records RPC calls."""

        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def call(self, method: str, params: dict[str, object]) -> dict[str, object]:
            self.calls.append((method, params))
            return {"ok": True, "result": {"dataframes": {}}}

    fake = FakeClient()
    client = BurstSelectionClient(fake)
    result = client.analyze_files(
        [Path("example.spc")],
        settings={"photon_filter": {"channels": [0, 8]}},
        windows={"prompt": [0, 2048]},
        detectors={"green": {"chs": [0, 8]}},
        filetype="SPC-130",
        output_dir=Path("burstwise_All 0.2000#60") / "bi4_bur",
        legacy_output=True,
        legacy_output_folder_name="burstwise_All 0.2000#60",
        selected_setup="Test",
        legacy_parameters={"decay_coarse": 8},
        mmfdb={
            "enabled": True,
            "sample_id": "sample_1",
            "source_artifact_ids": {"example.spc": "artifact_1"},
        },
    )
    assert result == {"dataframes": {}}
    assert fake.calls[0][0] == "burst_selection.jobs.analyze_files"
    assert fake.calls[0][1]["filetype"] == "SPC-130"
    assert fake.calls[0][1]["windows"] == {"prompt": [0, 2048]}
    assert fake.calls[0][1]["detectors"] == {"green": {"chs": [0, 8]}}
    assert fake.calls[0][1]["output_dir"] == "burstwise_All 0.2000#60/bi4_bur"
    assert fake.calls[0][1]["legacy_output"] is True
    assert fake.calls[0][1]["legacy_output_folder_name"] == "burstwise_All 0.2000#60"
    assert fake.calls[0][1]["selected_setup"] == "Test"
    assert fake.calls[0][1]["legacy_parameters"] == {"decay_coarse": 8}
    assert fake.calls[0][1]["mmfdb"] == {
        "enabled": True,
        "sample_id": "sample_1",
        "source_artifact_ids": {"example.spc": "artifact_1"},
    }


def test_client_load_diagnostics_accepts_unset_microtime_ranges() -> None:
    """Diagnostic loading should treat unset microtime ranges as unrestricted."""
    path = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna" / "m000.spc"
    settings = AnalysisSettings()
    settings.photon_filter.channels = []
    settings.photon_filter.microtime_ranges = None

    diag = BurstSelectionClient().load_diagnostics(path, settings=asdict(settings))

    assert set(diag) >= {"tttr", "selected", "start_stop", "settings"}
    assert diag["settings"].photon_filter.microtime_ranges == []
    assert len(diag["selected"]) == len(diag["tttr"])
