"""The window shell the structure-tool cards share: toolbar, status line, in-app dialogs, help window and guided tour.

A card (FPS JSON editor, docking, QuEst) is an ``ImApp`` drawn inside the Structure Tools hub or on its own. Each
one needs the same few things, so they live here once: a file chooser dialog (:class:`emtk.file_dialog.FileDialog`
in an :class:`emtk.dialog_window.DialogWindow`), a yes/no question, a text prompt, a message, the Help window and the
guided tour wired to the controls the card remembers in :attr:`item_rects`, and the host's drop verb.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import button_row


class CardShell(TourTarget, ImApp):
    """Base of a Structure Tools card.

    Parameters
    ----------
    title : str
        Window caption (also the title of its Help window).
    folder : pathlib.Path
        Where ``help.md`` and ``guide.json`` live.
    key : str
        Distinguishes the card's dock window and dialogs from another card's.
    """

    def __init__(self, title: str, folder: Path, key: str) -> None:
        self.title = title
        self.folder = Path(folder)
        self.card_key = key      # not `key`: that name is the host's keyboard entry point (ImApp.key)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.status = ""
        self.status_error = False
        self.dialog: FileDialog | None = None
        self.dialog_window = DialogWindow("Choose a file", size=(640.0, 420.0), key=f"{key}-file")
        self._on_pick: Callable[[str], Any] | None = None
        self._on_cancel: Callable[[], Any] | None = None
        #: The open question / message / prompt, or None: ``{"kind", "title", "text", ...}``.
        self.modal: dict | None = None
        self.modal_window = DialogWindow("Question", size=(460.0, 190.0), key=f"{key}-modal")
        self.docks = self.build_docks()
        self.native_layouts = {"main": self.docks}
        self.help_window = EmTkHelpWindow(
            title=f"{title} — Help", resource=self.folder / "help.md", owner=self,
            on_start_guide=self.start_guide, size=(680.0, 500.0),
        )
        self.tour = EmTkGuidedTour(
            steps=self.folder / "guide.json", get_target_rect=lambda k: self.item_rects.get(k),
            owner=self, wait_for_controls=True,
        )
        super().__init__(gui=self.render, continuous=False)

    def build_docks(self) -> DockManager:
        """The card's windows: one by default; a card with an input and a results side overrides this."""
        docks = DockManager(Region("main"))
        docks.add_window("main", self.title, self._draw_main, dock="main", closable=False)
        return docks

    # ── messages ──────────────────────────────────────────────────────────

    def say(self, text: str, error: bool = False) -> None:
        """The status line: what the last action did, or why it did not."""
        self.status, self.status_error = text, error
        self.request_frame()

    def used(self, name: str) -> None:
        """Tell the guided tour that the control *name* was used."""
        self.tour.notify_used(name)

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    # ── dialogs ───────────────────────────────────────────────────────────

    def choose_file(self, dialog: FileDialog, on_pick: Callable[[str], Any],
                    on_cancel: Callable[[], Any] | None = None) -> None:
        """Open *dialog* over the card; ``on_pick(path)`` gets the choice."""
        self.dialog, self._on_pick, self._on_cancel = dialog, on_pick, on_cancel
        self.dialog_window.title = dialog.title
        self.dialog_window.show()
        self.request_frame()

    def open_file(self, title: str, filters: str, on_pick: Callable[[str], Any], current: str = "",
                  folder: bool = False) -> None:
        """Ask for an existing file (or folder), starting where *current* is."""
        start = current if folder and os.path.isdir(current or "") else os.path.dirname(current or "")
        self.choose_file(FileDialog(title, mode="folder" if folder else "open", filters=filters,
                                    directory=start or None), on_pick)

    def save_file(self, title: str, filters: str, on_pick: Callable[[str], Any], filename: str = "",
                  directory: str = "") -> None:
        """Ask where to write (an existing file is only replaced after the dialog's own question)."""
        self.choose_file(FileDialog(title, mode="save", filters=filters, directory=directory or None,
                                    filename=filename), on_pick)

    def ask(self, title: str, text: str, on_yes: Callable[[], Any], yes: str = "Yes", no: str = "No") -> None:
        """A question with a default of *no*: nothing happens unless the user presses *yes*."""
        self.modal = {"kind": "ask", "title": title, "text": text, "yes": yes, "no": no, "on_yes": on_yes}
        self.modal_window.title = title
        self.modal_window.show()
        self.request_frame()

    def notify(self, title: str, text: str) -> None:
        """A message the user closes."""
        self.modal = {"kind": "notify", "title": title, "text": text}
        self.modal_window.title = title
        self.modal_window.show()
        self.request_frame()

    def prompt(self, title: str, label: str, on_ok: Callable[[str], Any], initial: str = "") -> None:
        """A one-line text prompt; OK hands over the stripped text (an empty one is refused)."""
        self.modal = {"kind": "prompt", "title": title, "text": label, "value": initial, "on_ok": on_ok}
        self.modal_window.title = title
        self.modal_window.show()
        self.request_frame()

    @property
    def blocked(self) -> bool:
        """Whether a dialog is over the card (the card behind it takes no input)."""
        return self.dialog is not None or self.modal is not None

    # ── host ──────────────────────────────────────────────────────────────

    def on_files_dropped(self, paths: Sequence[str]) -> bool:
        """The host's drop verb: see :meth:`take_drop`. Always True, the status line has the answer."""
        if not self.blocked:
            self.take_drop([str(p) for p in paths])
        self.request_frame()
        return True

    def take_drop(self, paths: list[str]) -> bool:  # pragma: no cover - overridden
        return False

    # ── frame ─────────────────────────────────────────────────────────────

    def render(self) -> None:
        self.before_frame()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin_disabled(self.blocked)
        top = float(self.toolbar_height())
        if top > 0:
            # A fixed strip above the windows (toolbar, status): the windows below can be rearranged by the user.
            im.set_next_window_pos((box[0], box[1]), im.Cond.ALWAYS)
            im.set_next_window_size((box[2], top), im.Cond.ALWAYS)
            if im.begin(f"##{self.card_key}-toolbar", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
                im.set_cursor_pos((box[0] + 6.0, box[1] + 4.0))  # the dock windows' content padding
                im.indent(6.0)
                self.draw_toolbar((box[0], box[1], box[2], top))
                im.unindent(6.0)
            im.end()
        self.docks.draw((box[0], box[1] + top, box[2], max(box[3] - top, 1.0)))
        im.end_disabled()
        if self.dialog is not None:
            self._draw_file_dialog(box)
        if self.modal is not None:
            self._draw_modal(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def before_frame(self) -> None:
        """Called at the top of every frame (collect finished work)."""

    def toolbar_height(self) -> float:
        """Height of a fixed strip above the dock windows (0: none); a card with movable views draws its toolbar there."""
        return 0.0

    def draw_toolbar(self, box) -> None:  # pragma: no cover - drawn only when toolbar_height() > 0
        """The fixed strip above the windows."""

    def _draw_main(self, box) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _draw_file_dialog(self, box) -> None:
        pressed = self.dialog_window.begin(box)
        result = self.dialog.draw()
        self.dialog_window.end()
        if result:
            pick, self.dialog = self._on_pick, None
            pick(result[0])
        elif result is False or pressed == "close":
            cancel, self.dialog = self._on_cancel, None
            if cancel is not None:
                cancel()

    def _draw_modal(self, box) -> None:
        modal = self.modal
        pressed = self.modal_window.begin(box)
        im.text_wrapped(modal["text"])
        done = None
        entered = False
        if modal["kind"] == "prompt":
            im.set_next_item_width(-1)
            if not modal.get("focused"):  # typed into at once, as Qt's input dialog is
                im.set_keyboard_focus_here()
                modal["focused"] = True
            entered, value = im.input_text(f"##{self.card_key}-prompt", modal["value"],
                                           flags=im.InputTextFlags.ENTER_RETURNS_TRUE)
            modal["value"] = value
            self.remember("prompt", im.get_item_rect())
            im.set_item_tooltip("The name; press OK or Enter.")
            if modal.get("error"):
                im.text_wrapped(modal["error"])
        im.new_line()
        buttons = {
            "ask": [{"label": modal.get("yes", "Yes"), "key": "yes", "tip": "Do it."},
                    {"label": modal.get("no", "No"), "key": "no", "tip": "Leave everything as it is."}],
            "notify": [{"label": "OK", "key": "no", "tip": "Close this message."}],
            "prompt": [{"label": "OK", "key": "yes", "tip": "Accept the name."},
                       {"label": "Cancel", "key": "no", "tip": "Close without adding anything."}],
        }[modal["kind"]]
        choice = button_row(buttons, remember=lambda name: self.remember(f"modal_{name}"))
        self.modal_window.end()
        if modal["kind"] == "prompt" and entered:
            choice = "yes"
        if pressed == "close":
            choice = "no"
        if choice == "yes":
            if modal["kind"] == "prompt":
                value = modal["value"].strip()
                if not value:
                    modal["error"] = "Enter a name first."
                    return
                done = lambda: modal["on_ok"](value)  # noqa: E731
            else:
                done = modal["on_yes"]
        if choice is not None:
            self.modal = None
            if done is not None:
                done()

    # ── helpers for the cards ─────────────────────────────────────────────

    def toolbar(self, buttons: Sequence[dict]) -> str | None:
        """A row of buttons that wraps; the key of the one pressed (remembered for the tour)."""
        return button_row(buttons, remember=self.remember)

    def help_buttons(self) -> list[dict]:
        return [
            {"label": "Guide", "key": "guide", "tip": "A step-by-step walk through the tool, pointing at each control."},
            {"label": "Help", "key": "help", "tip": "What the tool does, what it writes, and its limits."},
        ]

    def status_line(self) -> None:
        """The status line under the card's content: red when it reports a failure."""
        if not self.status:
            return
        if self.status_error:
            from emtk.im_core import Col

            im.push_style_color(Col.TEXT, (235, 90, 80, 255))
        im.text_wrapped(self.status)
        if self.status_error:
            im.pop_style_color(1)
        self.remember("status")

    def animating(self) -> bool:
        return super().animating()

    def close(self) -> None:
        """Release what the card holds (subclasses stop their workers first)."""
