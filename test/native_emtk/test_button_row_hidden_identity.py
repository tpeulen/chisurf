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
                [{"label": labels[0], "key": "run", "tip": "Run."},
                 {"label": labels[1], "key": "stop", "tip": "Stop."}],
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
