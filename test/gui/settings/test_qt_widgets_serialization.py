import logging

import pytest
import yaml
from qtpy.QtWidgets import QSpinBox

from chisurf.core.base import Base


class QtSerializationWidget(Base):
    def __init__(self):
        super().__init__(name="TestWidget")
        self.spinbox = QSpinBox()
        self.regular_value = 42
        self.text_value = "This is a test"


@pytest.fixture
def qapp():
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_without_the_flag_the_widget_survives_into_the_elementary_dict(qapp, caplog):
    """Without ``skip_qt_widgets`` the conversion does not raise — it lies.

    ``to_elementary`` has no branch for a Qt object unless it is asked to skip
    one, so it falls through to the "not converted to basic type" warning and
    returns the live widget. The dict then claims to hold only elementary types
    while holding a ``QSpinBox``, and the failure surfaces much later, at the
    YAML dump.

    This test used to assert that the conversion *raised*, which it has not done
    for some time; it passed only because the class it instantiated had been
    renamed out from under it and the resulting ``NameError`` satisfied
    ``pytest.raises(Exception)``. Fixing the name exposed the real behaviour, so
    the assertion now states it.
    """
    caplog.set_level(logging.DEBUG)
    test_widget = QtSerializationWidget()

    result = test_widget.to_dict(convert_values_to_elementary=True)

    assert isinstance(result["spinbox"], QSpinBox), (
        "the widget is now converted or dropped — say so here, and in to_elementary's contract"
    )
    with pytest.raises(Exception):
        yaml.safe_dump(result)


def test_serialization_succeeds_with_skip_qt_widgets(qapp, caplog):
    caplog.set_level(logging.DEBUG)
    test_widget = QtSerializationWidget()

    logging.info("Attempting to serialize with skipping Qt widgets...")
    result = test_widget.to_dict(convert_values_to_elementary=True, skip_qt_widgets=True)
    logging.info(f"Result: {result}")

    assert result is not None
    assert "spinbox" not in result
    assert result["regular_value"] == 42
    assert result["text_value"] == "This is a test"


def test_save_to_yaml_with_skip_qt_widgets(qapp, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    test_widget = QtSerializationWidget()

    yaml_path = tmp_path / "test_widget.yaml"
    logging.info("Attempting to save to YAML with skipping Qt widgets...")
    test_widget.save(str(yaml_path), skip_qt_widgets=True)

    assert yaml_path.exists()
    content = yaml_path.read_text()
    assert "spinbox" not in content
    assert "regular_value" in content
    assert "text_value" in content
