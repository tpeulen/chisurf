"""Native EMTK F-test and chi-square upper-limit calculator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import _CHI2_2_ATTRS, _CHI2_MAX_ATTRS, _CONF_ATTRS, FTestModel

#: The Qt tool's "From fit" menu: three load targets per open fit.
LOAD_TARGETS = (
    ("model1", "→ F-test model 1 (χ²₁, n₁)"),
    ("model2", "→ F-test model 2 (χ²₂, n₂)"),
    ("chi2max", "→ χ²-max (χ²min, params, ν)"),
)


def open_fits() -> list[Any]:
    """Read the same process fit registry as the legacy fitting client."""
    import chisurf

    result = []
    for group in getattr(chisurf, "fits", []):
        try:
            result.extend(iter(group))
        except TypeError:
            result.append(group)
    return result


class FTestApp(ImApp):
    def __init__(
        self, model: FTestModel | None = None, fit_provider: Callable[[], list[Any]] | None = None
    ) -> None:
        self.model = model or FTestModel()
        self.fit_provider = fit_provider or open_fits
        self.fits: list[Any] = []
        self.menu_open = False
        self.status = ""
        self.item_rects = {}
        self.spec = json.loads(Path(__file__).with_name("ftest.view.json").read_text())
        for panel in self.spec["sections"]:
            panel["n_col"] = 2
            panel["collapsible"] = True
            for field in panel["sections"]:
                attr = field["attr"]
                if attr in _CONF_ATTRS:
                    field["call"] = "recompute_conf"
                elif attr in _CHI2_2_ATTRS:
                    field["call"] = "recompute_chi2_2"
                elif attr in _CHI2_MAX_ATTRS:
                    field["call"] = "recompute_chi2_max"
        self.forms = [FormState(), FormState()]
        self.help_window = EmTkHelpWindow(
            title="F-test — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=self.target_rect,
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        for form in self.forms:
            form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("v", 0.58, Region("comparison"), Region("upper_limit")))
        self.docks.add_window(
            "comparison",
            "F-test: compare nested fits",
            self.draw_comparison,
            dock="comparison",
            closable=False,
        )
        self.docks.add_window(
            "upper_limit",
            "Chi-square upper limit",
            self.draw_upper_limit,
            dock="upper_limit",
            closable=False,
        )
        self.refresh_fits()
        super().__init__(self.render, continuous=False)

    def reveal_step(self, index, step):
        target = EmTkGuidedTour._target_key(step.get("target"))
        for panel, form in zip(self.spec["sections"], self.forms):
            if any(field.get("attr") == target for field in panel["sections"]):
                form.folds[panel["title"]] = True

    def target_rect(self, name):
        return self.item_rects.get(name) or next(
            (form.rects[name] for form in self.forms if name in form.rects), None
        )

    def refresh_fits(self) -> None:
        """Re-read the open fits (the Qt menu rebuilds itself each time it opens)."""
        try:
            self.fits = list(self.fit_provider())
            self.status = ""
        except Exception as exc:
            self.fits = []
            self.status = f"Could not read open fits: {exc}"

    def load_fit_into(self, index: int, target: str) -> bool:
        """Copy fit ``index``'s statistics into ``target`` (model1, model2 or chi2max)."""
        if not 0 <= index < len(self.fits):
            self.status = "No such open fit."
            return False
        fit = self.fits[index]
        try:
            self.model.load_fit(fit, target)
        except Exception as exc:
            self.status = f"Could not load fit statistics: {exc}"
            return False
        self.status = ""
        # Previously typed text must not conceal freshly loaded statistics.
        for form in self.forms:
            form.buffers.clear()
        self.tour.notify_used("From fit")
        return True

    def on_paths_dropped(self, paths) -> None:
        if paths:
            self.status = "The F-test calculator takes no dropped files."

    def files_dropped(self, paths) -> bool:
        self.on_paths_dropped(paths)
        return bool(paths)

    def draw_toolbar(self) -> None:
        """The Qt toolbar: the From fit menu, Guide and ?."""
        im.begin_menu_bar()
        opened = im.begin_menu("From fit")
        self.item_rects["From fit"] = im.get_item_rect()
        im.set_item_tooltip("Load n_points / n_free / χ²r from an open fit.")
        if opened:
            if not self.menu_open:
                self.refresh_fits()
            self.menu_open = True
            if not self.fits:
                im.menu_item("(no open fits)", enabled=False)
            for i, fit in enumerate(self.fits):
                name = str(getattr(fit, "name", "fit"))
                for target, label in LOAD_TARGETS:
                    if im.menu_item(f"{name}  {label}"):
                        self.load_fit_into(i, target)
            im.end_menu()
        else:
            self.menu_open = False
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through loading fit statistics and comparing nested models.")
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("?"):
            self.help_window.show()
        im.set_item_tooltip("Explain the F-test, confidence threshold and chi-square upper limit.")
        self.item_rects["help"] = im.get_item_rect()
        im.end_menu_bar()
        if self.status:
            im.text_wrapped(self.status)

    def draw_comparison(self, box) -> None:
        self.draw_toolbar()
        draw_form({"sections": [self.spec["sections"][0]]}, self.model, self.forms[0])

    def draw_upper_limit(self, box) -> None:
        draw_form({"sections": [self.spec["sections"][1]]}, self.model, self.forms[1])

    def render(self) -> None:
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        for form in self.forms:
            form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)


def make_app() -> FTestApp:
    return FTestApp()
