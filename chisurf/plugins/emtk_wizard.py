"""The stepper of a wizard without a toolkit: steps, Back / Next / Finish, completion marks, the navigation list.

The Qt wizard is an AutoForm ``wizard`` section: a navigation list with a check mark for every completed step, a header
(title and subtitle) and a page per step, and a Back / Next bar with Finish on the last step. :class:`Stepper` is that
state as a mixin for a view model; :func:`draw_steps` draws the navigation list. The page of each step is a panel of the
plugin's own spec drawn by :func:`emtk.view_form.draw_sections`.

A model that mixes :class:`Stepper` in sets ``STEPS`` and calls :meth:`Stepper.init_steps` from its ``__init__``.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from emtk import im

logger = logging.getLogger(__name__)


class Step(NamedTuple):
    """One wizard step as the plugin's Qt ``*.view.json`` declares it."""

    id: str
    title: str
    subtitle: str
    #: Attribute of the model that says the step is done; ``None``: complete as soon as it exists.
    complete_when: str | None = None
    #: An optional step counts as complete.
    optional: bool = False


class Stepper:
    """Current step, Back / Next / Finish and the completion marks of a wizard."""

    STEPS: tuple[Step, ...] = ()

    def init_steps(self) -> None:
        """Start on the first step; call from ``__init__``."""
        self.step = 0
        #: Set by Finish: the application closes its window.
        self.finished = False
        self._complete: list[bool] = [False] * len(self.STEPS)
        self.refresh_completion()

    # -- steps ------------------------------------------------------------------------------------------------------- #
    @property
    def current(self) -> Step:
        return self.STEPS[self.step]

    @property
    def step_id(self) -> str:
        return self.current.id

    @property
    def title(self) -> str:
        return self.current.title

    @property
    def subtitle(self) -> str:
        return self.current.subtitle

    @property
    def is_first(self) -> bool:
        return self.step <= 0

    @property
    def is_last(self) -> bool:
        return self.step >= len(self.STEPS) - 1

    def on_step(self, index: int) -> None:
        """Hook: step *index* was entered (a model reloads what the page shows)."""

    def go_to(self, index: int) -> None:
        """Select step *index* (clamped), as a click on the navigation list does."""
        index = max(0, min(len(self.STEPS) - 1, int(index)))
        if index != self.step:
            self.step = index
            self.on_step(index)
            self.refresh_completion()
            notify = getattr(self, "notify", None)
            if callable(notify):
                notify("step")

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

    # -- completion -------------------------------------------------------------------------------------------------- #
    def step_complete(self, index: int) -> bool:
        """Whether step *index* shows a check mark: optional, no condition, or its condition holds."""
        step = self.STEPS[index]
        if step.optional or step.complete_when is None:
            return True
        return bool(self._complete[index])

    def refresh_completion(self) -> None:
        """Re-evaluate the completion of the steps that have a condition."""
        for index, step in enumerate(self.STEPS):
            if step.complete_when is None or step.optional:
                self._complete[index] = True
                continue
            try:
                self._complete[index] = bool(getattr(self, step.complete_when))
            except Exception:
                logger.debug("completion of %s failed", step.id, exc_info=True)
                self._complete[index] = False

    def navigation(self) -> list[dict[str, Any]]:
        """The navigation list: ``label`` (a check mark when done), ``current`` and ``tooltip``."""
        return [
            {
                "index": i,
                "label": ("✓ " if self.step_complete(i) else "  ") + step.title,
                "title": step.title,
                "complete": self.step_complete(i),
                "current": i == self.step,
                "tooltip": step.subtitle,
            }
            for i, step in enumerate(self.STEPS)
        ]

    # -- persistence ------------------------------------------------------------------------------------------------- #
    def export_step(self) -> dict:
        """What is remembered of the stepper: the current step (the Qt wizard stores ``<key>/step``)."""
        return {"step": int(self.step)}

    def restore_step(self, settings: dict) -> None:
        """Restore :meth:`export_step`; an unusable value starts at the first step."""
        try:
            index = int(settings.get("step", 0))
        except (TypeError, ValueError, AttributeError):
            index = 0
        self.step = max(0, min(len(self.STEPS) - 1, index))
        self.on_step(self.step)
        self.refresh_completion()


def draw_steps(model: Stepper, rects: dict, on_pick=None, name: str = "nav_list") -> None:
    """Draw the navigation list; a click selects the step. The current row's rectangle goes to ``rects[name]``.

    Parameters
    ----------
    model : Stepper
    rects : dict
        The app's ``item_rects``; every row is also registered as ``step_<id>``.
    on_pick : callable, optional
        Called with the step index after a click (a tour learns that the user picked a step).
    """
    for item in model.navigation():
        if im.selectable(item["label"] + f"##step{item['index']}", item["current"]):
            model.go_to(item["index"])
            if callable(on_pick):
                on_pick(item["index"])
        im.set_item_tooltip(item["tooltip"])
        rects[f"step_{model.STEPS[item['index']].id}"] = im.get_item_rect()
        if item["current"]:
            rects[name] = im.get_item_rect()


__all__ = ["Step", "Stepper", "draw_steps"]
