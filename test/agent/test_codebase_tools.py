"""Knowledge tools: looking the API up instead of inventing it."""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import AgentContext, ToolError
from chisurf.core.agent.knowledge import (
    ApiIndex,
    iter_prose_documents,
    read_definition,
    repository_root,
    search_prose,
)
from chisurf.core.agent.tools import codebase as codebase_tools


@pytest.fixture(scope="module")
def index():
    """Return the API index, built once for the module."""
    return ApiIndex.load()


@pytest.fixture()
def context(tmp_path):
    """Return a context rooted at a scratch directory."""
    return AgentContext(working_directory=str(tmp_path))


# ── the index ─────────────────────────────────────────────────────────


def test_the_source_tree_yields_a_substantial_api(index):
    assert len(index.symbols) > 2000
    kinds = {symbol.kind for symbol in index.symbols}
    assert kinds == {"class", "function", "method"}


def test_private_symbols_are_left_out(index):
    assert not any(
        symbol.name.startswith("_") and symbol.name != "__init__" for symbol in index.symbols
    )


def test_tests_are_not_part_of_the_api(index):
    assert not any("/test/" in symbol.path for symbol in index.symbols)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("FitGroup", "chisurf.core.fitting.fit.FitGroup"),
        ("ChiSurfAPI", "chisurf.core.api.ChiSurfAPI"),
        ("add_fit", "chisurf.core.actions.fit_actions.add_fit"),
    ],
)
def test_a_known_symbol_is_found_by_name(index, query, expected):
    found = [symbol.qualname for symbol in index.search(query, limit=8)]
    assert expected in found


def test_an_exact_name_outranks_a_passing_mention(index):
    first = index.search("FitGroup", limit=1)[0]
    assert first.name == "FitGroup"


def test_a_search_can_be_restricted_to_classes(index):
    assert all(symbol.kind == "class" for symbol in index.search("fit", kind="class", limit=5))


def test_symbols_carry_a_usable_signature_and_location(index):
    symbol = index.get("chisurf.core.actions.fit_actions.add_fit")
    assert symbol is not None
    assert symbol.signature.startswith("def add_fit(")
    assert symbol.path.endswith("fit_actions.py")
    assert symbol.line > 0


def test_a_definition_can_be_read_back_from_source(index):
    symbol = index.get("chisurf.core.fitting.fit.FitGroup")
    source = read_definition(symbol, max_lines=40)
    assert source.startswith("class FitGroup")


def test_reading_a_definition_stops_at_the_next_one(index):
    symbol = index.get("chisurf.core.actions.fit_actions.add_fit")
    source = read_definition(symbol, max_lines=200)
    assert source.count("\ndef ") == 0, "the next function leaked into the result"


def test_the_index_is_cached_between_loads():
    first = ApiIndex.load()
    second = ApiIndex.load()
    assert len(first.symbols) == len(second.symbols)


# ── the prose ─────────────────────────────────────────────────────────


def test_prose_documents_are_found():
    documents = iter_prose_documents()
    assert len(documents) > 50
    assert any(path.name == "llm-agent.md" for path in documents)


def test_changelogs_are_excluded_from_the_prose():
    """They mention everything and answer nothing."""
    names = {path.name.lower() for path in iter_prose_documents()}
    assert "log.md" not in names


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("plugin manifest", "plugin"),
        ("fitting engine", "fitting"),
    ],
)
def test_a_concept_search_finds_the_document_about_it(query, expected):
    hits = search_prose(query, limit=3)
    assert hits
    assert any(expected in hit["document"] for hit in hits)


def test_prose_hits_carry_an_excerpt():
    hit = search_prose("plugin manifest", limit=1)[0]
    assert hit["excerpt"].strip()
    assert hit["title"]


# ── the tools ─────────────────────────────────────────────────────────


def test_search_api_returns_signatures(context):
    result = codebase_tools.search_api(context, query="FitGroup")
    assert result["ok"]
    assert result["results"][0]["signature"]
    assert ":" in result["results"][0]["location"]


def test_search_api_rejects_a_bad_kind(context):
    with pytest.raises(ToolError, match="must be"):
        codebase_tools.search_api(context, query="fit", kind="widget")


def test_search_api_says_so_when_nothing_matches(context):
    with pytest.raises(ToolError, match="nothing in the ChiSurf API"):
        codebase_tools.search_api(context, query="zzzznotarealsymbol")


def test_read_api_source_returns_the_definition(context):
    result = codebase_tools.read_api_source(
        context, qualname="chisurf.core.fitting.fit.FitGroup", max_lines=30
    )
    assert result["source"].startswith("class FitGroup")


def test_read_api_source_suggests_alternatives(context):
    with pytest.raises(ToolError, match="Did you mean"):
        codebase_tools.read_api_source(context, qualname="chisurf.core.fitting.FitGrup")


def test_search_docs_finds_the_architecture(context):
    result = codebase_tools.search_docs(context, query="plugin manifest")
    assert result["ok"] and result["documents"]


def test_read_doc_returns_a_documentation_file(context):
    result = codebase_tools.read_doc(context, document="okf/subsystems/llm-agent.md")
    assert "agent" in result["content"].lower()


def test_read_doc_refuses_to_leave_the_repository(context):
    with pytest.raises(ToolError):
        codebase_tools.read_doc(context, document="../../../etc/passwd")


def test_list_plugins_reports_manifests(context):
    result = codebase_tools.list_plugins(context)
    assert result["n_plugins"] > 10
    assert all(entry["path"].startswith("chisurf/plugins/") for entry in result["plugins"])


def test_list_plugins_can_be_filtered(context):
    result = codebase_tools.list_plugins(context, query="burst")
    assert result["n_plugins"] >= 1
    # An entry now carries lists as well as strings (RPC methods, packages),
    # so the haystack is flattened rather than joined.
    assert all("burst" in json.dumps(entry).lower() for entry in result["plugins"])


def test_list_plugins_says_how_to_drive_a_plugin(context):
    """Knowing a plugin exists is useless without knowing how to reach it."""
    result = codebase_tools.list_plugins(context)
    entries = result["plugins"]

    assert any("rpc_methods" in entry for entry in entries), "no plugin advertises an RPC method"
    assert any("cli" in entry for entry in entries), "no plugin advertises a command line"

    for entry in entries:
        for method in entry.get("rpc_methods", []):
            assert method["name"], f"{entry['id']} has an unnamed RPC method"


def test_a_plugin_is_findable_by_its_rpc_method_name(context):
    """"kappa" is what a user types; it appears only in the method name."""
    result = codebase_tools.list_plugins(context, query="kappa")
    names = [
        method["name"]
        for entry in result["plugins"]
        for method in entry.get("rpc_methods", [])
    ]
    assert "kappa2_dist.compute" in names


def test_list_plugins_reports_a_miss(context):
    with pytest.raises(ToolError, match="no plugin matches"):
        codebase_tools.list_plugins(context, query="zzzznotaplugin")


# ── checking generated code ───────────────────────────────────────────


def test_valid_code_passes_the_check(context):
    result = codebase_tools.check_python(context, code="def f(x):\n    return x + 1\n")
    assert result["syntax_ok"] is True


def test_a_syntax_error_is_reported_with_its_line(context):
    result = codebase_tools.check_python(context, code="def f(:\n    pass\n")
    assert result["ok"] is False
    assert result["syntax_ok"] is False
    assert "line" in result["error"]


def test_lint_problems_are_surfaced(context):
    result = codebase_tools.check_python(context, code="import os\nx = 1\n")
    if "note" in result:
        pytest.skip(result["note"])
    assert result["n_issues"] >= 1


def test_an_existing_file_can_be_checked(context, tmp_path):
    target = tmp_path / "script.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = codebase_tools.check_python(context, path="script.py")
    assert result["syntax_ok"] is True


def test_checking_nothing_is_refused(context):
    with pytest.raises(ToolError, match="nothing to check"):
        codebase_tools.check_python(context)


# ── the skill ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "write a plugin that shows the count rate",
        "how does chisurf store fits?",
        "implement a new fitting model for me",
        "add a feature to the burst browser",
    ],
)
def test_programming_requests_load_the_programming_skill(question):
    from chisurf.core.agent.skills import SkillLibrary

    matched = [skill.name for skill in SkillLibrary.discover().match(question, limit=3)]
    assert "program-chisurf" in matched


def test_the_repository_root_is_the_checkout():
    assert (repository_root() / "chisurf").is_dir()
    assert (repository_root() / "okf").is_dir()
