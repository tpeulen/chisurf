"""The Qt-free background view model."""


def test_background_view_model_estimate_reports_reason():
    """The Qt-free view-model refuses to estimate without files/detectors."""
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    model = BackgroundViewModel()
    assert model.can_estimate() is not None  # no files yet
    model.add_files(["/nonexistent/a.spc"])
    model.channels_provider = lambda: {}
    assert "detector" in (model.can_estimate() or "").lower()
    model.channels_provider = lambda: {"green": {"chs": [0, 8]}}
    assert model.can_estimate() is None


def test_files_pushed_by_the_workflow_are_deduplicated():
    """The hub pushes its raw files in; a repeated file is listed once."""
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    model = BackgroundViewModel(show_channel_definition=False)
    model.add_files(["/nonexistent/a.spc", "/nonexistent/a.spc"])
    assert model.files == ["/nonexistent/a.spc"]
