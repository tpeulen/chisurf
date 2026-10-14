"""LLTF has one set of defaults (the packaged YAML), and the CLI overrides only what it is given."""

from __future__ import annotations

import pathlib

import pytest
import yaml
from click.testing import CliRunner

from chisurf.plugins.fluorescence_decay.lltf.core import cli as lltf_cli
from chisurf.plugins.fluorescence_decay.lltf.core import fitter
from chisurf.plugins.fluorescence_decay.lltf.core.settings import get_default_settings
from chisurf.plugins.fluorescence_decay.lltf.gui.model import LLTFModel

_EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / "example"
_DECAY = _EXAMPLE / "5-44_D0.dat"
_IRF = _EXAMPLE / "IRF_D0.dat"


class _Captured(Exception):
    """Stops the CLI once the configuration handed to the fitter is captured."""


def test_fit_lifetime_without_config_uses_the_packaged_settings(tmp_path, monkeypatch):
    """The range, start lifetimes and selection mode come from lifetime_settings.yml."""
    seen = {}
    original = fitter.Decay.get_analysis_range

    def capture(self, **kwargs):
        seen.update(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(fitter.Decay, "get_analysis_range", capture)
    fitter.fit_lifetime(
        str(_DECAY),
        str(_IRF),
        config={
            "lifetime_fit_parameter": {
                "plot_probabilities": False,
                "plot_weighted_residuals": False,
            }
        },
        save_intermediate_results=False,
        output_file=str(tmp_path / "fit.json"),
    )
    packaged = get_default_settings()["analysis_range_parameter"]
    for key in ("area", "start_fraction", "count_threshold", "start_at_peak"):
        assert seen[key] == packaged[key], key


def test_packaged_selection_mode_is_the_documented_lower():
    assert get_default_settings()["lifetime_fit_parameter"]["selection_mode"] == "lower"


def _cli_config(tmp_path, monkeypatch, file_settings, extra_args):
    """Run ``lltf fit -f`` with *file_settings* and return the configuration the fitter got."""
    seen = {}

    def fake_fit_lifetime(**kwargs):
        seen.update(kwargs["config"])
        raise _Captured

    monkeypatch.setattr(lltf_cli, "fit_lifetime", fake_fit_lifetime)
    config = tmp_path / "config.yml"
    config.write_text(yaml.safe_dump(file_settings))
    result = CliRunner().invoke(
        lltf_cli.cli,
        ["fit", str(_DECAY), str(_IRF), "-c", str(config), "-sp", str(tmp_path), "-f", *extra_args],
    )
    assert isinstance(result.exception, _Captured), result.output
    return seen["lifetime_fit_parameter"]


def test_cli_keeps_the_files_scan_settings_when_no_option_is_given(tmp_path, monkeypatch):
    """selection_mode upper in the file used to be overwritten by the CLI's own default lower."""
    file_settings = {
        "lifetime_fit_parameter": {
            "selection_mode": "upper",
            "prob_threshold": 0.9,
            "maximum_number_of_lifetimes": 4,
            "noise_model": "poisson",
        }
    }
    got = _cli_config(tmp_path, monkeypatch, file_settings, [])
    assert got["selection_mode"] == "upper"
    assert got["prob_threshold"] == pytest.approx(0.9)
    assert got["maximum_number_of_lifetimes"] == 4
    assert got["noise_model"] == "poisson"


def test_cli_options_override_the_file(tmp_path, monkeypatch):
    file_settings = {
        "lifetime_fit_parameter": {"selection_mode": "upper", "noise_model": "poisson"}
    }
    got = _cli_config(
        tmp_path,
        monkeypatch,
        file_settings,
        ["-sm", "lower", "-pt", "0.5", "-m", "3", "--noise-model", "neyman"],
    )
    assert got["selection_mode"] == "lower"
    assert got["prob_threshold"] == pytest.approx(0.5)
    assert got["maximum_number_of_lifetimes"] == 3
    assert got["noise_model"] == "neyman"


def test_panel_passes_its_noise_model(tmp_path):
    model = LLTFModel()
    assert model.noise_model == get_default_settings()["lifetime_fit_parameter"]["noise_model"]
    model.decay_file, model.irf_file = str(_DECAY), str(_IRF)
    model.noise_model = "poisson"
    command = model.build_command(str(tmp_path / "c.yml"))
    assert command[command.index("--noise-model") + 1] == "poisson"
    assert model.export_preferences()["noise_model"] == "poisson"
