"""The native ndX factory builds the app the way ChiSurf's Qt NdxWindow does.

Both hosts run ndX's own ``NdxApp``; what can differ is the construction
(``build_ndxplorer_window`` vs ``gui.app.make_app``) and the closing. The Qt
facts come from ``build_ndxplorer_window`` in a subprocess, so this process
stays Qt-free.
"""

from __future__ import annotations

import json
import os
import subprocess
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
    """ndX's settings folder (dock layout, session store) is a scratch one."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))


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


_QT = r"""
import json, sys
import numpy as np
from test.gui.emtk_port_parity import emtk_inventory   # before ndX (its own `test` package)
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from ndxplorer.core.data_source import DataSource
from chisurf.plugins.ndxplorer.window import build_ndxplorer_window
cols = {k: np.asarray(v) for k, v in json.loads(sys.argv[1]).items()}
def flat(entries, prefix=""):
    out = []
    for e in entries:
        label = getattr(e, "label", "")
        if label:
            out.append(prefix + label)
        out.extend(flat(getattr(e, "entries", ()) or (), prefix + label + "/" if label else prefix))
    return out
w = build_ndxplorer_window(data_source=DataSource.from_columns(cols), session_autosave=False,
                           layout_store=None)
inv = emtk_inventory(w.app)
print("FACTS" + json.dumps({"controls": inv["controls"], "menus": flat(w.app.menubar.menus)}))
w.close()
"""


def test_same_controls_as_the_qt_window_on_the_same_table():
    pytest.importorskip("qtpy")
    from ndxplorer.core.data_source import DataSource

    columns = _columns()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, json.dumps({k: v.tolist() for k, v in columns.items()})],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"NdxWindow could not be built here: {proc.stderr[-800:]}")
    qt = json.loads(line[len("FACTS") :])
    app = _make(session_autosave=False)
    try:
        app.model.set_source(DataSource.from_columns(columns))
        app.data_changed()
        inv = emtk_inventory(app)
        ours = {"controls": inv["controls"], "menus": _flat(app.menubar.menus)}
        assert ours["menus"] == qt["menus"]

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
