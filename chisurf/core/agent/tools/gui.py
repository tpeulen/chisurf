"""Tools that drive the ChiSurf window the agent is running in.

Inside the desktop application the agent is a co-pilot, not a batch job: a fit
it creates should be on the screen, a global fit it links should be the one
the user is looking at, a tool it recommends should open, and a script it
writes should be in the code editor. These tools give the model that reach,
and :class:`GuiFollower` does the obvious part without being asked — it puts
the result of the agent's own work in front of the user.

The window is reached through a :class:`GuiHost` stored as
``context.extras["gui"]``. The host is supplied by whoever embeds the agent
(the emtk shell, :mod:`chisurf.emtk.agent_gui`); without one — the CLI, the
MCP server, tests — these tools are not registered at all (see
:func:`build_gui_registry`), so a headless model is never offered a window it
cannot open.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import MODEL_TOOLS, SAFETY_WRITE, ToolError, ToolRegistry

__all__ = ["GUI_HOST", "GuiFollower", "GuiHost", "build_gui_registry", "registry"]

logger = logging.getLogger(__name__)

#: Key of the host in ``AgentContext.extras``.
GUI_HOST = "gui"

#: Tools whose results change the fits a window shows.
FIT_TOOLS = MODEL_TOOLS
#: Tools whose results change the datasets a window shows.
DATA_TOOLS = {"load_data", "extract_subensemble_decay"}
#: Tools that write a file the user should see.
FILE_TOOLS = {"write_file"}


class GuiHost(Protocol):
    """What the agent needs from the application window."""

    def windows(self) -> list[dict[str, Any]]:
        """Return the open windows: ``{"id", "title"}``."""
        ...

    def tools(self) -> list[dict[str, Any]]:
        """Return the tools that can be opened: ``{"id", "label", "description"}``."""
        ...

    def open_tool(self, tool_id: str) -> dict[str, Any]:
        """Open (or bring forward) the tool *tool_id*."""
        ...

    def show_fit(self, uid: str) -> dict[str, Any]:
        """Bring the window of the fit *uid* forward, opening it if needed."""
        ...

    def open_file(self, path: str, line: int = 0) -> dict[str, Any]:
        """Open *path* in the code editor, at *line* when given."""
        ...

    def sync(self) -> None:
        """Refresh the window's view of the session's datasets and fits."""
        ...


registry = ToolRegistry()


def _host(context: AgentContext) -> GuiHost:
    """Return the window host, or raise a readable error."""
    host = context.extras.get(GUI_HOST)
    if host is None:
        raise ToolError("there is no ChiSurf window in this session")
    return host


def _words(text: str) -> set[str]:
    """Return the lower-case words of *text*."""
    return {word for word in "".join(c if c.isalnum() else " " for c in text.lower()).split()}


def match_tools(tools: list[dict[str, Any]], query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Rank *tools* by how well their id, label and description match *query*.

    Parameters
    ----------
    tools : list of dict
        ``{"id", "label", "description"}`` records.
    query : str
        What the user or model asked for, e.g. ``"global fit"``.
    limit : int
        Maximum number of matches.

    Returns
    -------
    list of dict
        Best first; an empty query returns the first *limit* tools.
    """
    wanted = _words(query)
    if not wanted:
        return tools[:limit]
    scored = []
    for tool in tools:
        name = _words(f"{tool.get('id', '')} {tool.get('label', '')}")
        prose = _words(str(tool.get("description", "")))
        score = 3 * len(wanted & name) + len(wanted & prose)
        if str(tool.get("id", "")).lower() == query.strip().lower():
            score += 10
        if score:
            scored.append((score, tool))
    scored.sort(key=lambda pair: -pair[0])
    return [tool for _score, tool in scored[:limit]]


def resolve_tool(tools: list[dict[str, Any]], reference: str) -> dict[str, Any]:
    """Return the tool *reference* names: its id, its label, or one clear match.

    Raises
    ------
    ToolError
        When nothing matches, or the match is ambiguous; the message lists
        the candidates so the model can pick.
    """
    wanted = str(reference or "").strip().lower()
    for tool in tools:
        if wanted in (str(tool.get("id", "")).lower(), str(tool.get("label", "")).lower()):
            return tool
    candidates = match_tools(tools, reference, limit=5)
    if len(candidates) == 1:
        return candidates[0]
    names = ", ".join(f"{t['id']} ({t.get('label', '')})" for t in candidates)
    raise ToolError(
        f"no tool is called {reference!r}"
        + (f"; did you mean one of: {names}?" if names else "; call list_windows to see them")
    )


@registry.add(
    name="list_windows",
    description=(
        "List the windows open in ChiSurf and the tools that can be opened. Pass a "
        "'query' (e.g. 'global fit', 'burst', 'FCS', 'code editor') to find the tool "
        "for a job; then open it with open_window."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words describing the tool wanted."}
        },
    },
)
def list_windows(context: AgentContext, query: str = "") -> dict[str, Any]:
    """Return the open windows and the matching openable tools."""
    host = _host(context)
    return {
        "ok": True,
        "open": host.windows(),
        "tools": [
            {"id": t["id"], "label": t.get("label", ""), "description": t.get("description", "")}
            for t in match_tools(host.tools(), query)
        ],
    }


@registry.add(
    name="open_window",
    description=(
        "Open a ChiSurf tool window, or bring it to the front if it is open — when "
        "the user asks to see or use a tool. 'tool' is a tool id or label from "
        "list_windows."
    ),
    parameters={
        "type": "object",
        "properties": {"tool": {"type": "string", "description": "Tool id or label."}},
        "required": ["tool"],
    },
    safety=SAFETY_WRITE,
)
def open_window(context: AgentContext, tool: str) -> dict[str, Any]:
    """Open the tool *tool* in the window."""
    host = _host(context)
    chosen = resolve_tool(host.tools(), tool)
    result = host.open_tool(str(chosen["id"]))
    return {"ok": True, "opened": chosen["id"], "label": chosen.get("label", ""), **result}


@registry.add(
    name="show_fit",
    description=(
        "Bring a fit's window to the front so the user sees its curve and "
        "residuals. Fits the agent creates or runs are shown automatically; use "
        "this when the user asks to see a particular one."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index from list_fits, or its name.",
            }
        },
        "required": ["fit"],
    },
)
def show_fit(context: AgentContext, fit: Any) -> dict[str, Any]:
    """Show the window of *fit*."""
    host = _host(context)
    obj, index = context.resolve_fit(fit)
    host.sync()
    uid = str(getattr(obj, "unique_identifier", "") or "")
    if not uid:
        raise ToolError(f"fit {index} has no identifier a window could show")
    return {"ok": True, "fit": index, **host.show_fit(uid)}


@registry.add(
    name="open_in_code_editor",
    description=(
        "Open a file in ChiSurf's code editor, optionally at a line. Scripts you "
        "write with write_file open there automatically; use this to show the user "
        "an existing file or a source location."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to open."},
            "line": {"type": "integer", "description": "1-based line to show."},
        },
        "required": ["path"],
    },
)
def open_in_code_editor(context: AgentContext, path: str, line: int = 0) -> dict[str, Any]:
    """Open *path* in the code editor."""
    host = _host(context)
    target = context.resolve_path(path)
    if not target.is_file():
        raise ToolError(f"no file at {target}")
    return {"ok": True, "path": str(target), **host.open_file(str(target), int(line or 0))}


#: How the agent should use the window, appended to the system prompt when a
#: host is present. Short on purpose: a small model follows a short rule.
GUI_INSTRUCTIONS = (
    "You are running inside the ChiSurf desktop application and can drive its "
    "window. Fits you create or run appear in their own windows automatically, "
    "and files you write open in the code editor. When the user asks to open or "
    "use a tool, find it with list_windows and open it with open_window. When "
    "asked to write code, write it with write_file (it opens in the code editor) "
    "and run it with run_python if the user wants the result."
)


def build_gui_registry() -> ToolRegistry:
    """Return a fresh registry with the window tools."""
    fresh = ToolRegistry()
    for spec in registry.tools.values():
        fresh.register(spec)
    return fresh


class GuiFollower:
    """Put the result of the agent's own tool calls on the screen.

    Feed it the runtime's events (``context.event_callback`` forwards them);
    on a completed fit tool it refreshes the window and shows the fit that was
    created or changed, on ``write_file`` it opens the file in the code editor.

    Parameters
    ----------
    context : AgentContext
        The agent's context; its ``extras["gui"]`` is the host.
    """

    def __init__(self, context: AgentContext):
        self.context = context
        self._known = self._uids()
        self._arguments: dict[str, dict[str, Any]] = {}

    def _uids(self) -> list[str]:
        """Return the identifiers of the session's fits, in order."""
        return [str(getattr(fit, "unique_identifier", "")) for fit in self.context.fits]

    def __call__(self, event: str, payload: dict[str, Any]) -> None:
        """Handle one runtime event; never raises into the agent."""
        host = self.context.extras.get(GUI_HOST)
        if host is None:
            return
        name = str(payload.get("tool") or "")
        if event == "tool.started":
            self._arguments[name] = dict(payload.get("arguments") or {})
            return
        if event != "tool.completed" or not payload.get("ok", True):
            return
        arguments = self._arguments.pop(name, {})
        try:
            if name in FIT_TOOLS or name in DATA_TOOLS:
                host.sync()
            if name in FIT_TOOLS:
                self._show_touched_fit(host, arguments)
            elif name in FILE_TOOLS:
                path = (payload.get("result") or {}).get("path") or arguments.get("path")
                if path:
                    host.open_file(str(self.context.resolve_path(str(path))), 0)
        except Exception:  # noqa: BLE001 - the window must never break the agent
            logger.exception("following %s in the window failed", name)

    def _show_touched_fit(self, host: GuiHost, arguments: dict[str, Any]) -> None:
        """Show the newest new fit, else the fit the call named."""
        uids = self._uids()
        new = [uid for uid in uids if uid and uid not in self._known]
        self._known = uids
        if new:
            host.show_fit(new[-1])
            return
        reference = arguments.get("fit")
        if isinstance(reference, list):
            reference = reference[0] if reference else None
        if reference is None and arguments.get("fits"):
            fits = arguments["fits"]
            reference = fits[0] if isinstance(fits, list) and fits else None
        if reference is None or reference == "all":
            return
        try:
            obj, _index = self.context.resolve_fit(reference)
        except Exception:  # noqa: BLE001 - a reference the tool itself accepted
            return
        uid = str(getattr(obj, "unique_identifier", "") or "")
        if uid:
            host.show_fit(uid)
