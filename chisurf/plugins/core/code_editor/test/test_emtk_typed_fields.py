"""The editor settings' RPC ports step with the arrow keys and stay in the Qt range."""

from __future__ import annotations

import pytest
from emtk import keys

from chisurf.plugins.core.code_editor.gui.editor_app import CodeEditorApp
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def drv(tmp_path):
    app = CodeEditorApp(project_root=tmp_path)
    app.editor_gui.settings_open = True
    app.editor_gui.docks.focus("editor_settings")
    return Driver(app)


def step_name(drv, name, code, times=1):
    """Click the integer field *name* and press an arrow key *times* times."""
    drv.click(drv.rect(name))
    for _ in range(times):
        drv.press(code)


def test_rpc_ports_step_with_the_arrows_and_stay_in_the_qt_range(drv):
    model = drv.app.model
    start = model.rpc_cmd_port
    step_name(drv, "rpc_cmd_port", keys.KEY_UP)
    assert model.rpc_cmd_port == start + 1
    model.rpc_pub_port = 1024
    step_name(drv, "rpc_pub_port", keys.KEY_DOWN)
    assert model.rpc_pub_port == 1024, "the Qt minimum is a floor"
    step_name(drv, "rpc_pub_port", keys.KEY_UP)
    assert model.rpc_pub_port == 1025
    model.rpc_pub_port = 65535
    step_name(drv, "rpc_pub_port", keys.KEY_UP)
    assert model.rpc_pub_port == 65535, "the Qt maximum is a ceiling"
    drv.type_into_name("rpc_cmd_port", "port")
    assert model.rpc_cmd_port == start + 1, "text that is not a number leaves the port"
