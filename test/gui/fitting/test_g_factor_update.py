"""Actual native Add, cell-edit and Delete actions retain per-detector G-factor identity."""

from __future__ import annotations

from typing import Any

from test.gui.test_cell_text_editing import edit_g
from test.gui.test_cell_text_editing import isolated_detector_settings as isolated_detector_settings
from test.gui.test_cell_text_editing import page as page


def two_detectors(page: Any) -> tuple[Any, Any, list[str]]:
    """Create two auto-named detectors using the visible native Add control."""
    native, ui, _ = page
    settings = native.get_settings()
    settings["detectors"] = {}
    native.set_settings(settings)
    ui.draw(2)
    ui.click("add_detector")
    ui.click("add_detector")
    names = list(native.detectors)
    assert len(names) == 2 and names[0] != names[1]
    edit_g(native, ui, 0, "1.234")
    edit_g(native, ui, 1, "2.345")
    return native, ui, names


def test_g_factor_update(page: Any) -> None:
    """Two detector rows keep their own values through real native keyboard commits."""
    native, _, names = two_detectors(page)
    assert native.detectors[names[0]]["g_factor"] == 1.234
    assert native.detectors[names[1]]["g_factor"] == 2.345


def test_a_detector_row_can_be_removed_without_disturbing_the_other(page: Any) -> None:
    """The actual Delete button removes one named detector without moving another value."""
    native, ui, names = two_detectors(page)
    ui.draw(2)
    rectangle = next(
        box
        for _, row, key, box in native.editor._detector_buttons.cells()
        if row == 0 and key == "delete"
    )
    ui.click(rectangle)
    assert list(native.detectors) == [names[1]]
    assert native.detectors[names[1]]["g_factor"] == 2.345
