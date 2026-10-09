"""The photon table's page fields take typed numbers, operated with real pointer and keyboard input.

The emtk surface the Qt tool hosts (``qt_host_app``), over the BH SPC-132 sample (183,657 photons), with a stand-in
for the tool's three page attributes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel
from chisurf.plugins.tttr.photon_table.gui.qt_host_app import PhotonTableApp

from .test_emtk_photon_table_parity import SAMPLE, hermetic, needs_sample  # noqa: F401  (hermetic is autouse)


@pytest.fixture
def drv():
    model = PhotonTableModel()
    model.load_file(str(SAMPLE))
    tool = SimpleNamespace(_model=model, first_index=0, rows_per_page=200, channel_filter=-1)
    return Driver(PhotonTableApp(tool))


@needs_sample
def test_rows_and_first_photon_are_typed_and_clamped(drv):
    tool = drv.app.tool
    drv.type_into_name("rows_per_page", "50")
    assert tool.rows_per_page == 50
    drv.type_into_name("rows_per_page", "99999")
    assert tool.rows_per_page == 20_000, "clamped to the Qt maximum"
    drv.type_into_name("rows_per_page", "50")
    drv.type_into_name("first_photon", "1000")
    assert tool.first_index == 1000
    drv.type_into_name("first_photon", "-7")
    assert tool.first_index == 0, "a negative index is clamped to the first photon"
    drv.type_into_name("first_photon", "abc")
    assert tool.first_index == 0
