"""What every panel of the native MMFDB Admin shares (Qt-free)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def cell(value: Any) -> Any:
    """A record value as a table cell: text for ``None`` and containers, numbers kept."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return value


def rows_of(items: Any, keys: tuple[str, ...] | list[str], key: str = "") -> list[dict]:
    """Table rows of *items* (dicts) over *keys*; ``_row`` numbers them, *key* names a row."""
    out = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        row = {k: cell(item.get(k)) for k in keys}
        row["_row"] = str(item.get(key, i)) if key else str(i)
        out.append(row)
    return out


class Panel:
    """One destination of the rail: a model the panel's spec section is drawn over.

    ``admin`` is the :class:`~.model.AdminModel` (the client, the call runner,
    the status line, the dialogs and the jumps between panels). A panel loads
    its data the first time it is opened (:meth:`ensure_loaded`) and again on
    :meth:`refresh` (the toolbar's Refresh, the panel's own).
    """

    key = ""
    name = ""
    icon = ""
    description = ""
    #: The ``view.json`` panel that draws it (default: its key).
    spec = ""

    def __init__(self, admin: Any) -> None:
        self.admin = admin
        self.loaded = False
        #: The panel's own message line (a result, a refusal); empty: nothing to say.
        self.message = ""

    # ── plumbing ───────────────────────────────────────────────────────
    @property
    def client(self) -> Any:
        return self.admin.client

    def run(
        self,
        label: str,
        fn: Callable[[], Any],
        done: Callable[[Any], None] | None = None,
        failed: Callable[[str], None] | None = None,
        redact: tuple[str, ...] = (),
    ) -> None:
        """Run *fn* (server calls) off the drawing thread; *done* applies its result."""
        self.admin.run(label, fn, done, failed, redact)

    def say(self, text: str) -> None:
        """Show *text* on the panel's message line and the window's status bar."""
        self.message = text
        self.admin.set_status(text)

    def failed(self, what: str) -> Callable[[str], None]:
        """A failure callback that says ``"<what> failed: <reason>"``."""
        return lambda error: self.say(f"{what} failed: {error}")

    # ── lifecycle ──────────────────────────────────────────────────────
    def ensure_loaded(self) -> None:
        if not self.loaded and self.admin.connected:
            self.loaded = True
            self.refresh()

    def refresh(self) -> None:
        """Fetch the panel's data again."""

    def status_line(self) -> str:
        """What the window's status bar says while this panel is open."""
        return self.message

    def enabled(self, name: str) -> bool:  # noqa: ARG002 - view_form hook
        """Every action needs a connection (the server enforces the rest)."""
        return self.admin.connected

    def message_text(self) -> str:
        return self.message
