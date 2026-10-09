"""A displayed correction factor must retain its declared identification source."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.core.fitting.priors import NormalPrior
from chisurf.core.fluorescence.burst.table import read_burst_table
from chisurf.core.fluorescence.fret.accurate import AutoCalibration
from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
from chisurf.plugins.burst.accurate_fret import core
from chisurf.plugins.burst.accurate_fret.test.test_accurate_fret_plugin import _simulate


def _measured_channels():
    """Read the actual 152 observations using the GUI capture's channel mapping."""
    path = (
        Path(__file__).resolve().parents[2] / "chisurf/plugins/burst/burst_selection/tests/"
        "data/bh_spc132_sm_dna/burst_analysis_handoff/bi4_bur/m000.bur"
    )
    columns = read_burst_table(path)
    names = [
        "S prompt green (kHz) | 0-2048",
        "S prompt red (kHz) | 0-2048",
        "S delayed yellow (kHz) | 2048-4095",
    ]
    return *(columns[name] for name in names), None


def _capture_sdk(monkeypatch):
    """Observe actual SDK outputs while leaving the physical calculation intact."""
    original = tttrlib.auto_calibrate
    records = []

    def capture(columns, constants, options, progress):
        result = original(columns, constants, options, progress)
        records.append((result, constants, options))
        return result

    monkeypatch.setattr(tttrlib, "auto_calibrate", capture)
    return records


@pytest.mark.parametrize("sample", ["measured", "known"])
def test_actual_sdk_identification_flags_survive_adapter(monkeypatch, tmp_path, sample):
    """Measured and known calibrations preserve flags, estimates and messages."""
    records = _capture_sdk(monkeypatch)
    dd, da, aa, tau = _measured_channels() if sample == "measured" else _simulate(n=900)
    result = core.calibrate(dd, da, aa, tau, n_bootstrap=0, use_priors=False)
    raw, constants, options = records[-1]
    receipt = {
        "rows": len(dd),
        "estimated": raw["estimated"],
        "gamma_estimates": raw["gamma_estimates"],
        "messages": raw["messages"],
        "priors": constants["priors"],
        "use_priors": options["use_priors"],
        "factors": raw["factors"],
        "uncertainties": raw["uncertainties"],
    }
    (tmp_path / (sample + "-sdk.json")).write_text(json.dumps(receipt, indent=2))
    assert result.calibration.estimated == raw["estimated"]
    assert result.calibration.gamma_estimates == raw["gamma_estimates"]
    assert result.factors == raw["factors"]
    assert result.calibration.messages == raw["messages"]
    origins = dict(
        zip(
            ("alpha", "beta", "gamma", "delta", "r0"),
            [row["origin"] for row in result.factor_rows()],
        )
    )
    for key, identified in raw["estimated"].items():
        assert origins[key] == ("data estimate" if identified else "not identified; retained value")
    assert result.calibration.factor_provenance["beta"] in ("stoichiometry_assumption", "unknown")


@pytest.mark.parametrize("use_priors", [False, True])
def test_prior_source_requires_actual_use_context(monkeypatch, use_priors):
    """A configured Gaussian prior is not provenance when its use is disabled."""
    records = _capture_sdk(monkeypatch)
    calibration = CalibrationParameters()
    calibration._gamma.prior = NormalPrior(mu=0.6, sigma=0.1)
    dd, da, aa, tau = _measured_channels()
    result = core.calibrate(
        dd, da, aa, tau, calibration=calibration, n_bootstrap=0, use_priors=use_priors
    )
    raw, constants, options = records[-1]
    assert raw["estimated"]["gamma"] is False
    assert options["use_priors"] is use_priors
    source = "optics_prior" if use_priors else "not_identified"
    assert result.calibration.factor_provenance["gamma"] == source
    assert result.factor_rows()[2]["origin"] == (
        "optics prior" if use_priors else "not identified; retained value"
    )


def test_identified_data_with_used_prior_reports_combination(monkeypatch):
    """Only actual identified data and an enabled valid prior claim fusion."""
    records = _capture_sdk(monkeypatch)
    calibration = CalibrationParameters()
    calibration._gamma.prior = NormalPrior(mu=0.6, sigma=0.1)
    result = core.calibrate(
        *_simulate(n=900), calibration=calibration, n_bootstrap=0, use_priors=True
    )
    assert records[-1][0]["estimated"]["gamma"] is True
    assert result.calibration.factor_provenance["gamma"] == "data_and_optics_prior"
    assert result.factor_rows()[2]["origin"] == "data + optics prior"


def test_legacy_unknown_source_never_claims_a_calibration_method():
    """Old callers without identification metadata retain an honest unknown."""
    calibration = AutoCalibration(
        CalibrationParameters(), {"alpha": 0.1, "beta": 1.2, "gamma": 1.0, "delta": 0.0, "r0": 52.0}
    )
    result = core.CalibrationResult(calibration, np.array([0.5]), None, None, np.array([0]))
    assert [row["origin"] for row in result.factor_rows()[:4]] == ["source not reported"] * 4


def test_final_masks_do_not_determine_declared_factor_source():
    """An absent final population cannot erase an SDK-declared data estimate."""
    calibration = AutoCalibration(
        CalibrationParameters(), {"alpha": 0.1, "beta": 1.2, "gamma": 1.0, "delta": 0.0, "r0": 52.0}
    )
    calibration.estimated = {"alpha": True, "gamma": False, "delta": False}
    calibration.factor_provenance = {
        "alpha": "data",
        "gamma": "not_identified",
        "delta": "not_identified",
        "beta": "unknown",
    }
    result = core.CalibrationResult(calibration, np.array([0.5]), None, None, np.array([-3]))
    assert result.factor_rows()[0]["origin"] == "data estimate"
    assert result.factor_rows()[2]["origin"] == "not identified; retained value"


def test_missing_sdk_flags_stay_unknown_even_with_finite_gamma_estimates(monkeypatch):
    """A factor value or finite candidate estimate does not replace a missing flag."""
    original = tttrlib.auto_calibrate

    def legacy(*args, **kwargs):
        raw = original(*args, **kwargs)
        raw.pop("estimated")
        return raw

    monkeypatch.setattr(tttrlib, "auto_calibrate", legacy)
    result = core.calibrate(*_simulate(n=900), n_bootstrap=0, use_priors=False)
    assert result.calibration.estimated is None
    assert result.calibration.factor_provenance == dict.fromkeys(
        ("gamma", "alpha", "beta", "delta"), "unknown"
    )
    assert result.factor_rows()[2]["origin"] == "source not reported"


def test_factor_source_labels_use_the_core_translation_backend(monkeypatch):
    """New visible origin text participates in the Qt-free translation seam."""
    from chisurf.core.support import i18n

    monkeypatch.setattr(i18n, "_backend", lambda context, text: "translated:" + text)
    calibration = AutoCalibration(CalibrationParameters(), {"r0": 52.0})
    result = core.CalibrationResult(calibration, np.array([0.5]), None, None, np.array([-3]))
    assert result.factor_rows()[2]["origin"] == "translated:source not reported"
    assert result.factor_rows()[4]["origin"] == "translated:given"


def test_report_adapter_keeps_identification_metadata(monkeypatch):
    """Passing the result to the shared report writer does not discard provenance."""
    captured = {}

    def report(payload):
        captured.update(payload)
        return "report"

    monkeypatch.setattr(tttrlib, "calibration_report", report)
    calibration = AutoCalibration(
        CalibrationParameters(),
        {"gamma": 1.0},
        estimated={"gamma": False},
        factor_provenance={"gamma": "not_identified"},
    )
    assert calibration.report() == "report"
    assert captured["estimated"] == {"gamma": False}
    assert captured["factor_provenance"] == {"gamma": "not_identified"}


@pytest.mark.parametrize(
    "options,mu,sigma,expected",
    [
        ({}, 0.6, 0.1, "optics_prior"),
        ({"use_priors": None}, 0.6, 0.1, "optics_prior"),
        ({"use_priors": True}, 0.6, 0.0, "optics_prior"),
        ({"use_priors": True}, 0.6, -0.1, "not_identified"),
        ({"use_priors": True}, 0.6, np.nan, "not_identified"),
        ({"use_priors": True}, np.nan, 0.1, "not_identified"),
    ],
)
def test_prior_boundary_context_matches_actual_sdk_finish(
    monkeypatch, options, mu, sigma, expected
):
    """Default use and prior validity follow the SDK finish conditions exactly."""
    from chisurf.core.fluorescence.fret import accurate

    original = accurate.calibration_constants

    def with_prior(calibration):
        """Supply the declared SDK prior directly, including invalid widths."""
        constants = original(calibration)
        constants["priors"]["gamma"] = (mu, sigma)
        return constants

    monkeypatch.setattr(accurate, "calibration_constants", with_prior)
    dd, da, aa, _ = _measured_channels()
    result = accurate.auto_calibrate(dd, da, aa, n_bootstrap=0, **options)
    assert result.estimated["gamma"] is False
    assert result.factor_provenance["gamma"] == expected
    assert result.factors["gamma"] == (0.6 if expected == "optics_prior" else 1.0)
