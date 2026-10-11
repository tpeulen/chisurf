"""Button row wrapping measures visible captions, preserving hidden identities."""

from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver

from chisurf.plugins.emtk_layout import button_row, button_width


def test_hidden_identity_does_not_push_fitting_buttons_to_another_row():
    """Real caption widths fit on one row and both controls remain clickable."""
    used = []
    widths = {}
    app = None

    def remember(key):
        """Remember the actual drawn control rectangle."""
        app.item_rects[key] = im.get_item_rect()

    def draw():
        """Render the real shared action row with hidden control identities."""
        if im.begin("Actions", (0, 0, 180, 120)):
            labels = ("Run##long-private-running-identity", "Stop##another-private-identity")
            for label in labels:
                widths[label] = button_width(label)
            pressed = button_row(
                [
                    {"label": labels[0], "key": "run", "tip": "Run."},
                    {"label": labels[1], "key": "stop", "tip": "Stop."},
                ],
                width=110,
                remember=remember,
            )
            if pressed:
                used.append(pressed)
        im.end()

    app = ImApp(draw)
    app.item_rects = {}
    driver = Driver(app, size=(180, 120))
    driver.draw(3)
    assert app.item_rects["run"][1] == app.item_rects["stop"][1]
    for label, key in zip(widths, ("run", "stop")):
        assert widths[label] == app.item_rects[key][2]
        driver.click(key)
    assert used == ["run", "stop"]


def test_a_row_of_translated_buttons_wraps_on_the_width_it_draws():
    """French captions are longer than the English source: the row must wrap on them, not on the source."""
    from emtk import i18n as toolkit_i18n

    from chisurf.emtk import i18n

    previous = toolkit_i18n.get_locale()
    widths, app = {}, None

    def remember(key):
        app.item_rects[key] = im.get_item_rect()

    def draw():
        if im.begin("Actions", (0, 0, 400, 120)):
            widths["save"] = button_width("Save settings")
            button_row(
                [
                    {"label": "Clear picks", "key": "clear"},
                    {"label": "Save settings", "key": "save"},
                ],
                width=1.0 + button_width("Clear picks") + im.get_style().item_spacing[0] + widths["save"],
                remember=remember,
            )
        im.end()

    try:
        i18n.install("fr")
        i18n.set_locale("fr")
        assert toolkit_i18n.tr("Save settings") != "Save settings"
        app = ImApp(draw)
        app.item_rects = {}
        Driver(app, size=(400, 120)).draw(3)
        assert widths["save"] == app.item_rects["save"][2]
        # it fits exactly, so it stays on the row; before, the width of "Save settings" was budgeted and the
        # longer "Enregistrer les réglages" ran past the edge of a dock that was sized to it
        assert app.item_rects["clear"][1] == app.item_rects["save"][1]
    finally:
        toolkit_i18n.set_locale(previous)
