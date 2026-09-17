"""Backend RPC service + CLI wiring tests for tttr_lut_tools."""

import pathlib

import pytest
from click.testing import CliRunner

from chisurf.plugins.tttr.tttr_lut_tools.backend.services import register_services
from chisurf.plugins.tttr.tttr_lut_tools.cli.main import cli

HERE = pathlib.Path(__file__).resolve().parents[5]
SPC = HERE / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


class _Dispatcher:
    def __init__(self):
        self.handlers = {}

    def register(self, name, fn):
        self.handlers[name] = fn

    def call(self, name, params):
        return self.handlers[name](params)


def test_register_services_registers_all_methods():
    d = _Dispatcher()
    register_services(d)
    assert set(d.handlers) == {
        "lut.autodetect_region",
        "lut.compute",
        "lut.apply_preview",
        "lut.settings_build",
        "lut.settings_load",
    }


def test_service_error_envelope_on_bad_input():
    d = _Dispatcher()
    register_services(d)
    res = d.call("lut.compute", {"files": ["/no/such/file.spc"]})
    assert res["ok"] is False and "error" in res


def test_settings_build_and_load_round_trip(tmp_path):
    d = _Dispatcher()
    register_services(d)
    out = str(tmp_path / "s.tttr.json")
    built = d.call(
        "lut.settings_build",
        {
            "channel_luts": {"0": [0.0, 1.0, 2.0]},
            "channel_shifts": {"0": 2},
            "reading_routine": "SPC-130",
            "out_path": out,
        },
    )
    assert built["ok"] and built["result"]["written"]
    loaded = d.call("lut.settings_load", {"path": out})
    assert loaded["ok"]
    assert loaded["result"]["channel_shifts"]["0"] == 2


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_cli_compute_and_settings(tmp_path):
    runner = CliRunner()
    lut_path = tmp_path / "green.npy"
    r = runner.invoke(cli, ["compute", str(SPC), "-o", str(lut_path)])
    assert r.exit_code == 0, r.output
    assert lut_path.is_file()
    settings_path = tmp_path / "s.tttr.json"
    r2 = runner.invoke(
        cli, ["settings", "--lut", f"0={lut_path}", "--shift", "0=3", "-o", str(settings_path)]
    )
    assert r2.exit_code == 0, r2.output
    assert settings_path.is_file()
