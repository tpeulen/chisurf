"""Headless tests for the LUT tooltip thumbnail renderer (matplotlib Agg)."""

import numpy as np

from chisurf.gui.widgets.wizard.tttr_channeldefinition import lut_thumbnail


def test_render_lut_png_nonempty():
    ntac = np.cumsum(np.abs(np.sin(np.linspace(0, 6, 512))) + 0.1)
    png = lut_thumbnail.render_lut_png(ntac)
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 200


def test_render_lut_tooltip_data_uri_and_cache():
    ntac = np.linspace(0, 4096, 4096)
    uri1 = lut_thumbnail.render_lut_tooltip(ntac)
    assert uri1.startswith("data:image/png;base64,")
    # identical array -> cache hit returns the exact same string object value
    uri2 = lut_thumbnail.render_lut_tooltip(ntac.copy())
    assert uri1 == uri2
    # different array -> different thumbnail
    uri3 = lut_thumbnail.render_lut_tooltip(np.linspace(0, 4096, 2048))
    assert uri3 != uri1


def test_render_empty_lut_does_not_crash():
    png = lut_thumbnail.render_lut_png(np.zeros(0))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
