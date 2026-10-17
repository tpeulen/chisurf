"""The Chain-diagnostics page says *why* it has nothing to draw, and opens ndX.

Four states of a fit's sampling run, four different pages: no run at all, a
report without draws (the run happened in another process), a chain too short
to judge, and a chain that is drawn.
"""

from __future__ import annotations

import types

import numpy as np
import pytest


def _fit(chain=None, diagnostics=None):
    return types.SimpleNamespace(
        name="f", sampling_chain=chain, sampling_diagnostics=diagnostics, model=None
    )


def _chain(n_draws):
    rng = np.random.default_rng(0)
    chains = rng.normal(size=(3, n_draws, 2))
    return {"chains": chains, "parameter_names": ["m:a", "m:b"], "burn_in": 0}


@pytest.fixture
def page_for():
    from chisurf.emtk.fit_pages.pages.sampling_diagnostics import SamplingDiagnosticsPlot

    def make(fit):
        page = SamplingDiagnosticsPlot(fit)
        page.update()
        return page

    return make


@pytest.mark.parametrize(
    "fit, state, words",
    [
        (_fit(), "none", "no chain stored for this fit"),
        (_fit(diagnostics={"n_chains": 3}), "external", "produced in another process"),
        (_fit(chain=_chain(5)), "short", "chain has 5 draws; at least 8 are needed"),
    ],
    ids=["none", "external", "short"],
)
def test_an_empty_page_says_why(page_for, fit, state, words):
    page = page_for(fit)
    assert page.state == state
    for notes in (page.rank_notes, page.ess_notes):
        assert len(notes) == 1 and words in notes[0].text


def test_a_chain_is_drawn(page_for):
    page = page_for(_fit(chain=_chain(60)))
    assert page.state == "ok"
    assert page.parameters == ["a", "b"]
    assert any("flat = converged" in line.text for line in page.rank_notes)
    assert any("lowest ESS" in line.text for line in page.ess_notes)


def test_a_group_shows_its_selected_members_run(page_for):
    member = _fit(chain=_chain(60))
    group = types.SimpleNamespace(name="g", grouped_fits=[member], selected_fit=member, model=None)
    assert page_for(group).state == "ok"


def test_open_in_ndx_is_on_both_panels_menus(page_for, monkeypatch):
    import chisurf.emtk.fit_pages.pages.sampling_diagnostics as module
    import chisurf.plugins.ndxplorer.gui.app as ndx_app

    opened = []
    monkeypatch.setattr(module, "project_path_for_ndx", lambda: "/tmp/p.cs.pto")
    monkeypatch.setattr(ndx_app, "open_in_ndx", opened.append)
    page = page_for(_fit(chain=_chain(60)))
    for panel in (page.rank_plot, page.ess_plot):
        labels = [label for label, _cb in panel._extra_menu_actions]
        assert "Open in ndX" in labels
    dict(page.rank_plot._extra_menu_actions)["Open in ndX"]()
    assert opened == ["/tmp/p.cs.pto"]
