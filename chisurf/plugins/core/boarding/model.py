"""Qt-free state of the onboarding wizard drawn by :mod:`.app`.

The Qt wizard is an AutoForm ``wizard`` section: eight steps in a navigation list with a check
mark for each completed step, a Back / Next bar and a Finish button on the last step. This model
is that stepper without a toolkit. It extends :class:`~.view_model.BoardingViewModel`, which
already holds the texts, the settings-folder actions (create missing files, restore defaults,
update experiments) and the completion booleans, so the Qt wizard and this one cannot drift
apart: both read and write the same files through :mod:`.utils`.

What differs from the Qt model is only what a Qt-free app must do differently:

* the actions that open another window (settings editor, Help, Plugin Manager) go through a
  ``host`` callable the embedding application supplies, and say where to find the window when
  there is none;
* *Restore defaults* asks before it replaces the user's settings (the Qt button did not);
* the completion of a step is computed when something may have changed and kept, so drawing a
  frame never queries the metadata store.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, NamedTuple

from . import utils
from .view_model import BoardingViewModel

logger = logging.getLogger(__name__)


class Step(NamedTuple):
    """One wizard step as ``boarding.view.json`` declares it for the Qt wizard."""

    id: str
    title: str
    subtitle: str
    #: Attribute of the model that says the step is done; ``None`` means always complete.
    complete_when: str | None = None
    #: An optional step counts as complete.
    optional: bool = False


#: The steps, in the order and with the titles and subtitles of the Qt wizard.
STEPS: tuple[Step, ...] = (
    Step("welcome", "Welcome", "A quick guided setup for a new ChiSurf installation."),
    Step(
        "settings",
        "Settings",
        "Review your user settings files; open the editor when needed.",
        "settings_ok",
    ),
    Step(
        "fix",
        "Fix / Initialize",
        "Create missing settings files or restore packaged defaults.",
    ),
    Step(
        "experiments",
        "Experiments",
        "Update experiment/model configuration so new models appear.",
    ),
    Step(
        "dependencies",
        "Dependencies",
        "Check optional Python packages used by specific features.",
    ),
    Step(
        "detector",
        "Detector setup",
        "Configure PIE / channel windows for TTTR workflows.",
        "has_detector_setups",
    ),
    Step(
        "fcs",
        "FCS channels",
        "Define which channels/pairs to correlate for FCS workflows.",
        "has_fcs_setups",
    ),
    Step("finish", "Finish", "You are ready to start working.", optional=True),
)

#: What the buttons that open another window say when the embedding application has no host.
_WHERE = {
    "settings_editor": "Open the settings editor from the Settings entry of the ChiSurf main window.",
    "help": "Open Help from the Help menu of the ChiSurf main window.",
    "plugin_manager": "Open the Plugin Manager from the Help or Plugins menu of the ChiSurf main window.",
}

#: Prompt kinds of :attr:`BoardingModel.confirm`.
RESTORE = "restore"


class BoardingModel(BoardingViewModel):
    """The onboarding wizard: current step, completion, confirmation and the host hook.

    Parameters
    ----------
    host : callable, optional
        ``host(kind) -> bool`` with ``kind`` one of ``"settings_editor"``, ``"help"``,
        ``"plugin_manager"``: opens that window of the embedding application and returns
        whether it did. Without one the action only says where the window is.
    """

    def __init__(self, host: Callable[[str], bool] | None = None) -> None:
        super().__init__()
        self.host = host
        #: Index of the current step.
        self.step = 0
        #: Set by Finish: the application closes its window.
        self.finished = False
        #: The open confirmation (``""`` or :data:`RESTORE`).
        self.confirm = ""
        #: A line under the navigation bar, e.g. what an unavailable window action says.
        self.notice = ""
        self._complete: list[bool] = [False] * len(STEPS)
        self._status_rows: list[dict] = []
        self._deps_rows: list[dict] = []
        self.refresh_completion()
        self.reload_tables()

    # ------------------------------------------------------------------ steps
    @property
    def steps(self) -> tuple[Step, ...]:
        """The steps of the wizard."""
        return STEPS

    @property
    def current(self) -> Step:
        """The current step."""
        return STEPS[self.step]

    @property
    def step_id(self) -> str:
        """Id of the current step."""
        return self.current.id

    @property
    def title(self) -> str:
        """Title of the current step (the header above its page)."""
        return self.current.title

    @property
    def subtitle(self) -> str:
        """Subtitle of the current step."""
        return self.current.subtitle

    @property
    def is_first(self) -> bool:
        """Whether the current step is the first one (Back is unavailable)."""
        return self.step <= 0

    @property
    def is_last(self) -> bool:
        """Whether the current step is the last one (Finish replaces Next)."""
        return self.step >= len(STEPS) - 1

    def go_to(self, index: int) -> None:
        """Select step *index* (clamped), as a click on the navigation list does."""
        index = max(0, min(len(STEPS) - 1, int(index)))
        if index != self.step:
            self.step = index
            self.notice = ""
            self.refresh_completion()
            self.notify("step")

    def go_back(self) -> None:
        """Back: the previous step; nothing on the first one."""
        self.go_to(self.step - 1)

    def go_next(self) -> None:
        """Next: the following step; nothing on the last one (the wizard is not linear)."""
        self.go_to(self.step + 1)

    def finish(self) -> None:
        """Finish: only on the last step; asks the application to close the wizard."""
        if self.is_last:
            self.finished = True
            self.notify("finish")

    def enabled(self, action: str) -> bool:
        """Whether the button *action* may be pressed now (the form greys it otherwise)."""
        if action == "go_back":
            return not self.is_first
        return True

    # ------------------------------------------------------------ completion
    def step_complete(self, index: int) -> bool:
        """Whether step *index* shows a check mark: optional, no condition, or its condition holds."""
        step = STEPS[index]
        if step.optional or step.complete_when is None:
            return True
        return bool(self._complete[index])

    def refresh_completion(self) -> None:
        """Re-evaluate the completion of the steps that have a condition."""
        for index, step in enumerate(STEPS):
            if step.complete_when is None or step.optional:
                self._complete[index] = True
                continue
            try:
                self._complete[index] = bool(getattr(self, step.complete_when))
            except Exception:
                logger.debug("boarding: completion of %s failed", step.id, exc_info=True)
                self._complete[index] = False

    def navigation(self) -> list[dict[str, Any]]:
        """The navigation list: ``label`` (with a check mark when done), ``current``, ``tooltip``."""
        return [
            {
                "index": i,
                "label": ("\u2713 " if self.step_complete(i) else "  ") + step.title,
                "title": step.title,
                "complete": self.step_complete(i),
                "current": i == self.step,
                "tooltip": step.subtitle,
            }
            for i, step in enumerate(STEPS)
        ]

    # ------------------------------------------------------------------ tables
    def reload_tables(self) -> None:
        """Read the settings-status and dependency tables again (the Refresh buttons)."""
        self._status_rows = utils.status_cells()
        self._deps_rows = utils.deps_cells()

    def status_rows(self) -> list[dict]:
        """Rows of the settings-status table: ``item``, ``status``, ``detail``."""
        return self._status_rows

    def deps_rows(self) -> list[dict]:
        """Rows of the optional-dependency table: ``module``, ``status``, ``purpose``."""
        return self._deps_rows

    def refresh(self) -> None:
        """Refresh button: re-check settings files, dependencies and the step marks."""
        self.reload_tables()
        self.refresh_completion()
        super().refresh()

    def _set_repair_status(self, ok: bool, msg: str) -> None:
        super()._set_repair_status(ok, msg)
        self.reload_tables()
        self.refresh_completion()

    # ------------------------------------------------------------ confirmation
    def restore_question(self) -> str:
        """The text of the confirmation Restore defaults asks."""
        return (
            "Replace your current settings files in the user settings folder with the packaged "
            "defaults? Settings you changed there are lost."
        )

    def request_restore(self) -> None:
        """Restore defaults: ask first, because it replaces the user's settings files."""
        self.confirm = RESTORE

    def confirm_yes(self) -> None:
        """Carry out the open confirmation."""
        kind, self.confirm = self.confirm, ""
        if kind == RESTORE:
            self.overwrite_defaults()

    def confirm_no(self) -> None:
        """Decline the open confirmation: nothing changes."""
        self.confirm = ""

    # ------------------------------------------------------- other windows
    def _open(self, kind: str) -> None:
        opened = False
        if callable(self.host):
            try:
                opened = bool(self.host(kind))
            except Exception:
                logger.warning("boarding: host could not open %s", kind, exc_info=True)
        self.notice = "" if opened else _WHERE[kind]

    def open_settings_editor(self) -> None:
        """Open the settings editor through the host, or say where it is."""
        self._open("settings_editor")

    def open_help(self) -> None:
        """Open the help browser through the host, or say where it is."""
        self._open("help")

    def open_plugin_manager(self) -> None:
        """Open the Plugin Manager through the host, or say where it is."""
        self._open("plugin_manager")

    # ------------------------------------------------------------ persistence
    def export_settings(self) -> dict:
        """What is remembered: the current step (the Qt wizard stores it as ``<key>/step``)."""
        return {"step": int(self.step)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; an unusable value starts at the first step."""
        try:
            index = int(settings.get("step", 0))
        except (TypeError, ValueError, AttributeError):
            index = 0
        self.step = max(0, min(len(STEPS) - 1, index))
        self.refresh_completion()


__all__ = ["BoardingModel", "Step", "STEPS", "RESTORE"]
