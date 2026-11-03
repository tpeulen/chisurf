"""The agent drives the ChiSurf window: tools, the follower, the frame queue."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

import chisurf as cs
from chisurf.core.agent.tools import gui
from chisurf.emtk import agent_gui


class FakeHost:
    """Records what the agent asked of the window."""

    def __init__(self):
        self.calls: list[tuple] = []

    def windows(self):
        """Return no open windows."""
        return []

    def tools(self):
        """A small catalogue."""
        return [
            {"id": "fcs_fit", "label": "FCS fit", "description": "Fit correlation curves"},
            {"id": "globalview", "label": "Global view", "description": "Global fit overview"},
            {"id": "code_editor", "label": "Code editor", "description": "Edit and run scripts"},
        ]

    def open_tool(self, tool_id):
        """Record an opening."""
        self.calls.append(("open_tool", tool_id))
        return {"window": tool_id}

    def show_fit(self, uid):
        """Record a fit shown."""
        self.calls.append(("show_fit", uid))
        return {"shown": True}

    def open_file(self, path, line=0):
        """Record a file opened."""
        self.calls.append(("open_file", path, line))
        return {}

    def sync(self):
        """Record a refresh."""
        self.calls.append(("sync",))


@pytest.fixture()
def hosted(context):
    """An agent context with a fake window."""
    host = FakeHost()
    context.extras[gui.GUI_HOST] = host
    return context, host


def test_a_tool_is_found_by_what_it_is_for(hosted):
    context, _host = hosted
    found = gui.list_windows(context, "global fit")
    assert found["tools"][0]["id"] == "globalview"


def test_open_window_accepts_a_label_and_refuses_a_guess(hosted):
    context, host = hosted
    assert gui.open_window(context, "Code editor")["opened"] == "code_editor"
    assert host.calls == [("open_tool", "code_editor")]
    with pytest.raises(gui.ToolError, match="no tool"):
        gui.open_window(context, "spectrometer")


def test_window_tools_are_only_offered_with_a_window():
    """A headless agent (CLI, MCP) is never offered a window it cannot open."""
    from chisurf.core.agent import build_default_registry

    assert "open_window" not in build_default_registry().names()
    assert {"list_windows", "open_window", "show_fit", "open_in_code_editor"} <= set(
        gui.build_gui_registry().names()
    )


def _fit(uid):
    return SimpleNamespace(unique_identifier=uid, name=uid)


def test_a_new_fit_is_shown_and_a_written_script_opens_in_the_editor(hosted, tmp_path):
    context, host = hosted
    follower = gui.GuiFollower(context)

    cs.fits.append(_fit("fit-a"))
    follower("tool.started", {"tool": "create_fit", "arguments": {"datasets": [0]}})
    follower("tool.completed", {"tool": "create_fit", "ok": True, "result": {}})
    assert host.calls == [("sync",), ("show_fit", "fit-a")]

    host.calls.clear()
    script = tmp_path / "analysis.py"
    script.write_text("print(1)\n")
    follower("tool.started", {"tool": "write_file", "arguments": {"path": str(script)}})
    follower("tool.completed", {"tool": "write_file", "ok": True, "result": {"path": str(script)}})
    assert host.calls == [("open_file", str(script), 0)]


def test_a_changed_fit_is_brought_forward(hosted):
    """run_fit on an existing fit shows that fit, not the newest."""
    context, host = hosted
    cs.fits.extend([_fit("one"), _fit("two")])
    follower = gui.GuiFollower(context)
    follower("tool.started", {"tool": "run_fit", "arguments": {"fit": 0}})
    follower("tool.completed", {"tool": "run_fit", "ok": True, "result": {}})
    assert host.calls == [("sync",), ("show_fit", "one")]


def test_a_failed_tool_moves_nothing(hosted):
    context, host = hosted
    follower = gui.GuiFollower(context)
    follower("tool.completed", {"tool": "create_fit", "ok": False, "result": {}})
    assert host.calls == []


def test_frame_calls_run_on_the_frame_thread():
    """The worker waits; the call runs where the shell draws."""
    shell = SimpleNamespace()
    ran_on: list[int] = []
    result: list = []

    worker = threading.Thread(
        target=lambda: result.append(
            agent_gui.call_on_frame(shell, lambda: ran_on.append(threading.get_ident()) or 7)
        )
    )
    worker.start()
    for _ in range(200):
        agent_gui.drain_frame_calls(shell)
        if result:
            break
        threading.Event().wait(0.01)
    worker.join(2)
    assert result == [7]
    assert ran_on == [threading.get_ident()]


def test_a_window_that_stopped_drawing_does_not_hang_the_agent():
    with pytest.raises(TimeoutError):
        agent_gui.call_on_frame(SimpleNamespace(), lambda: 1, timeout_s=0.05)


def test_attach_wires_host_and_follower(context):
    """The follower sees events before the panel's own callback does."""
    seen = []
    context.event_callback = lambda event, payload: seen.append(event)
    assert agent_gui.attach_to_shell(context, shell=SimpleNamespace(by_id={}, hosted={}))
    assert isinstance(context.extras[gui.GUI_HOST], agent_gui.ShellGuiHost)
    context.emit("tool.started", {"tool": "list_fits", "arguments": {}})
    assert seen == ["tool.started"]


def test_tools_that_change_models_run_under_the_perturbation_lock(context):
    """The shell's undo capture re-evaluates live models on another thread; it must wait.

    Caught mid-optimisation it failed with "prediction changed after reconstruction".
    """
    from chisurf.core.agent import AgentSession
    from chisurf.core.agent.llm import ToolCall
    from chisurf.core.agent.spec import ToolRegistry
    from chisurf.core.models.model import PERTURBATION_LOCK

    def free_elsewhere() -> bool:
        seen = []

        def probe():
            got = PERTURBATION_LOCK.acquire(blocking=False)
            seen.append(got)
            if got:
                PERTURBATION_LOCK.release()

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join()
        return seen[0]

    registry = ToolRegistry()
    for name in ("run_fit", "list_fits"):
        registry.add(name=name, description="probe")(
            lambda context, **_: {"ok": True, "free": free_elsewhere()}
        )
    session = AgentSession(llm=None, context=context, registry=registry, skills=None)
    held = session._execute(ToolCall(id="1", name="run_fit", arguments={}))
    unheld = session._execute(ToolCall(id="2", name="list_fits", arguments={}))
    assert held.result["free"] is False
    assert unheld.result["free"] is True
