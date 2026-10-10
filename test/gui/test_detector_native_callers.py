"""Real surviving detector callers share one native page and portable settings authority."""
from __future__ import annotations

import copy
import importlib
import socket

import pytest

SETTINGS = {
    "detectors": {"donor": {"chs": [0, 1], "micro_time_ranges": [[700, 2000]],
        "g_factor": 1.25, "l1": 0.05, "l2": 0.02, "g_factor_channels": [850, 1850],
        "future_metadata": {"preserve": True}}},
    "windows": {"prompt": [700, 2000]},
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 13.5,
                     "micro_time_resolution": 3.2958984375, "micro_time_binning": 2},
    "future_setup_metadata": {"preserve": [1, 2]},
}


@pytest.fixture(autouse=True)
def isolated_detector_settings(tmp_path, monkeypatch):
    """Isolate actual constructors and forbid account/daemon or external connections."""
    for key, path in {"CHISURF_SETTINGS_DIR": tmp_path / "settings",
                      "MMFDB_SETTINGS_DIR": tmp_path / "mmfdb",
                      "MMFDB_DATABASE_PATH": tmp_path / "database.sqlite",
                      "MMFDB_OBJECT_STORE": tmp_path / "objects",
                      "MMFDB_OBJECT_STORE_ROOT": tmp_path / "objects",
                      "XDG_CACHE_HOME": tmp_path / "cache"}.items():
        monkeypatch.setenv(key, str(path))
    def forbidden(*args, **kwargs):
        raise AssertionError("Detector caller attempted an external socket/daemon connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    import zmq
    monkeypatch.setattr(zmq.Socket, "connect", forbidden)
    monkeypatch.setattr(zmq.Socket, "bind", forbidden)
    from chisurf.core import settings, setup_channel_definition
    from chisurf.core.fio.lut_context import clear_active_setup_lut
    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings")
    monkeypatch.setattr(setup_channel_definition.CONFIG, "canonical_file", tmp_path / "setups.json")
    monkeypatch.setitem(settings.cs_settings, "mmfdb", {"default_user_id": "caller-owner"})
    clear_active_setup_lut()
    yield
    clear_active_setup_lut()


def native_driver(page):
    """Drive the actual hosted app with canonical SDK font, input and clipping metrics."""
    from emtk.testing import Driver
    return Driver(page.app, (1200, 900))


def actual_caller(kind):
    """Construct each existing caller; return its real parent and detector page."""
    if kind in {"background", "irf", "count_rate"}:
        section_factories = {
            "background": ("chisurf.plugins.burst.burst_background.gui.sections", "build_detector_page",
                "chisurf.plugins.burst.burst_background.view_model", "BackgroundViewModel"),
            "irf": ("chisurf.plugins.burst.burst_irf_bg.gui.sections", "irf_bg_channels",
                "chisurf.plugins.burst.burst_irf_bg.gui.view_model", "IrfBackgroundViewModel"),
            "count_rate": ("chisurf.plugins.tttr.tttr_count_rate_analysis.gui.sections", "count_rate_channels",
                "chisurf.plugins.tttr.tttr_count_rate_analysis.gui.view_model", "CountRateViewModel"),
        }
        module, factory, model_module, model_class = section_factories[kind]
        model = getattr(importlib.import_module(model_module), model_class)()
        page = getattr(importlib.import_module(module), factory)(model)
        return page, page, model
    if kind == "audifier":
        from chisurf.plugins.tttr.audifier.gui.sections import _SetupSection
        from chisurf.plugins.tttr.audifier.gui.view_model import AudifierViewModel
        model = AudifierViewModel()
        parent = _SetupSection(model)
        return parent, parent._page, model
    caller_constructors = {
        "core_tool": ("chisurf.plugins.core.setup_channel_definition.gui.tool", "SetupChannelDefinitionWidget", "page"),
        "core_wizard": ("chisurf.plugins.core.setup_channel_definition.wizard", "ChisurfWizard", "filter"),
        "bid": ("chisurf.plugins.burst.bid_to_analysis.gui.legacy", "BidToAnalysisGUI", "detector_page"),
        "trace": ("chisurf.plugins.tttr.trace_browser.widget", "TraceBrowser", "detector_page"),
        "image": ("chisurf.plugins.tttr.tttr_image_browser.workspace", "TTTRImageBrowser", "detector_page"),
        "intensity": ("chisurf.plugins.tttr.intensity_trace.qt_tool", "IntensityTrace", "detector_wizard_page"),
    }
    module, class_name, attribute = caller_constructors[kind]
    parent = getattr(importlib.import_module(module), class_name)()
    return parent, getattr(parent, attribute), getattr(parent, "model", None)


@pytest.mark.parametrize("kind", ["core_tool", "core_wizard", "background", "irf", "count_rate",
                                  "audifier", "bid", "trace", "image", "intensity"])
def test_actual_existing_caller_hosts_native_settings_and_preserves_semantics(qapp, kind):
    """Native hosting preserves real callbacks/providers and closes its owned surface."""
    from qtpy.QtWidgets import QWidget
    parent, page, model = actual_caller(kind)
    try:
        assert isinstance(page.host, QWidget) and page.host.control is page.app
        notices = []
        page.detectorsChanged.connect(lambda: notices.append(page.get_settings()))
        page.set_settings(copy.deepcopy(SETTINGS))
        assert len(notices) == 1
        data = page.get_settings()
        assert data["detectors"] == SETTINGS["detectors"]
        assert data["windows"] == SETTINGS["windows"]
        assert data["future_setup_metadata"] == SETTINGS["future_setup_metadata"]
        assert page.filetype == "SPC-130"
        assert page.effective_micro_time_resolution == 6.591796875
        if kind in {"background", "irf"}:
            assert model.channels_provider() == data["detectors"]
        elif kind == "count_rate":
            assert model.channels_provider() == page.channels()
        elif kind == "audifier":
            parent._update()
            assert [detector["name"] for detector in model.detectors] == ["donor"]
        elif kind == "trace":
            parent._on_continue()
            assert parent.model.setup_settings["detectors"] == data["detectors"]
        elif kind == "image":
            parent.apply_setup_settings(copy.deepcopy(data))
            assert parent.model.setup_settings["detectors"] == data["detectors"]
        parent.close()
        qapp.processEvents()
        assert page.editor._closing
    finally:
        parent.close()
        page.close()


@pytest.mark.parametrize("kind", ["intensity_dialog", "burst_dialog"])
def test_existing_modal_settings_callers_consume_actual_native_definition(qapp, monkeypatch, kind):
    """The existing accept callback consumes the native definition, not old combo/table fields."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

    captured = []
    def accept(dialog):
        page = dialog.findChild(DetectorWizardPage)
        assert page is not None and page.host.control is page.app
        page.set_settings(copy.deepcopy(SETTINGS))
        captured.append(page)
        dialog.accept()
        return QtWidgets.QDialog.Accepted
    monkeypatch.setattr(QtWidgets.QDialog, "exec_", accept)
    if kind == "intensity_dialog":
        from chisurf.plugins.tttr.intensity_trace.qt_tool import IntensityTrace
        parent = IntensityTrace()
    else:
        from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool
        parent = BurstSelectionTool()
    try:
        if kind == "intensity_dialog":
            parent._open_setup_dialog()
            accepted = parent._detector_settings
            assert accepted is not None
            assert accepted["detectors"] == SETTINGS["detectors"]
            assert accepted["future_setup_metadata"] == SETTINGS["future_setup_metadata"]
        else:
            parent._show_channel_settings()
            assert parent._selected_filetype == "SPC-130"
            assert parent.wizard.detectors == SETTINGS["detectors"]
        assert len(captured) == 1
    finally:
        parent.close()
        for page in captured:
            try:
                page.close()
            except RuntimeError:
                pass


def test_actual_setup_wizard_can_save_a_definition_and_then_finish(qapp, qtbot, tmp_path):
    """The existing enclosing wizard has a real save action before requiring its completion."""
    import json

    from qtpy import QtCore, QtWidgets

    from chisurf.plugins.core.setup_channel_definition.wizard import ChisurfWizard

    wizard = ChisurfWizard()
    qtbot.addWidget(wizard)
    wizard.resize(1200, 900)
    wizard.show()
    page = wizard.filter
    try:
        page.set_settings(copy.deepcopy(SETTINGS))
        qapp.processEvents()
        assert not page.isComplete()
        assert not wizard.button(QtWidgets.QWizard.FinishButton).isEnabled()
        ui = native_driver(page)
        ui.draw(2)
        before = page.get_settings()
        ui.click("save_definition")
        assert page.editor.dialog is not None
        page.editor.dialog.directory = str(tmp_path)
        page.editor.dialog.filename = "definition.json"
        ui.draw(2)
        ui.click([text[:4] for text in ui.painter.texts if text[5] == "Save"][-1])
        assert json.loads((tmp_path / "definition.json").read_text()) == before
        assert page.isComplete()
        qapp.processEvents()
        assert wizard.button(QtWidgets.QWizard.FinishButton).isEnabled()
        qtbot.mouseClick(wizard.button(QtWidgets.QWizard.FinishButton), QtCore.Qt.LeftButton)
        qapp.processEvents()
        assert not wizard.isVisible() and page.editor._closing
    finally:
        wizard.close()
        page.close()


@pytest.mark.parametrize("kind", ["core_wizard", "trace"])
def test_existing_enclosing_layout_allocates_reachable_native_controls(qapp, kind):
    """Existing parent layouts allocate the real editor, including its lower actions."""
    parent, page, _ = actual_caller(kind)
    try:
        page.set_settings(copy.deepcopy(SETTINGS))
        parent.resize(1400, 1000)
        parent.show()
        qapp.processEvents()
        if kind == "trace":
            from qtpy import QtCore, QtTest
            QtTest.QTest.mouseClick(parent.btn_back, QtCore.Qt.LeftButton)
            qapp.processEvents()
        page.host.repaint()
        qapp.processEvents()
        assert page.height() >= 400 and page.host.height() >= 400
        for key in ["read", "macro_time_resolution", "micro_time_resolution", "apply_lut", "optical"]:
            x, y, width, height = page.app.item_rects[key]
            assert 0 <= y < page.host.height() and y + height <= page.host.height(), (key, y, height)
        assert page.get_settings()["detectors"] == SETTINGS["detectors"]
    finally:
        parent.close()
        page.close()
