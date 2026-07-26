"""Finding a function you only half know the name of.

The assistant reaches a plugin's implementation through the API index, and the
name it starts from is usually not the name in the source. An RPC method called
``fret_calculator.fret.compute_from_efficiency`` is implemented by
``compute_fret_from_efficiency`` — and the search returned *nothing* for it,
because ``_`` is a word character, so the query stayed one unsplittable term
that is not a substring of the real name. A real model followed that dead end
until it ran out of attempts.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentContext, ToolError
from chisurf.core.agent.tools import codebase

MODULE = "chisurf.plugins.calculator.fret_calculator.core.algorithms"


@pytest.fixture(scope="module")
def context():
    """Return a context with the API index loaded once."""
    return AgentContext(working_directory=".")


def qualnames(result):
    """Return the qualified names of a search result."""
    return [entry["qualname"] for entry in result["results"]]


# ── searching ─────────────────────────────────────────────────────────


def test_a_name_with_a_missing_word_still_finds_the_function():
    """The regression, stated as the model experienced it."""
    context = AgentContext(working_directory=".")
    found = qualnames(codebase.search_api(context, query="compute_from_efficiency"))
    assert f"{MODULE}.compute_fret_from_efficiency" in found


def test_the_exact_name_still_wins(context):
    """Loosening the match must not cost precision."""
    found = qualnames(codebase.search_api(context, query="compute_fret_from_lifetime"))
    assert found[0].endswith("compute_fret_from_lifetime")


def test_plugin_code_is_searchable_at_all(context):
    """Plugins are most of what ChiSurf does; the index must cover them."""
    found = qualnames(codebase.search_api(context, query="compute_kappa2_dist"))
    assert any("kappa2_dist" in name for name in found)


def test_a_nonsense_query_still_fails(context):
    with pytest.raises(ToolError, match="nothing in the ChiSurf API"):
        codebase.search_api(context, query="zzzquux")


# ── reading ───────────────────────────────────────────────────────────


def test_asking_for_a_module_lists_what_is_in_it(context):
    """The natural next move after finding a plugin, and it used to fail."""
    result = codebase.read_api_source(context, qualname=MODULE)

    assert result["module"] == MODULE
    assert result["n_symbols"] >= 5
    names = [entry["qualname"] for entry in result["symbols"]]
    assert f"{MODULE}.compute_fret_from_efficiency" in names
    assert "read_api_source" in result["next_step"]


def test_reading_a_function_still_returns_its_source(context):
    result = codebase.read_api_source(
        context, qualname=f"{MODULE}.compute_fret_from_efficiency"
    )
    assert "def compute_fret_from_efficiency" in result["source"]


def test_an_unknown_name_suggests_alternatives(context):
    with pytest.raises(ToolError, match="Did you mean"):
        codebase.read_api_source(context, qualname="chisurf.core.fitting.NotAThing")
