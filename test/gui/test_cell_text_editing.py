"""Real native G-factor cell edits preserve model identity, callbacks and valid values."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from emtk.events import CONTROL_MODIFIER, LEFT_BUTTON
from emtk.keys import KEY_RETURN
from emtk.testing import Driver

from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizard
from test.gui.test_detector_native_callers import (
    isolated_detector_settings as isolated_detector_settings,
)
from test.gui.test_detector_native_callers import (
    native_driver,
)


@pytest.fixture
def page(qapp: Any, tmp_path: Any) -> Iterator[tuple[Any, Driver, list[dict]]]:
    """Use the public native page with one real detector and an isolated store."""
    settings = {
        "windows": {"prompt": [0, 2048]},
        "detectors": {
            "detector": {
                "chs": [0, 1],
                "micro_time_ranges": [[0, 4095]],
                "g_factor": 1.0,
                "l1": 0.17,
                "l2": 0.23,
                "future_metadata": {"keep": [1, 2]},
            }
        },
        "tttr_reading": {
            "file_type": "SPC-130",
            "macro_time_resolution": 50.0,
            "micro_time_resolution": 50.0,
            "micro_time_binning": 1,
        },
    }
    wizard = DetectorWizard(settings=settings, setups_file=str(tmp_path / "setups.json"))
    native = wizard.page(0)
    notices: list[dict] = []
    native.detectorsChanged.connect(lambda: notices.append(native.get_settings()))
    ui = native_driver(native)
    ui.draw(3)
    try:
        yield native, ui, notices
    finally:
        wizard.close()
        qapp.processEvents()


def cell_rect(editor: Any, ui: Driver, row: int, key: str) -> tuple[float, float, float, float]:
    """Locate a visible actual retained cell using the table's drawn geometry."""
    ui.draw(2)
    control = editor._detector_table.control
    x = control._header_box[0]
    y = control._body_box[1] + (control.order().index(row) - control.bar.top) * control._row_h
    for column, width in zip(control._shown, control._widths):
        if column.key == key:
            assert control._body_box[1] <= y < control._body_box[1] + control._body_box[3]
            return x, y, width, control._row_h
        x += width
    raise AssertionError(f"The actual detector table does not show {key}")


def double_click(ui: Driver, rectangle: tuple[float, float, float, float]) -> None:
    """Send the actual host double-click flag; two Driver.click calls are singles."""
    ui.hover(rectangle)
    x, y, width, height = rectangle
    x, y = x + width / 2, y + height / 2
    ui.surface.on_pointer_press(x, y, LEFT_BUTTON, 0, double=True)
    ui.draw(1)
    ui.surface.on_pointer_release(x, y, LEFT_BUTTON, 0)
    ui.draw(1)


def edit_g(page: Any, ui: Driver, row: int, text: str) -> None:
    """Double-click and replace the G cell through actual SDK keyboard input."""
    rectangle = cell_rect(page.editor, ui, row, "g")
    double_click(ui, rectangle)
    assert page.editor._detector_table.control.editing is not None
    ui.key(0x41, "a", CONTROL_MODIFIER)
    ui.type(text)
    ui.key(KEY_RETURN)
    ui.draw(2)
    assert page.editor._detector_table.control.editing is None


def test_programmatic_update_keeps_native_editor_and_scalar_callback(page: Any) -> None:
    """A scalar update retains native editor/table identity and scientific metadata."""
    native, ui, notices = page
    editor, table, model = native.editor, native.editor._detector_table.control, native.model
    assert native.update_detector("detector", {"g_factor": 3.456, "l1": 0.01, "l2": 0.02})
    ui.draw(2)
    assert (
        native.editor is editor
        and editor._detector_table.control is table
        and native.model is model
    )
    row = editor.detector_rows()[0]
    assert [float(row[key]) for key in ("g", "l1", "l2")] == [3.456, 0.01, 0.02]
    assert native.detectors["detector"]["future_metadata"] == {"keep": [1, 2]}
    assert len(notices) == 1


def test_programmatic_update_reaches_settings_and_identical_edit_is_not_reemitted(
    page: Any,
) -> None:
    """One actual changed definition is emitted; repeating its scalar value is a no-op."""
    native, _, notices = page
    assert native.update_detector("detector", {"g_factor": 3.456})
    assert native.get_settings()["detectors"]["detector"]["g_factor"] == pytest.approx(3.456)
    assert not native.update_detector("detector", {"g_factor": 3.456})
    assert len(notices) == 1


def test_readonly_native_cell_cannot_overwrite_calibrated_value(page: Any) -> None:
    """Read-only protection is enforced by the actual native input path."""
    native, ui, notices = page
    native.update_detector("detector", {"g_factor": 1.234})
    native.editor.read_only = True
    rectangle = cell_rect(native.editor, ui, 0, "g")
    double_click(ui, rectangle)
    ui.key(0x41, "a", CONTROL_MODIFIER)
    ui.type("9.999")
    ui.key(KEY_RETURN)
    assert native.detectors["detector"]["g_factor"] == 1.234
    assert native.editor._detector_table.control.editing is None
    assert len(notices) == 1


def test_user_edit_is_kept_and_normalised(page: Any) -> None:
    """Actual select-all/type/Enter commits the value and a three-decimal row."""
    native, ui, notices = page
    edit_g(native, ui, 0, "2.3")
    assert native.detectors["detector"]["g_factor"] == 2.3
    assert native.editor.detector_rows()[0]["g"] == "2.300"
    assert len(notices) == 1


def test_invalid_user_edit_restores_last_valid_value_without_a_callback(page: Any) -> None:
    """Unparseable native input rolls back the row and leaves scientific state unchanged."""
    native, ui, notices = page
    native.update_detector("detector", {"g_factor": 1.5})
    edit_g(native, ui, 0, "not a number")
    assert native.detectors["detector"]["g_factor"] == 1.5
    assert float(native.editor.detector_rows()[0]["g"]) == 1.5
    assert "must be a number" in native.editor.status
    assert len(notices) == 1
