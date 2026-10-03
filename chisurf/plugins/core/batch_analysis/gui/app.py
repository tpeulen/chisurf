"""Native EMTK Batch Analysis assistant over the Qt-free view model."""
from __future__ import annotations

from emtk import im
from emtk.app import ImApp

from .strings import install_translations, tr
from .view_model import BatchViewModel

install_translations()


class BatchAnalysisApp(ImApp):
    def __init__(self, model=None):
        self.model = model or BatchViewModel()
        self.message = ""
        super().__init__(self.render)

    def render(self):
        im.begin(tr("Batch Analysis"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Batch Analysis"), level=2)
        im.markdown(self.model.welcome_html())
        im.separator()
        im.heading(tr("Selection"), level=2)
        im.markdown(self.model.selection_html())
        changed, self.model.selected_fit_name = im.input_text(tr("Template fit"), self.model.selected_fit_name)
        im.set_item_tooltip(tr("Name of the representative fit used for every batch item"))
        changed, self.model.save_path = im.input_text(tr("CSV output"), self.model.save_path)
        im.set_item_tooltip(tr("Destination CSV path for batch results"))
        if im.button(tr("Run batch")):
            try:
                self.model.run()
                self.message = tr("Batch complete")
            except Exception as exc:
                self.message = f"{type(exc).__name__}: {exc}"
        im.set_item_tooltip(tr("Run the template fit across selected datasets and files"))
        if self.message:
            im.text_wrapped(self.message)
        im.separator()
        im.heading(tr("Results"), level=2)
        im.markdown(self.model.results_html())
        im.end()

    def export_settings(self):
        return {"selected_fit_name": self.model.selected_fit_name, "save_path": self.model.save_path}

    def restore_settings(self, settings):
        self.model.selected_fit_name = str(settings.get("selected_fit_name", ""))
        self.model.save_path = str(settings.get("save_path", ""))

    def close(self):
        self.model._observers.clear()


def make_app():
    return BatchAnalysisApp()
