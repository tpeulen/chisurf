"""Send a small model the tools its request needs, not the whole catalogue.

The full catalogue is ~46 tools and ~9k tokens of JSON Schema — three
quarters of every request. A hosted model shrugs that off; the on-device
1.7B model re-reads it every turn (~15 s of prompt processing on a laptop GPU
whenever the cache misses) and chooses worse from a longer list. *Focus*
sends a core set that covers the routine work — load, fit, report, script,
the window — plus:

* the tools the active skills declare (``tools:`` in ``SKILL.md``), including
  a skill loaded mid-run with ``load_skill``;
* the tools of a topic the request names (``burst`` → the single-molecule
  tools, ``global`` → linking, ``documentation`` → the reading tools, ...);
* anything the model asks for with :func:`find_tools`, the escape hatch.

The set only grows within a conversation: the tool list sits at the top of
the prompt, so every change re-processes the whole prompt, while a stable
list keeps the server's prompt cache valid. A known tool the model calls
without having been offered it still runs (the runtime dispatches by the full
registry) and joins the set.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import ToolRegistry

__all__ = ["CORE_TOOLS", "FIND_TOOLS", "TOPICS", "focus_for", "registry"]

#: The tool the model uses to reach the rest of the catalogue.
FIND_TOOLS = "find_tools"

#: Always offered: the routine chain plus the window, when there is one.
CORE_TOOLS = (
    FIND_TOOLS,
    "ask_user",
    "memory_recall",
    "memory_remember",
    "describe_session",
    "list_files",
    "load_data",
    "list_experiments",
    "create_fit",
    "run_fit",
    "auto_fit_decay",
    "set_irf",
    "set_components",
    "set_parameter",
    "get_fit",
    "list_fits",
    "fit_report",
    "run_python",
    "write_file",
    "read_file",
    "load_skill",
    # The window tools exist only when the agent runs inside the shell.
    "list_windows",
    "open_window",
    "show_fit",
    "open_in_code_editor",
)

#: Words of a request → the tools that topic needs. Matched on the lower-case
#: request, as substrings; generous on purpose — an extra tool costs a few
#: hundred tokens, a missing one costs a turn.
TOPICS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "burst",
            "single-molecule",
            "single molecule",
            "smfret",
            "pie",
            "alex",
            ".ptu",
            ".ht3",
            "tttr",
            "species",
            "stoichiometry",
            "efficiency histogram",
        ),
        (
            "detect_smfret",
            "run_burst_analysis",
            "inspect_bursts",
            "select_species",
            "extract_subensemble_decay",
            "fit_distance_distribution",
        ),
    ),
    (
        ("distance", "distribution", "fret"),
        ("fit_distance_distribution",),
    ),
    (
        ("global", "link", "share", "shared", "together", "simultaneous", "jointly"),
        ("link_parameters", "unlink_parameters", "list_links"),
    ),
    (("export", "csv", "table", "spreadsheet"), ("export_fit_results",)),
    (("save", "project", ".pto"), ("save_project",)),
    (("plot", "figure", "png", "picture", "graph"), ("plot_fit",)),
    (("range", "window", "channel"), ("set_fit_range",)),
    (("curve", "data points", "raw data", "values of"), ("get_curve",)),
    (
        (
            "what is",
            "what are",
            "what does",
            "how do",
            "how does",
            "explain",
            "documentation",
            "manual",
            "docs",
            "theory",
            "why",
            "mean",
        ),
        ("browse_documentation", "search_documentation", "read_documentation"),
    ),
    (("plugin", "tool for", "which tool"), ("list_plugins",)),
    (
        (
            "api",
            "class",
            "function",
            "method",
            "source",
            "script",
            "code",
            "program",
            "python",
            "write a",
            "implement",
        ),
        ("search_api", "read_api_source", "check_python"),
    ),
    (
        (
            "command",
            "shell",
            "terminal",
            "convert",
            "converter",
            "install",
            "unzip",
            "archive",
            "git",
        ),
        ("run_command", "which_program", "list_directory"),
    ),
    (("folder", "directory", "subfolder"), ("list_directory",)),
    (
        ("remember", "note", "finding", "record", "from now on", "always", "prefer"),
        ("record_finding", "save_skill"),
    ),
    (("skill", "procedure", "how would you"), ("list_skills",)),
)


def focus_for(question: str, skill_tools: list[str] | tuple[str, ...] = ()) -> set[str]:
    """Return the tools a request needs: core, its topics, and its skills' tools.

    Parameters
    ----------
    question : str
        The user's message.
    skill_tools : sequence of str
        Tools declared by the active skills.

    Returns
    -------
    set of str
        Tool names; names the registry does not hold are harmless.
    """
    wanted = set(CORE_TOOLS) | set(skill_tools)
    text = str(question or "").lower()
    for words, tools in TOPICS:
        if any(word in text for word in words):
            wanted.update(tools)
    return wanted


registry = ToolRegistry()


@registry.add(
    name=FIND_TOOLS,
    description=(
        "Find and enable more tools. Only the tools this request seemed to need "
        "are listed; ChiSurf has more — burst/single-molecule analysis, global "
        "fits (linking parameters), documentation, exporting, plotting, saving "
        "projects, running programs, the API reference. Describe what you need "
        "('link parameters', 'burst analysis', 'export csv'); the matching tools "
        "are enabled from your next step on."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What you need a tool for."}},
        "required": ["query"],
    },
)
def find_tools(context: AgentContext, query: str) -> dict[str, Any]:
    """Enable the tools matching *query* and say what they do."""
    full: ToolRegistry | None = context.extras.get("agent_registry")
    focus: set[str] | None = context.extras.get("tool_focus")
    if full is None or focus is None:
        return {"ok": True, "enabled": [], "note": "every tool is already available"}
    words = {
        w for w in "".join(c if c.isalnum() else " " for c in query.lower()).split() if len(w) > 2
    }
    # Topic words first: they encode which tools a phrase means.
    chosen = [t for t in sorted(focus_for(query) - set(CORE_TOOLS)) if full.get(t)]
    scored = []
    for name in full.names():
        spec = full.get(name)
        text = f"{name.replace('_', ' ')} {spec.description}".lower()
        score = sum(3 if word in name else 1 for word in words if word in text)
        if score:
            scored.append((score, name))
    for _score, name in sorted(scored, key=lambda pair: -pair[0])[:6]:
        if name not in chosen:
            chosen.append(name)
    new = [name for name in chosen if name not in focus]
    focus.update(chosen)
    return {
        "ok": True,
        "enabled": [
            {"name": name, "does": full.get(name).description.strip().splitlines()[0]}
            for name in chosen
        ],
        "note": (
            "These tools are available from your next step."
            if new
            else "These tools were already available — call them directly."
        ),
    }
