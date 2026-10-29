"""2CDE runs the shared excitation-window pre-flight on the micro-time ranges of its two streams.

On the simulated PIE demo of Excitation Windows (pulses at 2 and 52 ns, routing 0 donor / 1
acceptor): ranges of another instrument warn in the RPC result and on the CLI's stderr; ranges
that hold the pulses say nothing, for FRET-2CDE and for ALEX-2CDE's donor-excitation /
acceptor-excitation streams. The window computes 2CDE without micro-time gates (it passes none),
so it has no ranges to check.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_2cde.core.computation import applied_streams  # noqa: E402
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


def test_the_streams_follow_the_variant():
    fret = applied_streams("fret", [0], [PROMPT], [1], [PROMPT], [1], [DELAYED])
    assert fret == {"donor": ([0], [PROMPT]), "acceptor": ([1], [PROMPT])}
    alex = applied_streams("alex", [0, 1], [PROMPT], [1], [PROMPT], [1], [DELAYED])
    assert alex == {"donor": ([0, 1], [PROMPT]), "acceptor excitation": ([1], [DELAYED])}
    assert applied_streams("alex", [0], [PROMPT], [1], [DELAYED])["acceptor"] == ([1], [DELAYED])


def _run(folder, **settings):
    from chisurf.plugins.burst.burst_2cde.backend.services import compute_2cde_handler

    out = compute_2cde_handler(analysis_folder=str(folder), write_output=False,
                               settings={"file_type": "PTU", **settings})
    assert out.get("ok", True) is not False, out
    return (out.get("result") or out)["warnings"]


def test_ranges_of_another_instrument_warn(folder):
    lines = _run(folder, donor_channels=[0], donor_micro_time_ranges=[WRONG_DONOR],
                 acceptor_channels=[1], acceptor_micro_time_ranges=[FULL])
    assert len(lines) == 1 and "do not match the data" in lines[0], lines


def test_ranges_that_hold_the_pulses_say_nothing(folder):
    assert _run(folder, donor_channels=[0], donor_micro_time_ranges=[FULL],
                acceptor_channels=[1], acceptor_micro_time_ranges=[FULL]) == []
    assert _run(folder, variant="alex", donor_channels=[0, 1], donor_micro_time_ranges=[PROMPT],
                acceptor_channels=[1], acceptor_micro_time_ranges=[PROMPT],
                acceptor_excitation_channels=[1],
                acceptor_excitation_micro_time_ranges=[DELAYED]) == []


def test_the_cli_prints_the_warning(folder):
    from click.testing import CliRunner

    from chisurf.plugins.burst.burst_2cde.cli.main import cli

    args = ["compute", str(folder), "--file-type", "PTU", "--donor-channels", "0",
            "--acceptor-channels", "1", "--donor-mtr-start", str(WRONG_DONOR[0]),
            "--donor-mtr-end", str(WRONG_DONOR[1])]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "warning: Detector gates do not match the data" in result.output
