def test_view_model_channel_state():
    from chisurf.plugins.tttr.audifier.gui.view_model import AudifierViewModel

    m = AudifierViewModel()
    m.set_detectors_from_settings({"detectors": {"green": {"chs": [0, 1]}, "red": {"chs": [2]}}})
    assert m.channels == [0, 1, 2]
    assert len(m.detectors) == 2
    # colours are Qt-free (r, g, b) float tuples
    assert all(len(d["color"]) == 3 for d in m.detectors)
    m.set_channel(0, enabled=False)
    assert 0 not in m.selected_channels()
    assert m.can_render() is not None  # no data loaded
