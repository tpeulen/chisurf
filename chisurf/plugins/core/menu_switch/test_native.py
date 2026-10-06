from chisurf.plugins.core.menu_switch.app import MenuSwitchApp, make_app


def test_native_factory_defaults():
    app = make_app()
    assert isinstance(app, MenuSwitchApp)
    assert "Ready" in app.status


def test_missing_main_window_is_reported():
    app = MenuSwitchApp()
    assert app._resolve_window() is None
