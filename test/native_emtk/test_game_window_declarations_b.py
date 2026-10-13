"""Game host dimensions are declarations; native input and round state stay intact."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from emtk.keys import KEY_RETURN, KEY_RIGHT
from emtk.testing import Driver, RecordingPainter

from chisurf.core.dataspec.schema import validate_view_spec
from chisurf.emtk.state import attach_native_state

CASES = [
    ("gui.app", (1200, 800)),
    ("minesweeper.gui.app", (560, 620)),
    ("number_quest.gui.app", (560, 420)),
]


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Exercise fresh persisted state without touching the user's settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


def close_app(app):
    """Close native hosts that own resources; bare minefields need no teardown."""
    close = getattr(app, "close", None)
    if callable(close):
        close()


def module_for(name):
    """Resolve the actual native game factory owner."""
    return importlib.import_module(f"chisurf.plugins.misc.games.{name}")


def declaration_path(module):
    """Resolve the game-owned declaration after the canonical GUI move."""
    parent = Path(module.__file__).parent
    if module.__name__.endswith("number_quest.gui.app"):
        parent = parent.parent
    return parent / "app.view.json"


def override_declaration(monkeypatch, module, size):
    """Change only the spec read by the real constructor, retaining its structure."""
    path = declaration_path(module)
    original = Path.read_text
    spec = json.loads(path.read_text())
    spec["window"] = dict(zip(("width", "height"), size, strict=True))

    def read(source, *args, **kwargs):
        """Supply the edited declaration only to its exact source path."""
        return json.dumps(spec) if source == path else original(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)


@pytest.mark.parametrize("name,expected", CASES)
def test_real_constructor_reads_declared_default(name, expected):
    """Fresh native hosts use their true existing dimensions with valid specs."""
    module = module_for(name)
    spec = json.loads(declaration_path(module).read_text())
    assert not validate_view_spec(spec)
    assert spec["window"] == dict(zip(("width", "height"), expected, strict=True))
    app = attach_native_state(f"declarations-b-{name}", module.make_app())
    try:
        assert app.window_size == expected
        driver = Driver(app, expected)
        assert driver.draw(2).texts
        if name == "gui.app":
            assert app.child is not None and not app.error
    finally:
        close_app(app)


@pytest.mark.parametrize("name,expected", CASES)
def test_changed_declaration_is_consumed_by_real_constructor(name, expected, monkeypatch):
    """Changing the JSON changes the initial host size without source edits."""
    module = module_for(name)
    changed = expected[0] + 80, expected[1] + 40
    override_declaration(monkeypatch, module, changed)
    app = module.make_app()
    try:
        assert app.window_size == changed
    finally:
        close_app(app)


@pytest.mark.parametrize("name,expected", CASES)
def test_saved_resize_wins_over_changed_declaration(name, expected, monkeypatch):
    """A fresh first launch saves a real round and later respects user dimensions."""
    module = module_for(name)
    key = f"saved-declarations-b-{name}"
    first = attach_native_state(key, module.make_app())
    saved = expected[0] + 140, expected[1] + 100
    state = first.export_settings() if hasattr(first, "export_settings") else None
    first.window_resized(*saved)
    first.close()
    override_declaration(monkeypatch, module, (900, 700))
    reopened = attach_native_state(key, module.make_app())
    try:
        assert reopened.window_size == saved
        if state is not None:
            assert reopened.export_settings() == state
        reopened.draw(RecordingPainter(), 0, 0, 700, 500)
        assert reopened.window_size == saved
    finally:
        reopened.close()


def exercise(app, name, size):
    """Drive real game keys and retain deterministic state plus drawn controls."""
    actual = app.child if name == "gui.app" else app
    if name == "minesweeper.gui.app":
        actual.game._fixed_mine_positions = {
            (0, 0),
            (0, 3),
            (1, 7),
            (2, 4),
            (3, 2),
            (4, 8),
            (5, 5),
            (6, 1),
            (7, 7),
            (8, 3),
        }
        actual.game.reset()
        previous = actual.cursor_col
    else:
        actual.game.reset(target=37)
        previous = actual.estimate
    driver = Driver(app, size)
    driver.draw(2)
    driver.press(KEY_RIGHT)
    if name == "minesweeper.gui.app":
        assert actual.cursor_col == previous + 1
        driver.key(ord("F"), "f")
        assert actual.game.board[actual.cursor_row][actual.cursor_col].flagged
    else:
        assert actual.estimate == previous + 1
        driver.press(KEY_RETURN)
        assert actual.history == [51]
        if name == "gui.app":
            # The rows by their remembered rectangles: the header repeats the selected
            # game's name, so the drawn text "Number Quest" is not only the list row.
            driver.draw(2)
            driver.click(app.item_rects["game_Minesweeper"])
            assert app.selected == "Minesweeper" and not app.error
            driver.draw(2)
            driver.click(app.item_rects["game_Number Quest"])
            assert app.child is actual and actual.history == [51]
    painter = driver.draw(2)
    return actual.export_settings(), list(painter.texts)


@pytest.mark.parametrize("name,expected", CASES)
def test_declaration_override_preserves_game_input_state_and_controls(name, expected, monkeypatch):
    """Declared host defaults never alter gameplay or layout at a given viewport."""
    module = module_for(name)
    before = module.make_app()
    try:
        expected_state, expected_controls = exercise(before, name, expected)
    finally:
        close_app(before)
    override_declaration(monkeypatch, module, (900, 700))
    after = module.make_app()
    try:
        actual_state, actual_controls = exercise(after, name, expected)
        assert actual_state == expected_state
        assert actual_controls == expected_controls
    finally:
        close_app(after)
