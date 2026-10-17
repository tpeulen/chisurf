"""The Global View parameter network: what it draws, and what a gesture does.

The window is one emtk surface over a Qt-free model; what it draws and what a
gesture does is covered by the plugin's ``tests/test_model.py``. These tests
cover the graph builder the model reads and the Qt host: that nothing but the
host is Qt, that every guide step finds its control, and that fit events are
coalesced.
"""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import utils  # noqa: E402

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.fitting.parameter as fp  # noqa: E402
from chisurf.plugins.core.globalview.api.graph import build_graph  # noqa: E402


def _group(names):
    group = fp.FittingParameterGroup()
    for name in names:
        setattr(group, "_" + name, fp.FittingParameter(value=1.0, name=name))
    group.find_parameters()
    return group


class _Fit:
    def __init__(self, model, name="Fit"):
        self.model = model
        self.name = name
        self.unique_identifier = model.unique_identifier


# ── the builder ──────────────────────────────────────────────────────


def test_a_link_makes_exactly_one_edge():
    """Three fits with a ``tau`` each: one link is one edge, not three.

    The master used to be looked up by *name*, so a follower drew an edge to
    every same-named parameter in the session — with three fits of one model
    that is three arrows out of one link, two of them fiction.
    """
    models = [_group(["tau"]) for _ in range(3)]
    models[1].parameters_all_dict["tau"].link = models[0].parameters_all_dict["tau"]
    fits = [_Fit(m, f"Fit {i}") for i, m in enumerate(models)]

    result = build_graph(fit_list=fits)
    params = {n.node_idx for n in result.nodes if n.node_type == "parameter"}
    links = [e for e in result.edges if e.source in params and e.target in params]
    assert len(links) == 1


def test_the_link_edge_points_from_follower_to_master():
    """Direction is the whole meaning of the arrow, so it is asserted."""
    a, b = _group(["tau"]), _group(["tau"])
    b.parameters_all_dict["tau"].link = a.parameters_all_dict["tau"]
    result = build_graph(fit_list=[_Fit(a, "A"), _Fit(b, "B")])

    by_idx = {n.node_idx: n for n in result.nodes}
    params = {i for i, n in by_idx.items() if n.node_type == "parameter"}
    edge = next(e for e in result.edges if e.source in params and e.target in params)
    assert by_idx[edge.source].is_linked  # follower
    assert not by_idx[edge.target].is_linked  # master


# ── the window ───────────────────────────────────────────────────────
# 2f6fee28b retired the Qt GraphWizard host: the emtk app is the only window.
# The window-level contract (one emtk surface, every guide step pointing at a
# real control, the tour awaiting its control, refresh coalescing) moved to
# chisurf/plugins/core/globalview/tests/test_emtk_globalview.py, which drives
# the native GlobalViewApp directly.


def test_connect_base_joins_plugin_groups_to_the_fits():
    """Not just fits: a registered group is an owner and joins the same web.

    It used to connect ``node_type == "fit"`` only, which left a plugin's
    working model floating apart from the fits it exists to be linked against —
    the one relation the option is for.
    """
    from chisurf.core.registry.parameter_groups import (
        register_parameter_group,
        unregister_parameter_group,
    )

    plugin = _group(["E"])
    register_parameter_group(plugin, owner_id="test_owner", label="Plugin")
    try:
        result = build_graph(
            fit_list=[_Fit(_group(["tau"]), "A"), _Fit(_group(["tau"]), "B")],
            connect_owners=True,
            group_list=[("test_owner", "Plugin", plugin)],
        )
        owners = {n.node_idx for n in result.nodes if n.node_type in ("fit", "group")}
        group_idx = next(n.node_idx for n in result.nodes if n.node_type == "group")
        owner_edges = [e for e in result.edges if e.source in owners and e.target in owners]
        # 3 owners fully connected = 3 edges, and the group is in two of them.
        assert len(owner_edges) == 3
        assert sum(1 for e in owner_edges if group_idx in (e.source, e.target)) == 2
    finally:
        unregister_parameter_group("test_owner")
