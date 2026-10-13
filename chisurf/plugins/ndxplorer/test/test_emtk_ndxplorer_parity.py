"""The native ndX factory builds the app the way ChiSurf's Qt NdxWindow did.

Both hosts ran ndX's own ``NdxApp``; what could differ was the construction
(the retired ``window.build_ndxplorer_window`` vs ``gui.app.make_app``) and the
closing. The Qt facts were recorded from ``build_ndxplorer_window`` into
``qt_reference.json`` (the window's emtk inventory and menu bar) before the Qt
window was retired, so this test needs no Qt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
# Before ndX is imported: its module root carries a `test` package of its own.
sys.path.insert(0, str(REPO))
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402


@pytest.fixture(autouse=True)
def _scratch_ndx_settings(tmp_path, monkeypatch):
    """ndX's settings folders (dock layout, session store) are scratch ones."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))
    # The factory keeps its dock layout in ChiSurf's native-state store: a scratch one too, or the
    # owner's last focused tab decides which controls the inventory sees.
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "chisurf"))


def _columns():
    rng = np.random.default_rng(7)
    n = 2000
    return {
        "I_DD": rng.poisson(60, n).astype(float),
        "I_DA": rng.poisson(40, n).astype(float),
        "I_AA": rng.poisson(50, n).astype(float),
        "Tau": rng.normal(2.5, 0.3, n),
    }


def _flat(entries, prefix=""):
    """Every menu entry's path ("File/Import/…")."""
    out = []
    for entry in entries:
        label = getattr(entry, "label", "")
        if label:
            out.append(prefix + label)
        out.extend(
            _flat(getattr(entry, "entries", ()) or (), prefix + label + "/" if label else prefix)
        )
    return out


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _make(**kwargs):
    from chisurf.plugins.ndxplorer.gui.app import make_app

    return make_app(**kwargs)


# 1. constructed as the Qt window constructs it
def test_the_factory_wires_what_the_qt_window_wires(tmp_path):
    from chisurf.plugins.ndxplorer.gui.app import make_app

    app = make_app()
    try:
        assert app.chisurf_rpc is not None, "Send selection to needs ChiSurf's client"
        assert app.session_autosave is True
        # Kept, as the Qt window keeps it -- in ChiSurf's native-state store
        # (attach_native_state), where every emtk app's layout lives, rather than in
        # ndX's own settings file the Qt window uses.
        assert app.docks.store is not None and app.docks.store.path is not None
        assert "ndxplorer" in Path(app.docks.store.path).name
    finally:
        app.close()
    app = make_app(session_autosave=False)
    try:
        assert app.session_autosave is False
    finally:
        app.close()


#: What the legacy Qt window (build_ndxplorer_window) drew on _columns(): its emtk
#: inventory and its flattened menu bar, recorded before the Qt host is retired.
QT_REFERENCE = HERE / "qt_reference.json"


def test_same_controls_as_the_qt_window_on_the_same_table():
    from ndxplorer.core.data_source import DataSource

    qt = json.loads(QT_REFERENCE.read_text(encoding="utf-8"))
    app = _make(session_autosave=False)
    try:
        app.model.set_source(DataSource.from_columns(_columns()))
        app.data_changed()
        inv = emtk_inventory(app)
        ours = {"controls": inv["controls"], "menus": _flat(app.menubar.menus)}
        # The factory's app adds ChiSurf's Guide and quick reference to Help; the legacy Qt host has neither.
        added = {"Help/Guide", "Help/Quick reference"}
        assert [m for m in ours["menus"] if m not in added] == qt["menus"]
        assert added <= set(ours["menus"])

        # Every control of the Qt-hosted app is drawn by the factory's app too -- in full,
        # or clipped: the factory gives Plot controls a wider column (split 0.44), so the
        # path field's hint shows as "Drop folder her…".
        def present(text):
            return text in ours["controls"] or any(
                c.rstrip("…") and text.startswith(c.rstrip("…"))
                for c in ours["controls"]
                if len(c) > 6
            )

        assert [c for c in qt["controls"] if not present(c)] == []
    finally:
        app.close()


# 2. closing the host closes the app once (session kept, Global View slot emptied)
def test_closing_the_host_closes_the_app_once(monkeypatch):
    app = _make(session_autosave=False)
    closes = []
    original = type(app).close
    monkeypatch.setattr(type(app), "close", lambda self: (closes.append(1), original(self)))
    app.set_frame_request_callback(lambda: None)  # a host attached
    app.set_frame_request_callback(None)  # its window closed
    assert app._chisurf_closed
    app.close()  # and a second close is harmless
    from chisurf.plugins.ndxplorer.global_view_slot import published_group

    assert published_group() is None


def test_a_never_hosted_app_is_not_closed_by_a_none_callback():
    app = _make(session_autosave=False)
    try:
        app.set_frame_request_callback(None)
        assert not app._chisurf_closed
    finally:
        app.close()


# 4. draws, empty and with data, both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_with_data(size):
    from ndxplorer.core.data_source import DataSource

    app = _make(session_autosave=False)
    try:
        painter = _draw(app, size)
        assert "Plot controls" in painter.strings
        app.model.set_source(DataSource.from_columns(_columns()))
        app.data_changed()
        painter = _draw(app, size)
        assert "2000" in painter.strings
    finally:
        app.close()


# 6. no Qt
def test_port_is_qt_free():
    result = qt_free("ndxplorer")
    assert result["ok"], result["output"]


# 7. tooltips
def test_every_control_has_a_tooltip():
    app = build_emtk_app("ndxplorer")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()


def test_load_example_button_opens_the_simulated_table_and_releases_the_tour(tmp_path, monkeypatch):
    """The empty map offers Load example; pressing it opens the known table and the tour step is done."""
    from emtk.testing import Driver

    from chisurf.plugins.ndxplorer.gui.app import make_app

    monkeypatch.setattr("chisurf.plugins.demo_cache.cache_folder", lambda plugin: tmp_path / plugin)
    app = make_app(session_autosave=False)
    try:
        driver = Driver(app, (1200, 800))
        driver.settle()
        assert app.model.source is None
        app.tour.start(1)
        driver.frame(3)
        assert app.tour.awaiting
        x, y, w, h = app.tour.get_target_rect("load_example")
        driver.click((x + w / 2, y + h / 2))
        driver.settle()
        assert app.model.source is not None
        assert not app.tour.awaiting
        driver.frame(3)
        # While the tour stays on its example step the button is kept within reach ...
        assert app.tour.get_target_rect("load_example") is not None
        app.tour.next()
        driver.frame(3)
        # ... and once it moves on, the example is offered only over an empty map.
        assert app.tour.get_target_rect("load_example") is None
    finally:
        app.close()
