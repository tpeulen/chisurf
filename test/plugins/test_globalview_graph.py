"""Tests for the Global View graph builder's out-of-fit group support.

`build_graph` renders registered parameter groups (plugin working models) as
``"group"`` owner nodes alongside fits, and draws link edges between parameters
regardless of owner — so a plugin parameter linked to a fit parameter shows an
edge. Pure (no Qt).
"""

import pathlib

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.parameter  # noqa: F401  (initialises settings)
import chisurf.core.models  # noqa: F401
import chisurf.core.fitting.parameter as fp
from chisurf.plugins.core.globalview.api.graph import build_graph


def _group(names):
    g = fp.FittingParameterGroup()
    for n in names:
        setattr(g, "_" + n, fp.FittingParameter(value=1.0, name=n))
    g.find_parameters()
    return g


class _Fit:
    def __init__(self, model, name="Fit0"):
        self.model = model
        self.name = name
        self.unique_identifier = model.unique_identifier


def test_group_owner_and_param_nodes():
    g = _group(["tau", "amp"])
    res = build_graph(fit_list=[], group_list=[("plugin_x", "Plugin X", g)])
    owners = [n for n in res.nodes if n.node_type == "group"]
    params = [n for n in res.nodes if n.node_type == "parameter"]
    assert [o.name for o in owners] == ["Plugin X"]
    assert {p.name for p in params} == {"tau", "amp"}
    assert owners[0].owner_id == "plugin_x"
    assert all(p.param_uid for p in params)
    # each parameter connects to its owner
    owner_id = owners[0].node_idx
    assert sum(1 for e in res.edges if e.target == owner_id) == 2


def test_no_groups_is_fits_only():
    fit = _Fit(_group(["a"]))
    res = build_graph(fit_list=[fit])
    assert not any(n.node_type == "group" for n in res.nodes)
    assert any(n.node_type == "fit" for n in res.nodes)


def test_cross_owner_link_edge():
    fit_model = _group(["gtau"])
    plugin = _group(["tau"])
    plugin.parameters_all_dict["tau"].link = fit_model.parameters_all_dict["gtau"]

    res = build_graph(
        fit_list=[_Fit(fit_model)],
        group_list=[("plugin_x", "Plugin X", plugin)],
    )
    pidx = {n.node_idx for n in res.nodes if n.node_type == "parameter"}
    link_edges = [e for e in res.edges if e.source in pidx and e.target in pidx]
    assert len(link_edges) == 1


def test_include_fixed_filters_group_params():
    g = _group(["free1", "fixed1"])
    g.parameters_all_dict["fixed1"].fixed = True
    res = build_graph(
        fit_list=[], include_fixed=False,
        group_list=[("plugin_x", "Plugin X", g)],
    )
    names = {n.name for n in res.nodes if n.node_type == "parameter"}
    assert "free1" in names
    assert "fixed1" not in names
