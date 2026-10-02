"""Layout of the IRF and background window at 1200x800 and 800x600.

Defects fixed: nine stacked buttons including two full-width ones, Stop live while idle, short fields as wide as
the panel, icons touching labels.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_disjoint, assert_icons_clear, assert_inside, assert_texts_apart, draw,
)

from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = create_app()
    pass
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_actions_are_wrapped_rows(drawn):
    app, _p, size = drawn
    rects = app.item_rects
    names = ["toolAction_run", "Stop", "send_to_mle", "patterns", "guide", "help"]
    assert_disjoint(rects, names)
    for n in names:
        assert rects[n][2] < 0.6 * size[0] * 0.4 + 60, f"{n} is stretched: {rects[n]}"


def test_short_fields_icons_and_texts(drawn):
    app, painter, size = drawn
    fields = app.irf_gui.form_state.rects
    for name in ("min_photons", "photon_window", "time_window_ms", "baseline_quantile", "micro_time_binning"):
        assert fields[name][2] <= 140, (name, fields[name])
    assert_icons_clear(painter)
    assert_texts_apart(painter, region=(0.0, 0.0, size[0] * 0.4, size[1]))
