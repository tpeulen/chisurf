"""The emtk shell as the agent's window: :class:`chisurf.core.agent.tools.gui.GuiHost`.

The agent runs on a worker thread; the shell's docks, windows and hand-offs
belong to the frame thread. Every host call is therefore queued with
:func:`call_on_frame`, run by the shell between two frames
(:func:`drain_frame_calls`, called from the shell's ``draw``), and waited for —
with a timeout, so an agent never hangs on a window that has stopped drawing.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

_log = logging.getLogger(__name__)

#: How long a host call waits for the frame thread before giving up.
FRAME_TIMEOUT_S = 15.0


class _FrameCall:
    """One queued call and its outcome."""

    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


def _queue(shell: Any) -> list[_FrameCall]:
    """Return the shell's queue of frame calls, creating it on first use."""
    queue = getattr(shell, "_agent_frame_calls", None)
    if queue is None:
        queue = []
        shell._agent_frame_calls = queue
    return queue


def call_on_frame(shell: Any, fn: Callable[[], Any], timeout_s: float = FRAME_TIMEOUT_S) -> Any:
    """Run *fn* on the shell's frame thread and return its value (or raise its error).

    On the frame thread itself it is a plain call.

    Raises
    ------
    TimeoutError
        When the shell did not draw a frame within *timeout_s*.
    """
    if getattr(shell, "_frame_thread", None) == threading.get_ident():
        return fn()
    call = _FrameCall(fn)
    _queue(shell).append(call)
    wake = getattr(shell, "request_frame", None)
    if callable(wake):
        wake()
    if not call.done.wait(timeout_s):
        try:
            _queue(shell).remove(call)
        except ValueError:
            pass
        raise TimeoutError("the ChiSurf window did not respond")
    if call.error is not None:
        raise call.error
    return call.value


def drain_frame_calls(shell: Any) -> None:
    """Run the queued agent calls; called once per frame from the shell's ``draw``."""
    shell._frame_thread = threading.get_ident()
    queue = getattr(shell, "_agent_frame_calls", None)
    while queue:
        call = queue.pop(0)
        try:
            call.value = call.fn()
        except BaseException as error:  # noqa: BLE001 - handed back to the waiting thread
            call.error = error
        finally:
            call.done.set()


class ShellGuiHost:
    """Drive an :class:`chisurf.emtk.main_app.EmtkShellApp` on behalf of the agent.

    Parameters
    ----------
    shell : EmtkShellApp
        The open shell.
    """

    def __init__(self, shell: Any):
        self.shell = shell

    def _call(self, fn: Callable[[], Any]) -> Any:
        """Run *fn* on the frame thread."""
        return call_on_frame(self.shell, fn)

    def windows(self) -> list[dict[str, Any]]:
        """Return the open tool and fit windows."""

        def read() -> list[dict[str, Any]]:
            rows = [
                {"id": hosted.instance_id, "title": str(hosted.title())}
                for hosted in list(self.shell.hosted.values())
            ]
            data = getattr(self.shell, "data", None)
            for uid in list(getattr(data, "windows", {}) or {}):
                rows.append({"id": f"fit:{uid}", "title": "fit window"})
            return rows

        return self._call(read)

    def tools(self) -> list[dict[str, Any]]:
        """Return the tools the shell's menus can open."""
        entries = list(getattr(self.shell, "by_id", {}).values())
        return [
            {
                "id": entry.plugin_id,
                "label": entry.label,
                "description": entry.description,
                "menu": " › ".join(entry.path[:-1]),
            }
            for entry in entries
            if not getattr(entry, "cli_only", False)
        ]

    def open_tool(self, tool_id: str) -> dict[str, Any]:
        """Open *tool_id*, or bring its window forward."""

        def open_() -> dict[str, Any]:
            hosted = self.shell.open_plugin(tool_id, focus=True)
            if hosted is None:
                return {"ran": True}
            return {"window": hosted.instance_id}

        return self._call(open_)

    def show_fit(self, uid: str) -> dict[str, Any]:
        """Bring the window of fit *uid* forward."""

        def show() -> dict[str, Any]:
            self.shell.data.show_fit(uid)
            return {"shown": uid in getattr(self.shell.data, "windows", {})}

        return self._call(show)

    def open_file(self, path: str, line: int = 0) -> dict[str, Any]:
        """Open *path* in the code editor."""
        payload: dict[str, Any] = {"path": path}
        if line:
            payload["line"] = int(line)

        def open_() -> dict[str, Any]:
            self.shell.hand_off("code_editor", "open_file", payload)
            return {"editor": "code_editor"}

        return self._call(open_)

    def sync(self) -> None:
        """Have the shell read the session's datasets and fits again."""
        data = getattr(self.shell, "data", None)
        if data is not None:
            self._call(data.refresh)


def attach_to_shell(context: Any, shell: Any = None) -> bool:
    """Give an agent *context* the open shell as its window; ``False`` when there is none.

    Installs the host in ``context.extras`` and chains a
    :class:`~chisurf.core.agent.tools.gui.GuiFollower` in front of the
    context's event callback.
    """
    from chisurf.core.agent.tools.gui import GUI_HOST, GuiFollower

    if shell is None:
        from chisurf.emtk.main_app import active_shell

        shell = active_shell()
    if shell is None:
        return False
    context.extras[GUI_HOST] = ShellGuiHost(shell)
    follower = GuiFollower(context)
    downstream = context.event_callback

    def forward(event: str, payload: dict) -> None:
        follower(event, payload)
        if downstream is not None:
            downstream(event, payload)

    context.event_callback = forward
    return True
