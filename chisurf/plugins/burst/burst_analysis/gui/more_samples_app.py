"""Step 4 of the burst workflow, *More samples*, drawn with emtk.

Further measurements are dropped on the step -- dragged from its Input table (the workspace's
photon streams), or files dropped on the window -- and processed, one short row each, with the
:class:`..more_samples.Recipe` the workflow hands it: the pipeline as the user tuned it on the
first data. The work runs off the UI thread (:class:`..more_samples.SampleQueue`): the shell's busy
overlay shows it and its Stop stops it. Simple: the drop target, the table and Run. Advanced: the
recipe, part by part, and Re-run of the selected sample. Nothing in it imports Qt.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput
from chisurf.plugins.emtk_layout import button_row

from ..more_samples import Recipe, SampleQueue, register_sample, sample_cells, sample_tip

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent


class BurstMoreSamplesApp(TourTarget, ImApp):
    """The further measurements of a burst workflow and their processing (emtk; no Qt).

    Parameters
    ----------
    recipe_provider : callable, optional
        Returns the workflow's :class:`Recipe` as the steps are set now (the hub captures it).
    on_change : callable, optional
        Called on the UI thread when a sample finished (the hub updates its rail).
    """

    #: The plugin whose manifest ``accepts`` ``photons`` the Input section feeds.
    WORKSPACE_PLUGIN = "burst_analysis"

    def __init__(
        self,
        *,
        recipe_provider: Callable[[], Recipe | None] | None = None,
        on_change: Callable[[], Any] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.recipe_provider = recipe_provider
        self.on_change = on_change
        self._on_guide = on_guide
        self._on_help = on_help
        self.queue = SampleQueue()
        self.queue.on_change = self._wake
        #: The recipe shown (and the one the last run used, if it changed since).
        self.recipe: Recipe | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.selected_path: str | None = None
        #: Highlighted while workspace data is dragged over the table.
        self.drop_target: str | None = None
        self.message = ""
        #: Called from the worker when a sample changes (a hub wakes its frame loop).
        self.on_wake: Callable[[], Any] | None = None
        self.form = FormState()
        self._spec_full = load_view_spec(str(HERE / "more_samples.view.json"))
        self.spec = self._mode_spec(False)
        from chisurf.core.plugin.workspace_input import input_section, spec_for
        from chisurf.emtk.plugins import manifest

        self.input = NamedWorkspaceInput(self.WORKSPACE_PLUGIN, "photons", app=self)
        found = spec_for(manifest(self.WORKSPACE_PLUGIN), kind="photons")
        section = input_section(found[1], title="Workspace data") if found else None
        if section is not None:
            for table in section.get("sections", []):
                if (table.get("options") or {}).get("source") == "workspace_input_rows":
                    table["description"] = (
                        "The photon streams in the workspace. Drag a row (a group is one row) "
                        "into the Samples table below, or right-click it › Add to this tool: it "
                        "is processed as the first data was."
                    )
        self.input_spec = {"sections": [section]} if section else {"sections": []}
        self.input_form = FormState()
        self.help_window = EmTkHelpWindow(
            title="More samples - Help", resource=HERE / "more_samples_help.md", owner=self,
            on_start_guide=self.start_guide, size=(680.0, 500.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "more_samples_guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(gui=self._render, continuous=False)

    #: The workflow's Simple / Advanced mode (standalone: Advanced).
    advanced = False

    def _mode_spec(self, advanced: bool) -> dict:
        """The spec of a mode: Simple has the samples table only, without Re-run."""
        spec = copy.deepcopy(self._spec_full)
        sections = []
        for section in spec["sections"]:
            if section.pop("advanced", False) and not advanced:
                continue
            options = section.get("options") or {}
            menu = []
            for item in options.get("context_menu") or []:
                if item.pop("advanced", False) and not advanced:
                    continue
                menu.append(item)
            if "context_menu" in options:
                options["context_menu"] = menu
            sections.append(section)
        spec["sections"] = sections
        return spec

    def set_advanced(self, advanced: bool) -> None:
        """Simple: the drop target, the table and Run; Advanced: the recipe and Re-run too."""
        if bool(advanced) != self.advanced or not self.spec:
            self.advanced = bool(advanced)
            self.spec = self._mode_spec(self.advanced)
            self.form.tables.clear()  # bound again with the mode's sections

    # -- tour / help ---------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        if callable(self._on_guide):
            self._on_guide()
        else:
            self.tour.start()

    def show_help(self) -> None:
        if callable(self._on_help):
            self._on_help()
        else:
            self.help_window.show()

    def track(self, name: str) -> None:
        self.tour.notify_used(name)

    def _wake(self) -> None:
        self.wants_frame = True
        if callable(self.on_wake):
            try:
                self.on_wake()
            except Exception:  # noqa: BLE001 - the next frame shows it
                pass

    # -- the recipe ------------------------------------------------------------------------------ #
    def refresh_recipe(self) -> Recipe | None:
        """The recipe as the steps are set now (kept when the workflow cannot say)."""
        if callable(self.recipe_provider):
            try:
                recipe = self.recipe_provider()
            except Exception as exc:  # noqa: BLE001 - the last one stays, the line says why
                log.debug("capturing the recipe", exc_info=True)
                self.message = f"The recipe could not be read: {exc}"
                recipe = None
            if recipe is not None:
                self.recipe = recipe
        return self.recipe

    def set_recipe(self, recipe: Recipe | None) -> None:
        self.recipe = recipe

    def recipe_rows(self) -> list[dict]:
        return self.recipe.detail_rows() if self.recipe is not None else []

    # -- the samples ----------------------------------------------------------------------------- #
    def _paths(self) -> list[Path]:
        return [Path(p) for p in self.queue.paths()]

    def take_photons(self, paths, uids=()) -> int:
        """Further measurements from the workspace (the step's Input section, a drop on the window
        while the step is open); returns how many were added."""
        added = self.queue.add([Path(str(p)) for p in paths], [str(u or "") for u in uids])
        self.message = "" if added else tr("Nothing new to add (already in the list).")
        if added:
            self.track("samples")
        self.wants_frame = True
        return added

    def sample_rows(self) -> list[dict]:
        rows = []
        for sample in self.queue.samples:
            rows.append({"path": sample["path"], **sample_cells(sample), "tip": sample_tip(sample)})
        return rows

    def select_sample(self, record) -> None:
        self.selected_path = record.get("path") if isinstance(record, dict) else None

    def remove_sample(self, record) -> None:
        path = record.get("path") if isinstance(record, dict) else None
        if path and self.queue.remove(path):
            if self.selected_path == path:
                self.selected_path = None

    def rerun_sample(self, record=None) -> bool:
        """Advanced: process one sample again with the recipe as it is now."""
        path = (record or {}).get("path") if isinstance(record, dict) else self.selected_path
        if not path:
            return False
        return self.run(only=[path])

    # -- running --------------------------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        return self.queue.running

    @property
    def progress(self) -> tuple[int, int]:
        return self.queue.progress

    @property
    def status_text(self) -> str:
        """What the busy card says while the samples are processed."""
        return self.queue.message()

    def stop(self) -> None:
        self.queue.stop()

    def run(self, only=None) -> bool:
        """Process every sample that is not done (or *only* these) with the recipe as it is now;
        ``False`` when nothing started."""
        recipe = self.refresh_recipe()
        if recipe is None or not recipe.ready:
            self.message = tr("No recipe yet: run 3. Burst MLE on the first data first.")
            return False
        started = self.queue.start(recipe, only=only)
        if not started and not self.running:
            self.message = tr("Nothing to process: every sample is done (Advanced: Re-run one).")
        else:
            self.message = ""
            self.track("run")
        return started

    def run_step(self) -> bool:
        """The workflow hub's Next / fast-forward: process the samples (nothing when there are none)."""
        if not self.queue.samples:
            return False
        return self.run()

    def poll(self) -> None:
        """On the UI thread: the samples finished since the last frame enter the workspace."""
        finished = self.queue.poll()
        for sample in finished:
            register_sample(sample)
        if finished and callable(self.on_change):
            self.on_change()

    def done_count(self) -> int:
        return self.queue.counts().get("done", 0)

    # -- drawing --------------------------------------------------------------------------------- #
    def _draw_recipe_line(self) -> None:
        recipe = self.recipe
        text = recipe.summary() if recipe is not None else tr("No recipe yet: run 3. Burst MLE first.")
        im.text_disabled(tr("Recipe") + ": " + text)
        im.set_item_tooltip(
            (recipe.details() if recipe is not None else "")
            + "\n\n" + tr("Read-only: what every sample goes through, taken from the steps as they "
                          "are set now. Change a step, and the recipe follows.")
        )
        self.remember("recipe")

    def _draw_actions(self) -> None:
        counts = self.queue.counts()
        todo = counts.get("queued", 0) + counts.get("failed", 0)
        ready = self.recipe is not None and self.recipe.ready
        running = self.running
        buttons = [
            {
                "label": "Stop" if running else "Run",
                "key": "run",
                "enabled": running or (bool(todo) and ready),
                "tip": tr("Stop after the step each running sample is in.") if running else (
                    tr("Process the queued (and failed) samples with the recipe.")
                    if todo and ready else (
                        tr("Run 3. Burst MLE on the first data first.") if not ready
                        else tr("Add samples first: drag workspace data into the table.")
                    )
                ),
            },
        ]
        if self.advanced:
            selected = self.selected_path is not None and not running
            buttons += [
                {"label": "Re-run", "key": "rerun", "enabled": selected and ready,
                 "tip": tr("Process the selected sample again with the current recipe.")
                 if selected else tr("Select a sample first.")},
                {"label": "Remove", "key": "remove", "enabled": selected,
                 "tip": tr("Take the selected sample out of the list (its results stay).")},
                {"label": "Clear", "key": "clear", "enabled": bool(self.queue.samples) and not running,
                 "tip": tr("Take every sample out of the list (their results stay).")},
            ]
        pressed = button_row(buttons, remember=self.remember)
        if pressed == "run":
            if running:
                self.stop()
            else:
                self.run()
        elif pressed == "rerun":
            self.rerun_sample()
        elif pressed == "remove" and self.selected_path:
            self.remove_sample({"path": self.selected_path})
        elif pressed == "clear":
            self.queue.clear()
            self.selected_path = None
        done = counts.get("done", 0)
        if self.queue.samples:
            im.same_line()
            im.text_disabled(
                tr("{done}/{n} done").format(done=done, n=len(self.queue.samples))
                + (" · " + tr("{n} failed").format(n=counts["failed"]) if counts.get("failed") else "")
            )
            self.remember("counts")

    def _render(self) -> None:
        self.poll()
        if self.recipe is None:
            self.refresh_recipe()
        self.input.workspace_input_on_used = self.track
        self.input_form.rects.clear()
        draw_form(self.input_spec, self.input, self.input_form)
        for name, rect in self.input_form.rects.items():
            self.item_rects[name] = tuple(rect)
        im.separator()
        if self.message:
            im.text(self.message)
        im.text_disabled(tr("Drag measurements here ↓"))
        im.set_item_tooltip(tr(
            "Drag workspace data into the table below, or drop files on the window while this step "
            "is open: each is processed exactly as the first data was."
        ))
        self.remember("drag_hint")
        draw_sections(self.spec["sections"][:1], self, self.form)
        if "data_table" in self.form.rects:
            self.item_rects["samples"] = tuple(self.form.rects["data_table"])
        self._draw_actions()
        if self.advanced:
            im.separator()
            self._draw_recipe_line()
        if self.advanced and len(self.spec["sections"]) > 1:
            draw_sections(self.spec["sections"][1:], self, self.form)
        w, h = im.get_main_viewport().size
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))
        if self.tour.active:
            self.tour.draw(float(w), float(h))
        if self.running:
            self.wants_frame = True

    # -- persistence ----------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        return {
            "samples": self.queue.export(),
            "recipe": self.recipe.to_payload() if self.recipe is not None else None,
        }

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        if not self.running:
            self.queue.restore(state.get("samples"))
        if state.get("recipe"):
            try:
                self.recipe = Recipe.from_payload(state["recipe"])
            except ValueError:
                self.recipe = None

    def close(self) -> None:
        self.queue.stop()


def make_app(**kwargs) -> BurstMoreSamplesApp:
    """The step alone."""
    from chisurf.emtk.i18n import install

    install()
    return BurstMoreSamplesApp(**kwargs)


__all__ = ["BurstMoreSamplesApp", "make_app"]
