"""Tests for the MFD preparation plugin (see /plugins/burst.md)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TEST_FOLDER = (
    Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "burst_analysis_handoff"
)


class TestApi:
    def test_prepare_folder_returns_result(self):
        from chisurf.plugins.burst.mfd_prepare.api import (
            prepare_folder,
            PrepareRequest,
        )

        result = prepare_folder(PrepareRequest(folder=str(TEST_FOLDER)))
        assert result.error == ""
        assert result.n_bursts > 0
        assert len(result.channels) >= 2
        assert result.report

    def test_prepare_folder_no_photons(self):
        from chisurf.plugins.burst.mfd_prepare.api import (
            prepare_folder,
            PrepareRequest,
        )

        result = prepare_folder(
            PrepareRequest(folder=str(TEST_FOLDER), with_photons=False)
        )
        assert result.error == ""
        assert result.n_bursts > 0

    def test_prepare_nonexistent_folder(self):
        from chisurf.plugins.burst.mfd_prepare.api import (
            prepare_folder,
            PrepareRequest,
        )

        result = prepare_folder(PrepareRequest(folder="/nonexistent/path"))
        assert result.error != ""

    def test_describe_returns_contract(self):
        from chisurf.plugins.burst.mfd_prepare.api import describe_preparation

        contract = describe_preparation()
        assert contract["plugin"] == "mfd_prepare"
        assert len(contract["methods"]) == 2

    def test_result_to_dict_is_json_serializable(self):
        from chisurf.plugins.burst.mfd_prepare.api import (
            prepare_folder,
            PrepareRequest,
        )

        result = prepare_folder(PrepareRequest(folder=str(TEST_FOLDER)))
        d = result.to_dict()
        json.dumps(d, default=str)


class TestCli:
    def test_cli_contract(self):
        from click.testing import CliRunner
        from chisurf.plugins.burst.mfd_prepare.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["contract"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plugin"] == "mfd_prepare"

    def test_cli_prepare_report_only(self):
        from click.testing import CliRunner
        from chisurf.plugins.burst.mfd_prepare.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["prepare", str(TEST_FOLDER), "--report-only", "--no-photons"],
        )
        assert result.exit_code == 0
        assert "bursts:" in result.output

    def test_cli_has_fit_command(self):
        from click.testing import CliRunner
        from chisurf.plugins.burst.mfd_prepare.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "fit" in result.output


@pytest.fixture
def qapp():
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    yield app


class TestGui:
    def test_gui_construction(self, qapp):
        from chisurf.plugins.burst.mfd_prepare.gui.tool import MfdPrepareTool

        tool = MfdPrepareTool()
        assert tool.windowTitle() == "MFD Prepare"
        assert tool.centralWidget() is not None
