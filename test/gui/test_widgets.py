# --- Skip Qt Widgets Serialization Tests ---

from pathlib import Path

import pytest
from qtpy import QtWidgets

import chisurf.core.base


class SerializedTestClass(chisurf.core.base.Base):
    def __init__(self, name="TestClass"):
        super().__init__(name=name)
        # We don't need a real QApplication here if we are just testing skip_qt_widgets logic,
        # but chisurf.core.base likely checks for types.
        self.widget = QtWidgets.QWidget()
        self.spinbox = QtWidgets.QSpinBox()
        self.normal_attr = "This is a normal attribute"
        self.number = 42


def test_with_skip_qt_widgets(qtbot):
    """Test serialization with skip_qt_widgets=True"""
    test_obj = SerializedTestClass()

    # Try to convert to dict with skip_qt_widgets=True
    result = test_obj.to_dict(skip_qt_widgets=True)

    # Check that Qt widgets were skipped
    assert "widget" not in result, "Qt widget 'widget' was not skipped"
    assert "spinbox" not in result, "Qt widget 'spinbox' was not skipped"

    # Check that normal attributes were preserved
    assert "normal_attr" in result, "Normal attribute was incorrectly skipped"
    assert "number" in result, "Normal attribute was incorrectly skipped"


def test_with_to_elementary(qtbot):
    """Test to_elementary with skip_qt_widgets=True"""
    test_obj = SerializedTestClass()

    # Convert to dict first
    d = test_obj.to_dict()

    # Then use to_elementary with skip_qt_widgets=True
    result = chisurf.core.base.to_elementary(d, skip_qt_widgets=True)

    # Check that Qt widgets were skipped
    assert "widget" not in result, "Qt widget 'widget' was not skipped"
    assert "spinbox" not in result, "Qt widget 'spinbox' was not skipped"

    # Check that normal attributes were preserved
    assert "normal_attr" in result, "Normal attribute was incorrectly skipped"
    assert "number" in result, "Normal attribute was incorrectly skipped"


def test_yaml_serialization(qtbot):
    """Test YAML serialization with skip_qt_widgets=True"""
    test_obj = SerializedTestClass()

    # Try to convert to YAML with skip_qt_widgets=True
    yaml_str = test_obj.to_yaml(skip_qt_widgets=True)

    # Check that the YAML string doesn't contain references to Qt widgets
    assert "widget" not in yaml_str, "Qt widget 'widget' was not skipped in YAML"
    assert "spinbox" not in yaml_str, "Qt widget 'spinbox' was not skipped in YAML"

    # Check that normal attributes were preserved
    assert "normal_attr" in yaml_str, "Normal attribute was incorrectly skipped in YAML"
    assert "42" in yaml_str, "Normal attribute was incorrectly skipped in YAML"


# --- Visual Link Tests ---


def test_group_unlink_refreshes_visual_state_for_related_widgets_contract():
    path = (
        Path(__file__).resolve().parents[2]
        / "chisurf"
        / "gui"
        / "widgets"
        / "fitting"
        / "parameter_widgets.py"
    )
    if not path.exists():
        pytest.skip("parameter_widgets.py not found")
    src = path.read_text(encoding="utf-8")

    assert "def _refresh_group_link_visuals(self):" in src
    assert "QtCore.QTimer.singleShot(100, self._refresh_group_link_visuals)" in src
    assert "self._refresh_group_link_visuals()" in src
