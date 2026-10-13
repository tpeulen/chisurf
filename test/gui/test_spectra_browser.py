"""Headless tests for the Spectra tool shell and the masked password field (the browser, overview and Add-to-MMFDB checks live in the plugin's tests/test_native.py)."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _staging_db():
    from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase

    path = os.path.join(tempfile.mkdtemp(), "staging.db")
    db = FluorophoreDatabase(path)
    db.connect()
    wl = np.linspace(400, 700, 8)
    with db:
        db.register_component(
            name="EGFP",
            source="fpbase",
            kind="fluorescent_protein",
            spectra={"absorption": (wl, np.ones_like(wl)), "emission": (wl, np.ones_like(wl))},
        )
        db.register_component(
            name="Thorlabs SPCMxxA",
            source="fpbase",
            kind="detector",
            source_ref="9342",
            spectra={"quantum_efficiency": (wl, np.linspace(0, 1, 8))},
        )
        db.conn.commit()
    return db


def test_spectra_tool_navigation_panels_build():
    """The Spectra tool is an emtk app whose four panels all draw."""
    from emtk.testing import Driver

    from chisurf.plugins.spectra_downloader.gui.app import PANELS
    from chisurf.plugins.spectra_downloader.gui.tool import SpectraTool

    db = _staging_db()
    tool = SpectraTool(db)
    assert list(PANELS) == ["Overview", "Browse", "Download", "Add to MMFDB"]
    driver = Driver(tool, tool.window_size)
    for name in PANELS:
        tool.select_panel(name)
        painter = driver.draw(3)
        assert tool.panel == name
        assert painter.strings, f"panel {name} drew no text"
    db.close()


def test_autoform_password_kind_is_masked(qapp):
    """The password ValueSection renders a masked QLineEdit."""
    from qtpy import QtWidgets

    from chisurf.core.dataspec import ModelView, ValueSection
    from chisurf.gui.autoform import AutoForm

    class _M:
        secret = "hunter2"

        def view_spec(self):
            return ModelView(
                sections=[ValueSection(attr="secret", label="Secret", kind="password")]
            )

    form = AutoForm(_M())
    edits = form.findChildren(QtWidgets.QLineEdit)
    assert any(e.echoMode() == QtWidgets.QLineEdit.Password for e in edits)
