from __future__ import annotations

import copy


def test_acquisition_output_path_helper_falls_back_to_working_path(monkeypatch, tmp_path):
    """The acquisition output helper should use the working path fallback."""
    from chisurf import settings
    from chisurf.plugins.core.acq.gui import app

    monkeypatch.setattr(settings, "working_path", tmp_path)
    monkeypatch.setitem(settings.gui, "acquisition", {})

    assert app.default_acquisition_output_path() == str(tmp_path / "acquisition")
    assert app.configured_output_path() == ""


def test_native_acquisition_model_uses_configured_output_path(monkeypatch, tmp_path):
    """The native acquisition model prefills the saved standard output folder."""
    from chisurf import settings
    from chisurf.plugins.core.acq.gui.app import AcquisitionNativeModel

    output_path = tmp_path / "measurements"
    monkeypatch.setitem(settings.gui, "acquisition", {"output_path": str(output_path)})

    assert AcquisitionNativeModel().output_folder == str(output_path)


def test_acquisition_settings_widget_persists_output_path(qtbot, monkeypatch, tmp_path):
    """The setup panel should persist the standard output folder setting."""
    from chisurf import settings
    from chisurf.plugins.core.acq.gui.settings_panel import AcquisitionSettingsWidget

    saved = {}

    def fake_save(acquisition_settings):
        saved.clear()
        saved.update(copy.deepcopy(acquisition_settings))
        return True

    monkeypatch.setattr(
        "chisurf.core.settings.settings_utils.set_acquisition_settings",
        fake_save,
    )
    monkeypatch.setitem(settings.gui, "acquisition", {})
    monkeypatch.setattr(
        AcquisitionSettingsWidget,
        "_on_device_type_changed",
        lambda self, device_type: None,
    )

    widget = AcquisitionSettingsWidget()
    qtbot.addWidget(widget)

    output_path = tmp_path / "acquisition"
    widget.output_path_edit.setText(str(output_path))
    widget._save_settings()

    assert saved["output_path"] == str(output_path)
    assert widget.config["output_path"] == str(output_path)
    assert widget.output_path_edit.text() == str(output_path)
