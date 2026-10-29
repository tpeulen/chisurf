"""BVA runs the shared excitation-window pre-flight on the donor and acceptor micro-time ranges.

On the simulated PIE demo (pulses at 2 and 52 ns, routing 0 donor / 1 acceptor): ranges of another
instrument warn in the RPC result, on the CLI's stderr and in the window, which offers the
detected gates and takes them into the ranges; ranges that hold the pulses say nothing; a
donor-only measurement gives no false warning. BVA's ranges are inclusive, the shared check's
gates half-open: the conversion is tested on its own.
"""

from __future__ import annotations

import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_bva.core import windows  # noqa: E402
from chisurf.plugins.burst.burst_bva.tests import pie_folder  # noqa: E402
from chisurf.plugins.burst.burst_bva.tests.pie_folder import (  # noqa: E402
    DELAYED,
    PROMPT,
    WRONG_DONOR,
)

FULL = (0, 32768)


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    return pie_folder.build(tmp_path_factory.mktemp("pie"))


@pytest.fixture(scope="module")
def demo(folder):
    return {"excitation_windows_demo.ptu": tttrlib.TTTR(str(next(folder.parent.glob("*.ptu"))))}


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    return {"donor_only.ptu": tttrlib.TTTR(str(pie_folder.donor_only(tmp_path_factory.mktemp("d"))))}


def _pair(donor, acceptor):
    return windows.stream_detectors({"donor": ([0], [donor]), "acceptor": ([1], [acceptor])})


def test_inclusive_ranges_are_checked_as_the_channels_they_keep():
    assert windows.to_setup_gates([(50, 1612)]) == [[50, 1613]]
    assert windows.from_setup_gates([[50, 1613]]) == [(50, 1612)]
    assert windows.from_setup_gates(windows.to_setup_gates([PROMPT, DELAYED])) == [PROMPT, DELAYED]


def test_ranges_of_another_instrument_warn(demo):
    lines = windows.window_warnings(demo, _pair(WRONG_DONOR, FULL))
    assert len(lines) == 1 and "do not match the data" in lines[0], lines
    assert "donor" in lines[0] and "1613" in lines[0]  # the detected windows are named


def test_ranges_that_hold_the_pulses_say_nothing(demo):
    assert windows.window_warnings(demo, _pair(FULL, FULL)) == []
    # ALEX-2CDE streams: every photon after donor excitation, the acceptor's after acceptor
    # excitation -- one routing channel split by micro time
    alex = windows.stream_detectors({"dex": ([0, 1], [PROMPT]), "aex": ([1], [DELAYED])})
    assert windows.window_warnings(demo, alex) == []


def test_the_pie_split_of_the_setup_is_understood(demo):
    """FRET pair gated to the prompt pulse, the setup's yellow detector holding the delayed one."""
    detectors = windows.preflight_detectors(
        {"green": ([0], [PROMPT]), "red": ([1], [PROMPT])},
        {
            "green": {"chs": [0], "micro_time_ranges": [[0, 1613]]},
            "red": {"chs": [1], "micro_time_ranges": [[0, 1613]]},
            "yellow": {"chs": [1], "micro_time_ranges": [[1613, 3125]]},
            "blue": {"chs": [5], "micro_time_ranges": [[0, 10]]},  # other channels: not checked
        },
    )
    assert set(detectors) == {"green", "red", "yellow"}
    assert windows.window_warnings(demo, detectors) == []


@pytest.mark.xfail(
    strict=True,
    reason="the shared gate check (excitation/check.py _check_gates) reports a FRET acceptor gated "
    "to the donor-excitation pulse -- BVA's standard PIE gating -- as a gate that leaves out the "
    "acceptor excitation it sees, unless a sibling detector on the same channels holds that pulse "
    "(the CLI and explicit settings carry no setup to supply one); flips to a pass when the check "
    "accepts a gate that deliberately keeps one excitation",
)
def test_a_fret_pair_gated_to_the_prompt_pulse_says_nothing(demo):
    assert windows.window_warnings(demo, _pair(PROMPT, PROMPT)) == []


def test_ungated_streams_are_not_checked(demo):
    assert windows.window_warnings(demo, windows.stream_detectors(
        {"donor": ([0], []), "acceptor": ([1], [])})) == []


def test_a_donor_only_measurement_gives_no_false_warning(donor_only):
    assert windows.window_warnings(donor_only, _pair(PROMPT, FULL)) == []
    assert windows.window_warnings(donor_only, _pair(FULL, FULL)) == []


def test_the_rpc_result_carries_the_warning(folder):
    from chisurf.plugins.burst.burst_bva.backend.services import compute_bva_handler

    def run(donor):
        settings = {
            "donor_channels": [0],
            "donor_micro_time_ranges": [donor],
            "acceptor_channels": [1],
            "acceptor_micro_time_ranges": [FULL],
            "file_type": "PTU",
        }
        out = compute_bva_handler(analysis_folder=str(folder), settings=settings,
                                  write_output=False)
        assert out.get("ok", True) is not False, out
        return (out.get("result") or out)["warnings"]

    wrong = run(WRONG_DONOR)
    assert len(wrong) == 1 and "do not match the data" in wrong[0]
    assert run(FULL) == []


def test_the_workflow_context_supplies_the_pie_siblings(folder):
    from chisurf.plugins.burst.burst_bva.backend.services import compute_bva_handler

    context = {
        "burst_folder": str(folder),
        "channel_settings": {
            "detectors": {
                "green": {"chs": [0], "micro_time_ranges": [list(PROMPT)]},
                "red": {"chs": [1], "micro_time_ranges": [list(PROMPT)]},
                "yellow": {"chs": [1], "micro_time_ranges": [[1613, 3125]]},
            },
            "tttr_reading": {"file_type": "PTU"},
        },
    }
    out = compute_bva_handler(workflow_context=context, write_output=False)
    assert (out.get("result") or out)["warnings"] == [], out


def test_the_cli_prints_the_warning(folder):
    from click.testing import CliRunner

    from chisurf.plugins.burst.burst_bva.cli.main import cli

    args = ["compute", str(folder), "--file-type", "PTU", "--donor-channels", "0",
            "--acceptor-channels", "1", "--donor-mtr-start", str(WRONG_DONOR[0]),
            "--donor-mtr-end", str(WRONG_DONOR[1]), "-o", str(folder / "bv4")]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "warning: Detector gates do not match the data" in result.output


def test_the_window_offers_and_takes_the_detected_gates(demo):
    from chisurf.plugins.burst.burst_bva.gui.view_model import BvaViewModel

    model = BvaViewModel()
    model.donor_channels_text, model.acceptor_channels_text = "0", "1"
    model.donor_micro_time_ranges = [WRONG_DONOR]
    model.acceptor_micro_time_ranges = [FULL]
    model.set_window_checks(model.check_windows(demo))
    assert "do not match the data" in model.windows_check_text()
    assert not model.windows_check_quiet and model.windows_check_offer
    assert model.use_detected_windows()
    assert model.donor_micro_time_ranges == [(0, 3124)]  # the whole range, inclusive
    assert model.acceptor_micro_time_ranges == [(0, 3124)]  # clipped to the data
    model.set_window_checks(model.check_windows(demo))
    assert model.windows_check_quiet and not model.windows_check_offer


def test_the_window_says_nothing_on_matching_ranges(demo):
    from chisurf.plugins.burst.burst_bva.gui.view_model import BvaViewModel

    model = BvaViewModel()
    model.donor_channels_text, model.acceptor_channels_text = "0", "1"
    model.set_window_checks(model.check_windows(demo))
    assert model.windows_check_quiet and not model.windows_check_offer


def test_a_run_of_the_window_shows_the_check(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    app = create_app()
    try:
        m = app.model
        m.auto_update = False
        m.file_type = "PTU"
        m.donor_channels_text, m.acceptor_channels_text = "0", "1"
        m.donor_micro_time_ranges = [WRONG_DONOR]
        assert app.controller.set_folder(folder)
        app.controller.run()
        app.controller._future.result(timeout=120)
        app.controller.poll()
        assert m.df is not None, m.status_text
        assert m.windows_check_offer and "excitation-window check" in m.status_text
        Driver(app, size=(1100, 720)).draw(3)
        assert "windows_check" in app.item_rects
    finally:
        app.close()
