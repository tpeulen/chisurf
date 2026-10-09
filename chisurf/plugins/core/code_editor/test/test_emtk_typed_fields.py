"""The editor settings' RPC ports take typed numbers, operated with real pointer and keyboard input."""

from __future__ import annotations

import pytest

from chisurf.plugins.core.code_editor.gui.editor_app import CodeEditorApp
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def drv(tmp_path):
    app = CodeEditorApp(project_root=tmp_path)
    app.editor_gui.settings_open = True
    app.editor_gui.docks.focus("editor_settings")
    return Driver(app)


def test_rpc_ports_are_typed_and_clamped_to_the_qt_range(drv):
    model = drv.app.model
    drv.type_into_name("rpc_cmd_port", "9123")
    assert model.rpc_cmd_port == 9123
    drv.type_into_name("rpc_pub_port", "-1")
    assert model.rpc_pub_port == 1024, "a negative port is clamped to the Qt minimum"
    drv.type_into_name("rpc_pub_port", "70000")
    assert model.rpc_pub_port == 65535
    drv.type_into_name("rpc_cmd_port", "port")
    assert model.rpc_cmd_port == 9123, "text that is not a number leaves the port"
