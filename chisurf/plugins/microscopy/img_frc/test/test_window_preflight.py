"""FRC runs the shared excitation-window pre-flight on the detector gates a photon stream is binned through.

The measurement is a confocal scan of the FRC demo object whose photons carry the micro times of
the simulated PIE demo of Excitation Windows (32 ps, 3125 channels, pulses at 2 and 52 ns), donor
on routing 0 and acceptor on routing 5. Gates made for another instrument give the warning in the
result, the CLI and the window (which offers the detected windows); gates that hold the pulses give
none. The result's check is the imaging tools' gate check (``imaging_common.windows.gate_check``,
whose ungated, image-file and donor-only cases ``imaging_common/test`` covers).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.microscopy.img_frc import core  # noqa: E402

#: The donor and acceptor routing channels of the scan (1, 2 and 4 are the scanner's markers).
DONOR, ACCEPTOR = 0, 5
WRONG = {
    "green": {"chs": [DONOR], "micro_time_ranges": [[2048, 4095]]},
    "red": {"chs": [ACCEPTOR], "micro_time_ranges": [[0, 2047]]},
}
MATCHING = {
    "green": {"chs": [DONOR], "micro_time_ranges": [[0, 1612]]},
    "red": {"chs": [ACCEPTOR], "micro_time_ranges": []},
}


def pie_scan(path: Path, *, donor_only: bool = False) -> Path:
    """Write a 4-frame 64x64 confocal PIE scan of the FRC demo object to *path* (PTU)."""
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.microscopy import demo_stack
    from chisurf.plugins.microscopy.img_pixel_nb.demo import counts_to_tttr

    counts = np.rint(demo_stack.frc_stack(n_frames=4, size=64) * 4).clip(0).astype(np.int64)
    scan = counts_to_tttr(counts, 10e-6)
    macro = np.asarray(scan.macro_times)
    routing = np.asarray(scan.routing_channels).astype(np.int8)
    event = np.asarray(scan.event_types).astype(np.int8)
    micro = np.asarray(scan.micro_times).astype(np.uint16)
    photons = event == 0
    _, d_micro, d_routing = d.photon_stream(n_photons=4 * int(photons.sum()))
    t_ns = d_micro.astype(float) * d.RESOLUTION_S * 1e9
    pool = ~((d_routing == 1) & (t_ns > 51.0)) if donor_only else np.ones(d_micro.size, bool)
    d_micro, d_routing = d_micro[pool][: photons.sum()], d_routing[pool][: photons.sum()]
    micro[photons] = d_micro
    routing[photons] = np.where(d_routing == 1, ACCEPTOR, DONOR)
    # One macro tick is one laser period (the sync), as a TCSPC scan records it.
    ticks = int(round(float(scan.header.macro_time_resolution) / d.MACRO_S))
    out = tttrlib.TTTR(macro * np.uint64(ticks), micro, routing, event)
    header = out.header
    header.set_macro_time_resolution(d.MACRO_S)
    header.set_micro_time_resolution(d.RESOLUTION_S)
    for name in ("ImgHdr_LineStart", "ImgHdr_LineStop", "ImgHdr_Frame", "ImgHdr_PixX",
                 "ImgHdr_PixY", "ImgHdr_BiDirect"):
        header.set_tag(name, int(scan.header.tag(name)["value"]), 0x10000008)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert out.write(str(path), "PTU"), path
    return path


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    return pie_scan(tmp_path_factory.mktemp("scan") / "pie_scan.ptu")


def test_the_scan_is_an_image_with_two_detectors(scan):
    stack = core.load_image_stack(str(scan), windows=MATCHING)
    assert stack.kind == "tttr" and stack.channel_names == ["green", "red"]
    assert stack.n_frames >= 2 and stack.image(0).sum() > 0


def test_gates_of_another_instrument_are_reported_in_the_result(scan):
    result = core.analyse(str(scan), windows=WRONG)
    assert len(result.warnings) == 1 and "do not match the data" in result.warnings[0]
    assert result.to_dict()["warnings"] == result.warnings


def test_gates_that_hold_the_pulses_say_nothing(scan):
    assert core.analyse(str(scan), windows=MATCHING).warnings == []


def test_the_cli_prints_the_warning(scan):
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_frc.cli.main import cli

    out = CliRunner().invoke(cli, [str(scan), "--windows", json.dumps(WRONG), "--json"])
    assert "do not match the data" in json.loads(out.stdout)["warnings"][0]
    out = CliRunner().invoke(cli, [str(scan), "--windows", json.dumps(WRONG)])
    assert out.output.startswith("warning: ") and "do not match the data" in out.output


def test_the_window_offers_the_detected_windows_and_takes_them(scan):
    from chisurf.plugins.microscopy.img_frc.gui.model import FrcModel

    model = FrcModel()
    model.apply_setup_settings({"detectors": WRONG})
    model.open_path(str(scan))
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    assert "do not match" in model.status_line
    assert model.use_detected_windows()
    green = model.detectors["green"]["micro_time_ranges"]
    assert any(lo <= 2e-9 / 32e-12 < hi for lo, hi in green), green
    assert not model.windows_check_offer
