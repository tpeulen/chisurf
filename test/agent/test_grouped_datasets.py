"""A file that holds many curves must not be reported as one measurement.

A Zeiss ConfoCor file is a measurement archive: the sample used here holds
sixteen correlation curves — four repeats each of two autocorrelations and two
cross-correlations. ChiSurf fits such a dataset as a group with one member per
curve, but the agent used to be told only "one fit, chi2r = 133" when the
sixteen members spanned 12 to 180. A single number standing in for sixteen is
not merely incomplete, it is wrong, and it is the kind of answer a user would
put in a paper.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentContext
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import fitting as fit_tools
from test.agent.conftest import DATA_DIR

CONFOCOR = DATA_DIR / "fcs" / "confocor3" / "Zeiss_Confocor3_LSM780_FCCS_HeLa_2015"
SAMPLE = "017_cp_KIND+BFA.fcs"
MODEL = "FCS (general: diffusion + bunching/anticorr)"


@pytest.fixture()
def loaded(clean_session):
    """Return a context with the ConfoCor sample loaded."""
    if not (CONFOCOR / SAMPLE).is_file():
        pytest.skip(f"no ConfoCor sample at {CONFOCOR / SAMPLE}")
    context = AgentContext(working_directory=str(CONFOCOR))
    data_tools.load_data(context, paths=[SAMPLE])
    return context


def test_the_group_reports_how_many_curves_it_holds(loaded):
    dataset = data_tools.list_datasets(loaded)["datasets"][0]
    assert dataset["n_curves"] == 16
    assert len(dataset["curves"]) == 16


def test_each_curve_says_which_kind_of_correlation_it_is(loaded):
    """The reader knows; it used to throw the answer away."""
    curves = data_tools.list_datasets(loaded)["datasets"][0]["curves"]
    kinds = [curve["correlation_type"] for curve in curves]
    assert sorted(set(kinds)) == ["AC1", "AC2", "CC12", "CC21"]
    assert kinds.count("AC1") == 4, "four repeats of each kind"
    # The kind is part of the name, so a user reading a plot legend can tell
    # an autocorrelation from a cross-correlation.
    assert all(curve["name"].endswith(kind) for curve, kind in zip(curves, kinds))


def test_a_mixed_group_warns_that_the_curves_are_not_repeats(loaded):
    note = data_tools.list_datasets(loaded)["datasets"][0]["note"]
    assert "not repeats" in note
    assert "cross-correlation" in note


def test_a_fit_over_a_group_says_it_covers_every_curve(loaded):
    fit_tools.create_fit(loaded, model_name=MODEL)
    summary = fit_tools.list_fits(loaded)["fits"][0]

    assert summary["n_members"] == 16
    assert summary["chi2r_is_for_member"] == 0
    spread = summary["members_chi2r"]
    assert spread["min"] < spread["max"], "sixteen curves do not share one chi2r"
    assert "member 0 only" in summary["note"]


def test_running_a_grouped_fit_reports_every_member(loaded):
    fit_tools.create_fit(loaded, model_name=MODEL)
    entry = fit_tools.run_fit(loaded, fit=0)["results"][0]

    assert entry["ok"]
    members = entry["assessment"]["members"]
    assert len(members) == 16
    assert {member["member"] for member in members} == set(range(16))
    assert all(member["chi2r"] is not None for member in members)


def test_a_group_is_only_as_good_as_its_worst_curve(loaded):
    """One acceptable member must not pass a group full of bad ones."""
    fit_tools.create_fit(loaded, model_name=MODEL)
    fit_tools.run_fit(loaded, fit=0)

    from chisurf.core.agent.tools.decay import assess_fit

    verdict = assess_fit(loaded.fits[0])
    worst = max(member["chi2r"] for member in verdict["members"])
    assert worst > 2.0, "the sample is expected to fit badly with a naive model"
    assert verdict["quality"] == "poor"


def test_an_ordinary_dataset_gains_no_group_noise(clean_session):
    """A single curve must stay a single curve in the payload."""
    source = DATA_DIR / "fcs" / "kristine"
    if not source.is_dir():
        pytest.skip(f"no sample data at {source}")
    context = AgentContext(working_directory=str(source))
    data_tools.load_data(context, directory=".", pattern="*.cor")

    for dataset in data_tools.list_datasets(context)["datasets"]:
        assert "n_members" not in dataset
        if "n_curves" in dataset:
            assert dataset["n_curves"] > 1, "a count is only reported for real groups"
