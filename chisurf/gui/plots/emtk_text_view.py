r"""A read-only emtk text view with the plain-text call surface.

The fit Info page's report and the Export tab's mmCIF preview are emtk's
read-only :class:`~emtk.widgets.text_editor.TextEditor`. This wrapper is no
widget: it is the editor plus the ``setPlainText``/``toPlainText`` spelling the
code that fills it (and the tests that read it) use, and a refresh target so a
new text is drawn without waiting for input. Whatever draws it -- the fit
window's surface, the *Plot settings* dock -- hosts :attr:`editor` (or the view
itself: it forwards the control contract to the editor).

A read-only emtk editor still selects, copies, searches and scrolls, which is
exactly what a fit report needs.
"""

from __future__ import annotations

from typing import Any, Callable


class EmtkTextView:
    """A read-only text view drawn by emtk."""

    def __init__(self) -> None:
        from emtk.widgets.text_editor import TextEditor

        self.editor = TextEditor("", None, read_only=True)
        # A report is not code: no gutter numbers, no highlighted line.
        self.editor.config.show_line_numbers = False
        self.editor.config.highlight_current_line = False
        self.editor.config.show_matching_brackets = False
        self._refresh_target: Callable[[], None] | None = None

    # -- the plain-text surface ----------------------------------------------
    def setPlainText(self, text: str) -> None:  # noqa: N802 - the text-edit spelling
        """Replace the text."""
        self.editor.set_text(str(text))
        if self._refresh_target is not None:
            self._refresh_target()

    def toPlainText(self) -> str:  # noqa: N802 - the text-edit spelling
        """The text."""
        return self.editor.text

    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send repaint requests to *callback* (the surface that draws the editor)."""
        self._refresh_target = callback

    # -- the control contract: the editor's own ---------------------------------
    def __getattr__(self, name: str) -> Any:
        if name == "editor":
            raise AttributeError(name)
        return getattr(self.editor, name)
