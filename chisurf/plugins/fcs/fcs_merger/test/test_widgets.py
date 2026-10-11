"""The merger manifest points at the one declared native app."""


def test_fcs_merger_native_factory():
    from chisurf.plugins.fcs.fcs_merger.gui.app import MergerApp, create_app

    app = create_app()
    try:
        assert isinstance(app, MergerApp)
        assert app.form is not None
    finally:
        app.close()
