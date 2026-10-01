"""Native EMTK onboarding wizard over BoardingViewModel."""
from __future__ import annotations

from emtk import im
from emtk.app import ImApp

from .strings import install_translations, tr
from .view_model import BoardingViewModel

install_translations()


class BoardingApp(ImApp):
    def __init__(self, model=None):
        self.model = model or BoardingViewModel()
        self.page = "welcome"
        super().__init__(self.render)

    def render(self):
        im.begin(tr("Welcome to ChiSurf"), (0, 0, *im.get_main_viewport().size))
        for page, label, tip in (("welcome", "Welcome", "Read the onboarding overview"), ("repair", "Repair settings", "Create or restore user settings"), ("status", "Status", "Inspect settings and optional dependencies"), ("finish", "Finish", "Review recommended next steps")):
            if im.selectable(tr(label), self.page == page):
                self.page = page
            im.set_item_tooltip(tr(tip))
        im.separator()
        # The page content overflows small hosts; a scrollable child region
        # gives it a scrollbar instead of clipping.
        avail = im.get_content_region_avail()
        if im.begin_child("##boarding_page", avail):
            if self.page == "welcome":
                im.markdown(self.model.welcome_html())
            elif self.page == "repair":
                im.markdown(self.model.repair_intro_html())
                if im.button(tr("Create missing files")):
                    self.model.create_missing()
                im.set_item_tooltip(tr("Create only missing user settings files"))
                im.same_line()
                if im.button(tr("Restore defaults")):
                    self.model.overwrite_defaults()
                im.set_item_tooltip(tr("Replace user settings with packaged defaults"))
                im.markdown(self.model.repair_status_html())
            elif self.page == "status":
                im.markdown(self.model.status_html())
                im.markdown(self.model.deps_html())
                if im.button(tr("Open settings folder")):
                    self.model.open_settings_dir()
                im.set_item_tooltip(tr("Open the user settings directory"))
            else:
                im.markdown(self.model.finish_html())
            im.end_child()
        im.end()

    def export_settings(self): return {"page": self.page}

    def restore_settings(self, settings): self.page = str(settings.get("page", "welcome"))


def make_app():
    return BoardingApp()
