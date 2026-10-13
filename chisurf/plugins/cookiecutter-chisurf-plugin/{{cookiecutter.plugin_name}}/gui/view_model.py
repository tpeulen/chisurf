"""State of the {{ cookiecutter.plugin_display_name }} window, bound by ``{{ cookiecutter.plugin_name }}.view.json``.

Toolkit-free: attributes are what ``value`` sections edit, methods are what ``button_row`` actions
call and what ``info`` sections read. The numbers come from the backend through
:class:`~.client.{{ cookiecutter.class_prefix }}Client` -- never from ``..core`` directly -- so the same
window works against an in-process backend, a server, or a fake in a test.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class {{ cookiecutter.class_prefix }}ViewModel:
    """What the window shows and edits.

    Parameters
    ----------
    client : {{ cookiecutter.class_prefix }}Client, optional
        The backend client; created on first use when omitted.
    """

    def __init__(self, client: Any = None) -> None:
        self._client = client
        #: Edited by the ``example_number`` value section.
        self.example_number = 1.0
        #: The last result, or ``None`` before the first run.
        self.result: float | None = None
        #: One line under the buttons: what the last action did, or why it failed.
        self.status = "Ready."
        #: Set by the app: open the help window / start the guided tour.
        self.on_help: Callable[[], Any] | None = None
        self.on_guide: Callable[[], Any] | None = None

    @property
    def client(self) -> Any:
        """The backend client (created on first use)."""
        if self._client is None:
            from .client import {{ cookiecutter.class_prefix }}Client

            self._client = {{ cookiecutter.class_prefix }}Client()
        return self._client

    # -- actions (button_row) ---------------------------------------------------------------- #
    def run(self) -> None:
        """*Run*: ask the backend for the result of the current settings."""
        try:
            self.result = float(self.client.compute({"example_number": self.example_number}))
            self.status = f"Done: {self.result:g}"
        except Exception as error:  # noqa: BLE001 - shown in the window, never raised into the frame
            self.status = f"Failed: {error}"

    def open_help(self) -> None:
        """*?*: the help page (``help.md``)."""
        if self.on_help is not None:
            self.on_help()

    def start_guide(self) -> None:
        """*Guide*: the guided tour (``guide.json``)."""
        if self.on_guide is not None:
            self.on_guide()

    # -- info sources ------------------------------------------------------------------------ #
    def result_text(self) -> str:
        """The result panel."""
        if self.result is None:
            return "Press Run to compute the result."
        return f"Result: {self.result:g}"

    def status_text(self) -> str:
        """The status line."""
        return self.status

    # -- persistence ------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered between sessions."""
        return {"example_number": self.example_number}

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`; an unusable value is ignored."""
        try:
            self.example_number = float(state.get("example_number", self.example_number))
        except (TypeError, ValueError):
            pass


__all__ = ["{{ cookiecutter.class_prefix }}ViewModel"]
