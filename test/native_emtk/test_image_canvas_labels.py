"""Shared image canvases must identify the map and its displayed unit."""

import numpy as np
from emtk import im
from emtk.testing import RecordingPainter

from chisurf.emtk.image_canvas import ImageCanvas


def test_scalar_map_legend_uses_the_analysis_label_and_unit():
    painter = RecordingPainter()
    canvas = ImageCanvas("mean_micro_time", image_label="Mean micro-time", image_unit="ns")
    with im.frame(painter, (0, 0, 800, 600)):
        canvas.draw(np.arange(9, dtype=float).reshape(3, 3))
    assert "Mean micro-time (ns)" in painter.strings
    assert "Colormap" in painter.strings


def test_existing_canvas_label_remains_intensity_by_default():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 800, 600)):
        ImageCanvas("intensity").draw(np.ones((3, 3)))
    assert "Intensity" in painter.strings


def test_shared_canvas_translates_axis_and_map_labels_in_all_six_locales():
    from emtk import i18n as toolkit_i18n

    from chisurf.emtk.i18n import install, set_locale

    expected = {
        "en": "Mean micro-time (ns)",
        "de": "Mittlere Mikrozeit (ns)",
        "fr": "Microtemps moyen (ns)",
        "es": "Microtiempo medio (ns)",
        "pt": "Microtempo médio (ns)",
        "ru": "Среднее микровремя (ns)",
    }
    previous = toolkit_i18n.get_locale()
    try:
        install("en")
        for locale, label in expected.items():
            set_locale(locale)
            painter = RecordingPainter()
            with im.frame(painter, (0, 0, 800, 600)):
                ImageCanvas(
                    "mean_micro_time", image_label="Mean micro-time", image_unit="ns"
                ).draw(np.ones((3, 3)))
            assert label in painter.strings
    finally:
        set_locale(previous)
