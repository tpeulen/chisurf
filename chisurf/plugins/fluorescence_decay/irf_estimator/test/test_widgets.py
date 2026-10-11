"""The native IRF estimator app builds with its controls (the Qt tool creation test, ported)."""


def test_irf_estimator_app_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app

    app = make_app()
    try:
        form = app.form_model
        # estimate / save / transfer exist and are disabled until a decay is loaded
        assert [
            form.enabled(n) for n in ("request_estimate", "request_save", "request_transfer")
        ] == [
            False,
            False,
            False,
        ]
    finally:
        app.close()
