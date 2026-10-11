"""Shared tour translations retain real awaited actions and navigation."""

from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver

from chisurf.emtk import help_guide

TRANSLATIONS = {
    "Guided Tour": "Parcours",
    "Step {step} of {total}: {title}": "Étape {step}/{total} : {title}",
    "First task": "Première action",
    "Second task": "Deuxième action",
    "Read this.": "Lisez ces informations supplémentaires avant de continuer. " * 4,
    "Ready.": "Prêt.",
    "Press Action.": "Appuyez sur Action.",
    "drag here to move": "déplacer ici",
    "Close Tour": "Fermer",
    "◄ Prev": "◄ Retour",
    "Next ►": "Suite ►",
    "Finish ✓": "Fin ✓",
    "Use the highlighted control to continue.": "Utilisez le bouton indiqué.",
    "Go to the previous tour step.": "Revenir à l’étape précédente.",
    "This is the first tour step.": "Première étape du parcours.",
    "Go to the next tour step.": "Passer à l’étape suivante.",
    "Finish the guided tour.": "Terminer ce parcours.",
    "Close the guided tour and return to the tool.": "Fermer le parcours et revenir à l’outil.",
}


class TourApp(ImApp):
    """Expose an actual awaited button beneath the shared tour renderer."""

    def __init__(self):
        self.actions = 0
        self.target = None
        self.tour = help_guide.EmTkGuidedTour(
            [
                {
                    "title": "First task",
                    "text": "Read this.",
                    "target": "action",
                    "await": {"hint": "Press Action."},
                },
                {"title": "Second task", "text": "Ready."},
            ],
            get_target_rect=lambda name: self.target,
            wait_for_controls=True,
        )
        super().__init__(self.render)
        self.io.wall_clock = False
        self.tour.start()

    def render(self):
        """Notify the tour only when the actual target action fires."""
        im.begin("Owner", (0, 0, 640, 500))
        if im.button("Action"):
            self.actions += 1
            self.tour.notify_used("action")
        self.target = im.get_item_rect()
        im.end()
        self.tour.draw(640, 500)


def install_translation(monkeypatch):
    """Supply a deterministic catalogue through the existing translation seam."""
    monkeypatch.setattr(help_guide, "tr", lambda text: TRANSLATIONS.get(text, text))


def test_translated_tour_text_is_measured_before_rendering(monkeypatch):
    """Expanded authored content increases card height and appears with translated hints."""
    english = TourApp()
    english_painter = Driver(english, (640, 500)).frame(2)
    english_close = next(t for t in english_painter.visible_texts if t[5] == "Close Tour")
    install_translation(monkeypatch)
    app = TourApp()
    painter = Driver(app, (640, 500)).frame(2)
    text = " ".join(" ".join(painter.strings).split())
    assert "Étape 1/2 : Première action" in text
    assert "informations supplémentaires" in text
    assert "Appuyez sur Action." in text
    assert "déplacer ici" in text
    translated_close = next(t for t in painter.visible_texts if t[5] == "Fermer")
    assert translated_close[1] > english_close[1]
    assert app.actions == 0 and app.tour.awaiting


def test_translated_buttons_preserve_await_prev_close_and_finish(monkeypatch):
    """Localized real buttons wait for the target, navigate, and close normally."""
    install_translation(monkeypatch)
    app = TourApp()
    driver = Driver(app, (640, 500))
    driver.frame(2)
    driver.hover("Suite ►")
    app.io.now += 1.0
    painter = driver.frame(2)
    assert TRANSLATIONS["Use the highlighted control to continue."] in " ".join(painter.strings)
    driver.click("Suite ►")
    assert app.tour.step_idx == 0 and app.tour.awaiting and app.actions == 0
    driver.click("Action")
    assert app.actions == 1 and not app.tour.awaiting
    driver.click("Suite ►")
    assert app.tour.step_idx == 1
    driver.frame(2)
    driver.click("◄ Retour")
    assert app.tour.step_idx == 0 and app.tour.awaiting
    driver.frame(2)
    driver.click("Action")
    driver.click("Suite ►")
    driver.frame(2)
    driver.click("Fin ✓")
    assert not app.tour.active and app.actions == 2
    app.tour.start()
    driver.frame(2)
    driver.click("Fermer")
    assert not app.tour.active
