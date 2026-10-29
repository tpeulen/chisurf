"""The count rates run the shared excitation-window pre-flight before they count PIE windows.

The simulated PIE demo of Excitation Windows (32 ps, pulses at 2 and 52 ns) counted with the
windows of another instrument: the CLI prints the warning and the detected windows, with the
detected windows it prints nothing, and a donor-only file gives the note, not a warning. The tool
offers the detected windows after Calculate and the user takes them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tttrlib")

from tttrlib import setup_channel_map

from chisurf.core.fluorescence.excitation import windows_message  # noqa: E402
from chisurf.core.fluorescence.simulation import pie_demo as pie  # noqa: E402
from chisurf.plugins.tttr.tttr_count_rate_analysis.cli import (  # noqa: E402
    calculate_count_rates,
    window_check,
)

GATES = {"green": {"chs": [0], "micro_time_ranges": [[0, 4095]]},
         "red": {"chs": [1], "micro_time_ranges": [[0, 4095]]}}
MATCHING = {"detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 3125]]},
                          "red": {"chs": [1], "micro_time_ranges": [[0, 3125]]}},
            "windows": {"prompt": [50, 1613], "delayed": [1613, 3125]}}


def wrong_setup() -> dict:
    """The demo's mismatched setup (SPC-130 windows, 50 ps) with the gates the counts need."""
    return {**pie.wrong_setup(), "detectors": GATES}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return pie.make_demo(tmp_path_factory.mktemp("pie"))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    path = tmp_path_factory.mktemp("donly") / "donly.ptu"
    pie.make_demo(path.parent, donor_only=True, name=path.name, n_photons=100_000)
    return path


def _warnings(path, setup) -> list[str]:
    warnings: list[str] = []
    channels = setup_channel_map(setup, ungated_means_all=True, per_detector_without_windows=True)
    calculate_count_rates([str(path)], channels, setup=setup, warnings=warnings)
    return warnings


def test_wrong_windows_are_reported(demo):
    warnings = _warnings(demo, wrong_setup())
    assert len(warnings) == 1 and "PIE windows do not match" in warnings[0], warnings
    assert warnings[0].startswith(demo.name) and "prompt 50–1613" in warnings[0]


def test_matching_windows_say_nothing(demo):
    assert _warnings(demo, MATCHING) == []


def test_a_donor_only_file_gives_the_note_not_a_warning(donor_only):
    warnings = _warnings(donor_only, wrong_setup())
    assert len(warnings) == 1 and "donor-only" in warnings[0], warnings
    assert "do not match" not in warnings[0]


def test_the_cli_prints_the_warning(demo, tmp_path):
    import json

    from click.testing import CliRunner

    from chisurf.plugins.tttr.tttr_count_rate_analysis.cli import cli

    setups = tmp_path / "setups.json"
    setups.write_text(json.dumps({"setups": {"wrong": wrong_setup()}}))
    result = CliRunner().invoke(cli, ["analyze", str(demo), "-s", str(setups), "-n", "wrong"])
    assert result.exit_code == 0, result.output
    assert "PIE windows do not match" in result.output


def test_a_setup_without_windows_is_checked_for_its_gates_only(demo):
    per_detector = {"detectors": MATCHING["detectors"], "windows": {}}
    # "no windows" is not a finding
    assert windows_message(window_check(str(demo), per_detector)) is None
    narrow = {"detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 3125]]},
                            "red": {"chs": [1], "micro_time_ranges": [[1700, 3000]]}},
              "windows": {}}
    line = windows_message(window_check(str(demo), narrow))
    assert line and line.startswith("Detector gates do not match"), line


def test_calculate_offers_the_detected_windows_and_the_user_takes_them(demo):
    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

    app = create_app(setups={"wrong": wrong_setup()})
    try:
        tool = app.tool
        tool.add_paths([demo])
        assert tool.calculate()
        tool.job.future.result(timeout=120)
        tool.job.poll()
        assert tool.windows_check_offer and "do not match" in tool.windows_check_text()
        assert "Excitation-window check" in tool.message and demo.name in tool.message
        assert tool.use_detected_windows()
        windows = tool.channel_editor.model.get_settings()["windows"]
        assert windows["prompt"][0] < 2e-9 / 32e-12 < windows["prompt"][1]
        assert windows["delayed"][0] < 52e-9 / 32e-12 < windows["delayed"][1]
        assert not tool.windows_check_offer and tool.windows_check_quiet
        assert tool.calculate()
        tool.job.future.result(timeout=120)
        tool.job.poll()
        assert tool.windows_check_quiet, tool.windows_check_text()
    finally:
        app.close()
