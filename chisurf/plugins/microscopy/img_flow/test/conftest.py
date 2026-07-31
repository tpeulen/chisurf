"""Test fixtures for the flow-map plugin."""

import pytest
from qtpy.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for the widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
