"""Native emtk onboarding wizard: the eight steps of the Qt wizard in one window.

Left window: the step list (a check mark for a completed step, as the Qt navigation list) with
Back / Next / Finish below it and the Help / Guide buttons. Right window: the header of the
current step and its page. Every page is a panel of the view spec ``boarding_emtk.view.json``
drawn by :func:`emtk.view_form.draw_sections`; the two tables are ``data_table`` sections. Only
what a spec cannot express is drawn here: the Markdown texts, the coloured outcome line and the
two shared editors the Qt wizard embeds, the detector setup editor of the Setup: Channel
Definition tool (:class:`~chisurf.plugins.core.setup_channel_definition.gui.app.SetupChannelDefinitionApp`)
and the FCS channel-pair editor of the Setup: FCS Definitions tool
(:class:`~chisurf.plugins.fcs.fcs_channel_preset.gui.app.PresetApp`). Both are hosted, not
copied: the same models, stores and dialogs. All state is in :class:`~.model.BoardingModel`.
Nothing here imports Qt.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import STEPS, BoardingModel
from .strings import install_translations, tr

install_translations()

HERE = Path(__file__).parent
#: Seconds between two re-checks of the step marks while an embedded editor is showing.
RECHECK_SECONDS = 1.5
#: Colours that carry the outcome of an action (green: it worked, red: it did not).
_OK, _FAILED = (0.18, 0.62, 0.22, 1.0), (0.85, 0.2, 0.2, 1.0)


def _default_detector_editor() -> Any:
    """The detector setup editor of the Setup: Channel Definition tool (built on first use)."""
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    return make_app()


def _default_fcs_editor() -> Any:
    """The FCS channel-pair editor of the Setup: FCS Definitions tool (built on first use)."""
    from chisurf.plugins.fcs.fcs_channel_preset.gui.app import create_app

    return create_app()


class BoardingApp(ImApp):
    """First-run onboarding: check, repair and initialise the ChiSurf settings.

    Parameters
    ----------
    model : BoardingModel, optional
    host : callable, optional
        ``host(kind) -> bool`` that opens the settings editor, Help or Plugin Manager of the
        embedding application (see :class:`~.model.BoardingModel`).
    detector_editor, fcs_editor : callable, optional
        Factories of the two embedded editors (default: the shared tools'); the editors are
        built when their step is first shown, as the Qt wizard builds them with its page.
    """

    def __init__(
        self,
        model: BoardingModel | None = None,
        host: Callable[[str], bool] | None = None,
        detector_editor: Callable[[], Any] | None = None,
        fcs_editor: Callable[[], Any] | None = None,
    ) -> None:
        self.model = model or BoardingModel(host=host)
        self._detector_factory = detector_editor or _default_detector_editor
        self._fcs_factory = fcs_editor or _default_fcs_editor
        self.detector: Any = None
        self.fcs: Any = None
        spec = json.loads((HERE / "boarding_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["markdown"] = self._draw_markdown
        self.form.custom["repair_status"] = self._draw_repair_status
        self.form.custom["notice"] = self._draw_notice
        self.form.custom["detector_editor"] = self._draw_detector
        self.form.custom["fcs_editor"] = self._draw_fcs
        self.item_rects: dict[str, tuple] = {}
        self.confirm_window = DialogWindow(
            "Restore defaults", size=(480.0, 190.0), key="boarding_confirm", fit_height=True
        )
        self._checked_at = 0.0
        self._closing = False
        self.help_window = EmTkHelpWindow(
            title="Welcome to ChiSurf - Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.26, Region("steps"), Region("page")))
        self.docks.add_window("steps", tr("Steps"), self.draw_steps, dock="steps", closable=False)
        self.docks.add_window("page", tr("Welcome to ChiSurf"), self.draw_page, dock="page", closable=False)
        super().__init__(gui=self.render)

    # ----------------------------------------------------------- the editors
    def detector_editor(self) -> Any:
        """The embedded detector editor, built (and its saved setups listed) on first use."""
        if self.detector is None:
            self.detector = self._detector_factory()
            reload = getattr(getattr(self.detector, "toolbar", None), "reload", None)
            if callable(reload):
                reload()
            self.detector.autoload = False
        return self.detector

    def fcs_editor(self) -> Any:
        """The embedded FCS editor, built on first use; its Close leaves the step."""
        if self.fcs is None:
            self.fcs = self._fcs_factory()
            self.fcs.request_close = self._leave_fcs
        return self.fcs

    def _leave_fcs(self) -> None:
        """Close of the FCS editor: the Qt wizard closes the embedded widget; here we go on."""
        self.model.go_to(len(STEPS) - 1)

    # ------------------------------------------------------------------ frame
    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.form.rects.clear()
        self._recheck()
        self.docks.draw(box)
        if self.detector is not None:
            self.detector.page.draw_dialogs(box)
            self.detector._draw_prompt(box)
            self.detector.help_window.draw(box)
            self.detector.tour.draw(*vp.size)
        if self.fcs is not None:
            self._draw_fcs_dialogs(box, vp.size)
        self._draw_confirm(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)
        if self.model.finished and not self._closing:
            self._closing = True
            self.request_close()

    def _recheck(self) -> None:
        """Re-evaluate the step marks now and then: a setup may have been saved in an editor."""
        now = time.monotonic()
        if self.model.step_id in ("detector", "fcs") and now - self._checked_at > RECHECK_SECONDS:
            self._checked_at = now
            self.model.refresh_completion()

    # ---------------------------------------------------------------- windows
    def draw_steps(self, box: Any = None) -> None:
        """The navigation list, the Back / Next / Finish bar and Help / Guide."""
        for item in self.model.navigation():
            if im.selectable(item["label"], item["current"]):
                self.model.go_to(item["index"])
                self.tour.notify_used("nav_step")
            im.set_item_tooltip(item["tooltip"])
            if item["current"]:
                self.item_rects["nav_list"] = im.get_item_rect()
        im.separator()
        draw_sections(self.panels["navigation"]["sections"], self.model, self.form, titles=False)
        if im.button(tr("Help")):
            self.help_window.show()
        im.set_item_tooltip(tr("Explain the steps of the wizard."))
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Guide")):
            self.tour.start()
        im.set_item_tooltip(tr("Walk through the wizard step by step."))
        self.item_rects["guide"] = im.get_item_rect()

    def draw_page(self, box: Any = None) -> None:
        """The header of the current step and its page."""
        im.text(self.model.title)
        im.text_disabled(self.model.subtitle)
        im.separator()
        panel = self.panels[self.model.step_id]
        draw_sections(panel["sections"], self.model, self.form, titles=False)

    # ------------------------------------------------------- custom sections
    def _draw_markdown(self, section: dict, model: Any, state: FormState, width: float) -> None:
        source = (section.get("options") or {}).get("source", "")
        text = getattr(model, source)()
        im.markdown(text)

    def _draw_repair_status(self, section: dict, model: Any, state: FormState, width: float) -> None:
        if model.repair_message:
            im.text_colored(_OK if model.repair_ok else _FAILED, model.repair_message)

    def _draw_notice(self, section: dict, model: Any, state: FormState, width: float) -> None:
        if model.notice:
            im.text_wrapped(model.notice)

    def _draw_detector(self, section: dict, model: Any, state: FormState, width: float) -> None:
        editor = self.detector_editor()
        editor._draw_window()
        self.form.rects.update({f"detector_{k}": v for k, v in editor.item_rects.items()})

    def _draw_fcs(self, section: dict, model: Any, state: FormState, width: float) -> None:
        editor = self.fcs_editor()
        editor.draw_setup(None)
        im.separator()
        editor.draw_pairs(None)
        self.form.rects.update({f"fcs_{k}": v for k, v in editor.item_rects.items()})

    def _draw_fcs_dialogs(self, box: tuple, size: Any) -> None:
        """The file chooser, Help and Guide of the embedded FCS editor."""
        fcs = self.fcs
        if fcs.dialog:
            if im.begin(tr("Channel preset file")):
                result = fcs.dialog.draw()
                if result:
                    if fcs.dialog_action == "import":
                        fcs.run_action(lambda: fcs.model.import_presets(result[0]))
                    else:
                        fcs.run_action(lambda: fcs.model.export_presets(result[0]))
                    fcs.dialog = None
                elif result is False:
                    fcs.dialog = None
            im.end()
        if fcs.help.open:
            fcs.help.draw(box)
        if fcs.tour.active:
            fcs.tour.draw(*size)

    def _draw_confirm(self, box: tuple) -> None:
        """The question Restore defaults asks, as an in-app window."""
        if self.model.confirm and not self.confirm_window.open:
            self.confirm_window.show()
        if not self.model.confirm and self.confirm_window.open:
            self.confirm_window.hide()
        if not self.confirm_window.open:
            return
        pressed = self.confirm_window.begin(box)
        draw_sections(self.panels["confirm"]["sections"], self.model, self.form, titles=False)
        self.confirm_window.end()
        if pressed == "close":
            self.model.confirm_no()

    # ------------------------------------------------------------ persistence
    def export_settings(self) -> dict:
        """What is remembered: the current step and the window layout."""
        return {**self.model.export_settings(), "docks": self.docks.state()}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.restore_settings(settings)
        self.docks.restore(settings.get("docks"))

    def close(self) -> None:
        """Stop what the embedded editors run."""
        if self.detector is not None:
            self.detector.close()


def make_app() -> BoardingApp:
    """Build the wizard (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return BoardingApp()


__all__ = ["BoardingApp", "make_app"]
