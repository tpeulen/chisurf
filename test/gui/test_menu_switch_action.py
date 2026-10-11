"""Menu Switch operates the actual Main menu/ribbon and persisted preference."""

import copy

import pytest
import yaml


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    """Construct the production host with real widgets and isolated preferences."""
    from qtpy import QtCore

    import chisurf as cs
    import chisurf.gui as gui
    import chisurf.gui.widgets
    from chisurf.core import settings
    from chisurf.core.api.context import PluginContext
    from chisurf.gui.main import Main

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    real_settings = QtCore.QSettings

    class IsolatedSettings(real_settings):
        """Keep Qt layout persistence inside this test's actual INI store."""

        def __init__(self, *_args, **_kwargs):
            super().__init__(str(tmp_path / "main.ini"), real_settings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    gui_settings = copy.deepcopy(settings.cs_settings.get("gui", {}))
    gui_settings["use_ribbon_interface"] = False
    monkeypatch.setitem(settings.cs_settings, "gui", gui_settings)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    if getattr(cs, "console", None) is None:
        console = cs.gui.widgets.ipython.QIPythonWidget()
        console.history_widget = None
        monkeypatch.setattr(cs, "console", console, raising=False)
    main = Main()
    main.plugin_context = PluginContext(main_window=main)
    # Production sets this in the post-show stage that restores the saved interface.
    main._ribbon_integration = None
    main.resize(1400, 900)
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    gui.setup_gui(qapp, main, stage="populate_plugins")
    main.show()
    qapp.processEvents()
    yield main
    # Close while isolated QSettings is still installed, avoiding user-state writes.
    main._save_window_state = lambda: None
    main.hide()
    main.deleteLater()
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    qapp.processEvents()


def preference(tmp_path):
    """Read the same on-disk setting used on the next real application startup."""
    path = tmp_path / "settings" / "settings_chisurf.yaml"
    return yaml.safe_load(path.read_text())["gui"]["use_ribbon_interface"]


def test_real_menu_and_ribbon_actions_toggle_main_and_save_preference(main_window, qapp, tmp_path):
    """Both real launcher routes invoke the current host; neither opens a dummy window."""
    from qtpy import QtWidgets

    main = main_window
    assert main._ribbon_integration is None
    before_children = dict(getattr(main, "_plugin_windows", {}))
    menu_actions = [
        action
        for action in main.findChildren(QtWidgets.QAction)
        if action.text().split(" (")[0] == "Menu Switch"
    ]
    assert menu_actions, "Production plugin discovery must expose the host action in its menu."
    menu_actions[0].trigger()
    qapp.processEvents()
    assert main._ribbon_integration is not None
    assert preference(tmp_path) is True
    assert dict(getattr(main, "_plugin_windows", {})) == before_children
    ribbon = main._ribbon_integration.ribbon_bar
    buttons = [
        button
        for button in ribbon.findChildren(QtWidgets.QToolButton)
        if button.text().split(" (")[0] == "Menu Switch"
    ]
    assert buttons, "The same declared action must be discoverable from the ribbon."
    button = buttons[0]
    category = button.parent()
    while category is not None and category not in ribbon.categories().values():
        category = category.parent()
    if category is not None:
        ribbon.setCurrentCategory(category)
    ribbon.showRibbon()
    qapp.processEvents()
    assert main.grab().save(str(tmp_path / "after-ribbon.png"))
    button.click()
    qapp.processEvents()
    assert main._ribbon_integration is None
    assert preference(tmp_path) is False
    assert dict(getattr(main, "_plugin_windows", {})) == before_children
    assert main.grab().save(str(tmp_path / "after-menu.png"))
