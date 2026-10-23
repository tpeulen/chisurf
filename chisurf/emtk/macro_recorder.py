"""The macro recorder that writes code for what the user does.

The console recorder only ever captured what was *typed* into the console,
which is why a recording of a pure point-and-click session came out empty.
Every click that changes the session funnels through the action dispatcher
(:mod:`chisurf.core.actions`), so the recorder taps that stream and translates
each dispatched action into the ``cs_dispatch(name, payload)`` call that
reproduces it. The composed macro is plain Python -- it lands in the console's
editor for editing and runs like any other macro.

Recording combines two channels:

* the actions the user triggered (buttons, menus, synced widgets), as
  ``cs_dispatch`` calls annotated with the time and the action's name;
* the code the user ran in the console, verbatim.
"""

from __future__ import annotations

import io
import os
import pprint
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Calls closer together than this with the same name and payload are one
#: action (the dispatcher debounces widget syncs by re-executing them).
DEDUPE_SECONDS = 3.0


@dataclass
class _Entry:
    """One recorded step: the code line, when it happened, and why it is here."""

    time: float
    code: str
    comment: str = ""

    def render(self) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(self.time))
        out = io.StringIO()
        if self.comment:
            out.write(f"# {stamp}  {self.comment}\n")
        else:
            out.write(f"# {stamp}\n")
        out.write(self.code.rstrip("\n") + "\n")
        return out.getvalue()


@dataclass
class MacroRecorder:
    """Collect user actions as an editable Python script.

    :meth:`attach` wraps a dispatcher's ``execute`` (records, then calls
    through); :meth:`detach` restores it. The wrapper records only what the
    action's spec marks replayable -- a macro must be a sequence the user can
    safely run again.
    """

    recording: bool = False
    entries: list[_Entry] = field(default_factory=list)
    #: The dispatcher this recorder is attached to, with its ``execute`` pair.
    _dispatcher: Any = None
    _original_execute: Any = None
    _wrapped_execute: Any = None
    #: (name, payload) of the last recorded action, with its timestamp.
    _last_action: tuple[str, Any, float] | None = None

    # -- the stream --------------------------------------------------------- #

    def record(self, code: str, comment: str = "") -> None:
        """Append one step to the macro (a no-op unless recording is on)."""
        if self.recording and code.strip():
            self.entries.append(_Entry(time=time.time(), code=code, comment=comment))

    # -- attachment --------------------------------------------------------- #

    def attach(self, dispatcher: Any) -> None:
        """Start recording every action *dispatcher* executes."""
        if self._dispatcher is dispatcher:
            return
        self.detach()
        original = dispatcher.execute

        def recording_execute(name, payload=None, summary=None, **kwargs):
            self._tap(name, payload, summary)
            return original(name, payload=payload, summary=summary, **kwargs)

        dispatcher.execute = recording_execute  # noqa: B010 - the instrumentation itself
        self._dispatcher = dispatcher
        self._original_execute = original
        self._wrapped_execute = recording_execute
        self.recording = True

    def detach(self) -> None:
        """Stop recording and put the dispatcher's ``execute`` back."""
        if (
            self._dispatcher is not None
            and getattr(self._dispatcher, "execute", None) is self._wrapped_execute
        ):
            self._dispatcher.execute = self._original_execute  # still ours: put it back
        self._dispatcher = None
        self._original_execute = None
        self._wrapped_execute = None
        self.recording = False

    def _tap(self, name: str, payload: dict | None, summary: str | None) -> None:
        """Translate one dispatched action into a macro step."""
        if not self.recording:
            return
        spec = None
        registry = getattr(self._dispatcher, "registry", None)
        if registry is not None:
            try:
                spec = registry.get(registry.resolve_name(name))
            except Exception:  # noqa: BLE001 - an unknown action has no spec
                spec = None
        if spec is not None and not spec.replayable:
            return  # a macro is something the user can run again
        canonical = spec.name if spec is not None else str(name)
        now = time.time()
        last = self._last_action
        if last is not None and last[0] == canonical and last[1] == payload:
            if now - last[2] < DEDUPE_SECONDS:
                self._last_action = (canonical, payload, now)
                return  # the dispatcher's debounce re-delivers one interaction
        self._last_action = (canonical, payload, now)
        comment = summary or canonical
        self.record(
            f"cs_dispatch({canonical!r}, {self._render_payload(payload)})",
            comment=str(comment),
        )

    # -- the script --------------------------------------------------------- #

    @staticmethod
    def _render_payload(payload: dict | None) -> str:
        return pprint.pformat(payload or {}, sort_dicts=False, width=72)

    @property
    def script(self) -> str:
        """The recorded steps as a standalone Python macro (may be empty)."""
        if not self.entries:
            return ""
        header = (
            '"""ChiSurf macro, recorded {stamp}.\n'
            "\n"
            "What was clicked and typed, as code: every recorded action is one\n"
            "cs_dispatch call -- edit the payloads, delete steps, add your own.\n"
            '"""'.format(stamp=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        )
        body = "\n".join(entry.render() for entry in self.entries)
        return f"{header}\n\nfrom chisurf.core.actions import dispatch as cs_dispatch\n\n{body}"

    def clear(self) -> None:
        """Forget everything recorded so far."""
        self.entries.clear()
        self._last_action = None

    def save(self, filename: str | os.PathLike) -> str:
        """Write the macro to *filename*; its path."""
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.script, encoding="utf-8")
        return str(path)
