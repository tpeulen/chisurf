from __future__ import annotations

import pytest
from emtk.testing import Driver

from chisurf.emtk.main_app import EmtkShellApp


@pytest.fixture
def shell(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    app = EmtkShellApp(session_factory=lambda: None)
    yield app
    app.close()


def test_styles_submenu_in_settings_menu(shell):
    driver = Driver(shell, size=(1200, 800))
    driver.frame(2)

    # 1. Open Settings menu
    driver.click("menu.Settings")
    driver.frame(2)
    strings = set(driver.painter.strings)
    assert "Styles" in strings
    assert "Dark theme" not in strings
    assert "Light theme" not in strings

    # 2. Click Styles to open the submenu
    driver.click("menu.styles")
    driver.frame(2)
    strings = set(driver.painter.strings)
    assert "Dark Blue" in strings
    assert "Dark" in strings
    assert "Light" in strings
    assert "Dark Green" in strings
    assert "Dark Orange" in strings
    assert "Dark Violet" in strings
    assert "Dark Blue Flat" not in strings

    styles_action = shell._theme_actions()[0]
    child_labels = [c.label for c in styles_action.children]
    child_keys = [c.key for c in styles_action.children]
    assert len(child_labels) == len(set(child_labels)), f"Duplicate labels found: {child_labels}"
    assert len(child_keys) == len(set(child_keys)), f"Duplicate keys found: {child_keys}"

    # 3. Choose a style from the submenu
    driver.click("menu.style_dark_green")
    driver.frame(2)

    from emtk import theme
    from chisurf.core.settings import theme as stored_theme

    assert theme.current_theme() == "dark_green"
    assert stored_theme.stored_style() in ("dark_green.css", "dark_green")

    # 4. Verify that re-opening the menu immediately reflects dark_green colors live without restart
    from emtk import style as emtk_style

    assert emtk_style.POPUP_BG == (36, 44, 38, 255)
    driver.click("menu.Settings")
    driver.frame(2)

    menu_strokes = [
        call for call in driver.painter.calls
        if call[0] == "stroke_rect" and call[2] == 16.0
    ]
    assert len(menu_strokes) > 0
    # Last stroke_rect for popup background must use dark_green POPUP_BG
    assert menu_strokes[-1][6] == (36, 44, 38, 255)

    # 5. Switch to Light style live
    driver.click("menu.styles")
    driver.frame(2)
    driver.click("menu.style_light")
    driver.frame(2)

    assert theme.current_theme() == "light"
    assert emtk_style.POPUP_BG == (252, 252, 253, 255)

    driver.click("menu.Settings")
    driver.frame(2)

    menu_strokes = [
        call for call in driver.painter.calls
        if call[0] == "stroke_rect" and call[2] == 16.0
    ]
    assert len(menu_strokes) > 0
    # Popup background must immediately use light POPUP_BG without restart
    assert menu_strokes[-1][6] == (252, 252, 253, 255)
