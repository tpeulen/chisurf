"""Global analysis: sharing parameters between fits.

Linking is what makes ChiSurf a global-analysis platform, so these tests use
the real donor-only / donor-acceptor pair rather than synthetic objects.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import ToolError
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import fitting as fitting_tools
from chisurf.core.agent.tools import linking as linking_tools

TCSPC = "tcspc/EasyTau300"
MODEL = "Lifetime (new)"


@pytest.fixture()
def two_fits(context):
    """Two decay fits — the donor-only and donor-acceptor measurements."""
    data_tools.load_data(context, paths=[f"{TCSPC}/215-268 D0.dat", f"{TCSPC}/215-268 DA.dat"])
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0, 1])
    return context


def test_a_parameter_can_be_shared_between_fits(two_fits):
    result = linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)

    assert result["ok"]
    assert result["linked"] == [{"fit": 1, "parameter": "tL1"}]
    assert "Run the fits again" in result["next_step"]


def test_linking_removes_a_degree_of_freedom(two_fits):
    before = linking_tools.list_links(two_fits)["free_parameters"]["1"]
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    after = linking_tools.list_links(two_fits)["free_parameters"]["1"]

    assert after == before - 1, "a linked parameter must stop being fitted"


def test_the_link_is_visible_and_names_its_source(two_fits):
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    links = linking_tools.list_links(two_fits)

    assert links["n_links"] == 1
    assert links["links"][0]["fit"] == 1
    assert links["links"][0]["parameter"] == "tL1"
    assert links["links"][0]["follows"] == "tL1"


def test_a_linked_parameter_follows_the_source_value(two_fits):
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    fitting_tools.set_parameter(two_fits, parameter="tL1", fit=0, value=2.75)

    follower = two_fits.fits[1].model.parameters_all_dict["tL1"]
    assert follower.value == pytest.approx(2.75, rel=1e-6)


def test_links_can_be_released_again(two_fits):
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    released = linking_tools.unlink_parameters(two_fits, parameters=["tL1"])

    assert released["n_released"] == 1
    assert linking_tools.list_links(two_fits)["n_links"] == 0


def test_releasing_without_names_clears_every_link(two_fits):
    linking_tools.link_parameters(two_fits, parameters=["tL1", "sc"], source_fit=0)
    assert linking_tools.unlink_parameters(two_fits)["n_released"] == 2
    assert linking_tools.list_links(two_fits)["n_links"] == 0


def test_an_unknown_parameter_lists_the_real_ones(two_fits):
    with pytest.raises(ToolError, match="no parameter"):
        linking_tools.link_parameters(two_fits, parameters=["not_a_parameter"], source_fit=0)


def test_linking_needs_something_to_link_to(context):
    data_tools.load_data(context, paths=[f"{TCSPC}/215-268 D0.dat"])
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0])
    with pytest.raises(ToolError, match="no other fit"):
        linking_tools.link_parameters(context, parameters=["tL1"], source_fit=0)


def test_naming_no_parameter_is_refused(two_fits):
    with pytest.raises(ToolError, match="at least one"):
        linking_tools.link_parameters(two_fits, parameters=[], source_fit=0)


def test_a_single_name_is_accepted_as_well_as_a_list(two_fits):
    result = linking_tools.link_parameters(two_fits, parameters="tL1", source_fit=0)
    assert result["linked"] == [{"fit": 1, "parameter": "tL1"}]


def test_the_source_fit_keeps_its_own_freedom(two_fits):
    before = linking_tools.list_links(two_fits)["free_parameters"]["0"]
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    after = linking_tools.list_links(two_fits)["free_parameters"]["0"]

    assert after == before, "the source keeps fitting its own value"


def test_a_linked_series_still_runs(two_fits):
    linking_tools.link_parameters(two_fits, parameters=["tL1"], source_fit=0)
    result = fitting_tools.run_fit(two_fits)

    assert result["n_run"] == 2
    assert all(entry["ok"] for entry in result["results"])
