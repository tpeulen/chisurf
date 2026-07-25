"""Tests for the decay-specific tools: IRF, components, report, plot.

These pin the behaviour that decides whether a TCSPC fit is meaningful at
all, using the real sample decay and its measured IRF.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import ToolError
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import decay as decay_tools
from chisurf.core.agent.tools import fitting as fitting_tools

TCSPC = "tcspc/EasyTau300"
MODEL = "Lifetime (new)"
DECAY_FILE = f"{TCSPC}/215-268 D0.dat"
IRF_FILE = f"{TCSPC}/215-268 D0 irf.dat"


@pytest.fixture()
def decay_fit(context):
    """Load the sample decay and its IRF and create a fit on the decay."""
    data_tools.load_data(context, paths=[DECAY_FILE, IRF_FILE])
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0])
    return context


# ── IRF handling ──────────────────────────────────────────────────────


def test_loading_flags_irf_files_as_references(context):
    result = data_tools.load_data(context, paths=[DECAY_FILE, IRF_FILE])
    assert result["likely_irf_datasets"] == [1]
    assert "set_irf" in result["hint"]


def test_set_irf_attaches_the_measured_response(decay_fit):
    result = decay_tools.set_irf(decay_fit, irf=1, fit=0)
    assert result["ok"]
    assert result["irf"]["index"] == 1
    convolve = decay_fit.fits[0].model.convolve
    assert convolve._irf is not None
    assert "Run the fit again" in result["next_step"]


def test_set_irf_can_address_the_irf_by_name(decay_fit):
    name = decay_fit.datasets[1].name
    result = decay_tools.set_irf(decay_fit, irf=name, fit=0)
    assert result["irf"]["index"] == 1


def test_set_irf_without_a_target_suggests_the_candidates(decay_fit):
    with pytest.raises(ToolError, match="irf"):
        decay_tools.set_irf(decay_fit, fit=0)


def test_set_irf_removes_the_response_again(decay_fit):
    decay_tools.set_irf(decay_fit, irf=1, fit=0)
    result = decay_tools.set_irf(decay_fit, fit=0, remove=True)
    assert result["irf"] is None


def test_looks_like_irf_recognises_the_usual_names():
    class Dataset:
        def __init__(self, name):
            self.name = name

    assert decay_tools.looks_like_irf(Dataset("sample_IRF.dat"))
    assert decay_tools.looks_like_irf(Dataset("prompt.dat"))
    assert not decay_tools.looks_like_irf(Dataset("215-268 D0.dat"))


# ── components ────────────────────────────────────────────────────────


def test_component_groups_finds_the_lifetimes(decay_fit):
    groups = decay_tools.component_groups(decay_fit.fits[0].model)
    assert groups.get("lifetimes") == 1


def test_set_components_adds_and_removes(decay_fit):
    added = decay_tools.set_components(decay_fit, n=3, fit=0)
    assert added["n_components"] == 3
    assert added["component"] == "lifetimes"

    removed = decay_tools.set_components(decay_fit, n=2, fit=0)
    assert removed["n_components"] == 2


def test_set_components_rejects_zero(decay_fit):
    with pytest.raises(ToolError, match="at least one"):
        decay_tools.set_components(decay_fit, n=0, fit=0)


def test_set_components_rejects_an_unknown_group(decay_fit):
    with pytest.raises(ToolError, match="available groups"):
        decay_tools.set_components(decay_fit, n=2, fit=0, component="gaussians")


# ── the point of it all ───────────────────────────────────────────────


def test_irf_and_a_second_component_produce_a_good_fit(decay_fit):
    """The whole reason these tools exist: chi2r 8.5 -> ~1.4."""
    without_irf = fitting_tools.run_fit(decay_fit, fit=0)["results"][0]["chi2r"]
    assert without_irf > 5

    decay_tools.set_irf(decay_fit, irf=1, fit=0)
    decay_tools.set_components(decay_fit, n=2, fit=0)
    with_irf = fitting_tools.run_fit(decay_fit, fit=0)["results"][0]["chi2r"]

    assert with_irf < 2.0, f"expected a good fit, got chi2r={with_irf}"
    assert with_irf < without_irf


# ── reporting ─────────────────────────────────────────────────────────


def test_fit_report_warns_when_no_irf_is_attached(decay_fit):
    report = decay_tools.fit_report(decay_fit, fit=0)
    assert report["irf_attached"] is False
    assert "set_irf" in report["warning"]
    assert report["components"]["lifetimes"] == 1


def test_fit_report_carries_the_quality_numbers(decay_fit):
    decay_tools.set_irf(decay_fit, irf=1, fit=0)
    decay_tools.set_components(decay_fit, n=2, fit=0)
    fitting_tools.run_fit(decay_fit, fit=0)

    report = decay_tools.fit_report(decay_fit, fit=0)
    assert report["irf_attached"] is True
    assert "warning" not in report
    assert report["chi2r"] is not None
    assert report["degrees_of_freedom"] > 0
    assert report["durbin_watson"] is not None
    assert report["residuals"]["rms"] > 0
    assert any(parameter["name"].startswith("tL") for parameter in report["parameters"])


# ── plotting ──────────────────────────────────────────────────────────


def test_a_bad_fit_is_called_bad_and_told_what_to_do(decay_fit):
    """A number alone let a real model report chi2r=12.8 as a result."""
    result = fitting_tools.run_fit(decay_fit, fit=0)
    assessment = result["results"][0]["assessment"]

    assert assessment["quality"] == "poor"
    assert "far above 1" in assessment["reason"]
    assert "set_irf" in assessment["next_step"], "no IRF attached — that is the first fix"
    assert "next_step" in result


def test_the_advice_moves_on_once_the_irf_is_attached(decay_fit):
    decay_tools.set_irf(decay_fit, irf=1, fit=0)
    result = fitting_tools.run_fit(decay_fit, fit=0)
    assessment = result["results"][0]["assessment"]

    assert assessment["quality"] == "poor"
    assert "set_components" in assessment["next_step"]


def test_a_good_fit_is_reported_as_good(decay_fit):
    decay_tools.set_irf(decay_fit, irf=1, fit=0)
    decay_tools.set_components(decay_fit, n=3, fit=0)
    result = fitting_tools.run_fit(decay_fit, fit=0)
    assessment = result["results"][0]["assessment"]

    assert assessment["quality"] in ("good", "acceptable")
    assert "next_step" not in result


def test_assessment_survives_a_fit_without_metrics(context):
    class Bare:
        """A fit-like object that cannot produce a chi2."""

        model = None

    verdict = decay_tools.assess_fit(Bare())
    assert verdict["quality"] == "unknown"


# ── the expert protocol in one call ───────────────────────────────────


def test_auto_fit_decay_finds_the_irf_and_the_component_count(decay_fit):
    result = decay_tools.auto_fit_decay(decay_fit, fit=0)

    assert result["ok"]
    assert "auto-detected dataset 1 as the IRF" in result["notes"]
    assert result["assessment"]["quality"] in ("good", "acceptable")
    assert result["n_components"] >= 2, "one exponential cannot describe this decay"

    trace = result["trace"]
    assert [step["n_components"] for step in trace] == list(range(1, len(trace) + 1))
    assert trace[-1]["chi2r"] < trace[0]["chi2r"] / 5, "adding components must help a lot here"


def test_auto_fit_decay_creates_the_fit_it_needs(context):
    """Fitting a decay is one instruction, not create_fit plus auto_fit."""
    data_tools.load_data(context, paths=[DECAY_FILE, IRF_FILE])
    assert context.fits == []

    result = decay_tools.auto_fit_decay(context)

    assert len(context.fits) == 1
    assert any("created fit 0" in note for note in result["notes"])
    assert result["assessment"]["quality"] in ("good", "acceptable")


def test_auto_fit_decay_asks_which_decay_when_several_could_be_meant(context):
    data_tools.load_data(context, directory=TCSPC, pattern="*.dat")
    with pytest.raises(ToolError, match="which decay"):
        decay_tools.auto_fit_decay(context)


def test_auto_fit_decay_refuses_when_only_references_are_loaded(context):
    data_tools.load_data(context, paths=[IRF_FILE])
    with pytest.raises(ToolError, match="no decay is loaded"):
        decay_tools.auto_fit_decay(context)


def test_auto_fit_decay_honours_a_component_ceiling(decay_fit):
    result = decay_tools.auto_fit_decay(decay_fit, fit=0, max_components=1)
    assert result["n_components"] == 1
    assert len(result["trace"]) == 1


def test_auto_fit_decay_rejects_a_component_that_does_not_earn_its_place(decay_fit):
    result = decay_tools.auto_fit_decay(decay_fit, fit=0, max_components=6)
    rejected = [step for step in result["trace"] if "rejected" in step]
    if rejected:
        assert "not material" in rejected[0]["rejected"]
    assert result["n_components"] <= 6


def test_auto_fit_decay_says_when_no_irf_was_found(context):
    data_tools.load_data(context, paths=[DECAY_FILE])
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0])
    result = decay_tools.auto_fit_decay(context, fit=0, max_components=2)
    assert any("no IRF" in note for note in result["notes"])


def test_auto_fit_decay_asks_which_irf_when_several_match(context):
    data_tools.load_data(
        context,
        paths=[DECAY_FILE, IRF_FILE, f"{TCSPC}/215-268 DA irf.dat"],
    )
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0])
    result = decay_tools.auto_fit_decay(context, fit=0, max_components=1)
    assert any("several datasets look like IRFs" in note for note in result["notes"])


def test_plot_fit_writes_a_png(decay_fit, tmp_path):
    fitting_tools.run_fit(decay_fit, fit=0)
    target = tmp_path / "plots" / "fit.png"
    result = decay_tools.plot_fit(decay_fit, path=str(target), fit=0)
    assert result["ok"]
    assert target.is_file()
    assert target.stat().st_size > 5000
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_plot_fit_reports_a_missing_fit(context):
    with pytest.raises(ToolError, match="create_fit"):
        decay_tools.plot_fit(context, path="nope.png")
