"""The native F-test calculator at parity with the Qt FTestTool.

The Qt tool is driven in a subprocess (this process stays Qt-free): the same two
fits are loaded into the same targets through its "From fit" menu actions, the
same fields are edited, and the resulting statistics and menu entries are compared
with the emtk app's. The menu itself is driven with pointer presses on the rows
where the pixel painter draws them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.testing import PixelPainter, RecordingPainter

from chisurf.plugins.core.f_test.gui.app import LOAD_TARGETS, FTestApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
FIT_DATA = [("decay 1-exp", 1.31, 1024, 3), ("decay 2-exp", 1.02, 1024, 5)]
#: (fit index, target) loads, then (attr, value) edits -- applied in this order on both sides.
LOADS = [(0, "model1"), (1, "model2"), (1, "chi2max")]
EDITS = [("conf_level", 0.99), ("n2", 900), ("npars", 1), ("conf_level_2", 0.68)]
STATS = [
    "chi2_1",
    "n1",
    "chi2_2",
    "n2",
    "conf_level",
    "chi2_min",
    "npars",
    "dof",
    "conf_level_2",
    "chi2_max",
]


def _fits():
    return [
        SimpleNamespace(name=n, chi2r=c, model=SimpleNamespace(n_points=p, n_free=f))
        for n, c, p, f in FIT_DATA
    ]


_QT = r"""
import json, sys
from types import SimpleNamespace
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
data, loads, edits, stats = (json.loads(a) for a in sys.argv[1:5])
fits = [SimpleNamespace(name=n, chi2r=c, model=SimpleNamespace(n_points=p, n_free=f)) for n, c, p, f in data]
import chisurf.gui.widgets.fitting.fitting_client as fc
fc.get_fitting_client = lambda: SimpleNamespace(get_fit_objects=lambda: [fits])
from chisurf.plugins.core.f_test.gui.tool import FTestTool
w = FTestTool()
w._rebuild_fit_menu()
menu = []
for sub_action in w._from_fit_btn.menu().actions():
    sub = sub_action.menu()
    menu += [f"{sub_action.text()}  {a.text()}" for a in sub.actions()]
actions = {f"{f.name}  {a.text()}": a for f in fits
           for s in w._from_fit_btn.menu().actions() if s.text() == f.name for a in s.menu().actions()}
labels = {"model1": "model 1", "model2": "model 2", "chi2max": "max"}
trail = []
for index, target in loads:
    name = fits[index].name
    key = next(k for k in actions if k.startswith(name + "  ") and labels[target] in k)
    actions[key].trigger()
    trail.append({k: getattr(w._model, k) for k in stats})
for attr, value in edits:
    setattr(w._model, attr, value)
    w._on_field_edited(attr)
    trail.append({k: getattr(w._model, k) for k in stats})
print("FACTS" + json.dumps({"menu": menu, "trail": trail,
                            "tooltip": w._from_fit_btn.toolTip()}))
w.close()
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, *(json.dumps(x) for x in (FIT_DATA, LOADS, EDITS, STATS))],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


#: Pointer tests draw small: the toolbar and its menu sit top-left, and the pixel painter's cost
#: grows with the area (1200x800 took ~1.5 s a frame).
POINTER_SIZE = (480, 360)


def _frames(app, n=2, size=POINTER_SIZE, painter=PixelPainter):
    for _ in range(n):
        app.draw(painter(*size) if painter is PixelPainter else painter(), 0, 0, *size)


def _click(app, x, y, size=POINTER_SIZE):
    app.pointer_move(x, y)
    app.press(x, y)
    _frames(app, 1, size)
    app.release()
    _frames(app, 2, size)


def _menu_rows(app):
    """Centre of every drawn menu row (the panel hangs from the title's bottom edge)."""
    from emtk.widgets.menus import ROW_SCALE

    x, y, w, h = app.item_rects["From fit"]
    row_h = PixelPainter(10, 10).line_height() * ROW_SCALE
    return [(x + 60.0, y + h + row_h * (k + 0.5)) for k in range(len(app.fits) * len(LOAD_TARGETS))]


# 1. the same statistics after every one of the same loads and edits (a final-state
#    comparison alone hides a wrong recompute that a later edit overwrites). Both hosts
#    now run the shared model, so this guards the wiring; the rules themselves are
#    checked against the independent reference below.
def test_loads_and_edits_match_the_qt_tool(qt):
    app = FTestApp(fit_provider=_fits)
    app.refresh_fits()
    trail = []
    for index, target in LOADS:
        assert app.load_fit_into(index, target)
        trail.append({k: getattr(app.model, k) for k in STATS})
    for attr, value in EDITS:
        app.model.edit_field(attr, value)
        trail.append({k: getattr(app.model, k) for k in STATS})
    assert len(trail) == len(qt["trail"])
    for step, (ours, theirs) in enumerate(zip(trail, qt["trail"])):
        assert ours == pytest.approx(theirs), step


def _reference_trail():
    """The committed Qt tool's rules written out with scipy, independent of the shared model.

    Load (``FTestTool._load_fit`` before the port): model 1 sets χ²₁, n₁ and solves χ²₂;
    model 2 sets χ²₂, n₂ and recomputes the confidence; χ²-max sets χ²min, params, ν.
    Edit (``_on_field_edited``): χ²₂/n₁/n₂ → confidence; χ²₁/confidence → χ²₂;
    χ²min/params/ν/confidence₂ → χ²max.
    """
    from scipy.stats import f

    s = dict(
        chi2_1=1.1, n1=100, chi2_2=1.0, n2=98, chi2_min=1.0, npars=1, dof=100, conf_level_2=0.95
    )

    def conf():
        s["conf_level"] = f.cdf(s["chi2_1"] / s["chi2_2"], s["n1"], s["n2"])

    def chi2_2():
        s["chi2_2"] = s["chi2_1"] / f.ppf(s["conf_level"], s["n1"], s["n2"])

    def chi2_max():
        p, nu = max(1, s["npars"]), max(1, s["dof"])
        s["chi2_max"] = s["chi2_min"] * (1.0 + p / nu * f.ppf(s["conf_level_2"], p, nu))

    conf()
    chi2_max()
    trail = []
    for index, target in LOADS:
        _name, chi2r, n_points, n_free = FIT_DATA[index]
        nu = max(1, n_points - n_free)
        if target == "model1":
            s["chi2_1"], s["n1"] = chi2r, nu
            chi2_2()
        elif target == "model2":
            s["chi2_2"], s["n2"] = chi2r, nu
            conf()
        else:
            s["chi2_min"], s["npars"], s["dof"] = chi2r, n_free, nu
            chi2_max()
        trail.append({k: s[k] for k in STATS})
    for attr, value in EDITS:
        s[attr] = value
        if attr in ("chi2_2", "n1", "n2"):
            conf()
        elif attr in ("chi2_1", "conf_level"):
            chi2_2()
        if attr in ("chi2_min", "npars", "dof", "conf_level_2"):
            chi2_max()
        trail.append({k: s[k] for k in STATS})
    return trail


def test_loads_and_edits_follow_the_committed_qt_rules():
    app = FTestApp(fit_provider=_fits)
    app.refresh_fits()
    trail = []
    for index, target in LOADS:
        assert app.load_fit_into(index, target)
        trail.append({k: getattr(app.model, k) for k in STATS})
    for attr, value in EDITS:
        app.model.edit_field(attr, value)
        trail.append({k: getattr(app.model, k) for k in STATS})
    for step, (ours, ref) in enumerate(zip(trail, _reference_trail(), strict=True)):
        assert ours == pytest.approx(ref, rel=1e-9), step


# 1. the same menu: one row per fit and target, with the Qt labels
def test_from_fit_menu_matches_the_qt_menu(qt):
    app = FTestApp(fit_provider=_fits)
    app.refresh_fits()
    ours = [f"{fit.name}  {label}" for fit in app.fits for _target, label in LOAD_TARGETS]
    assert ours == qt["menu"]


# 5. end to end: open the menu, press each row where it is drawn
@pytest.mark.parametrize("row", range(6))
def test_pressing_a_drawn_menu_row_loads_that_fit_into_that_target(row):
    app = FTestApp(fit_provider=_fits)
    _frames(app)
    x, y, w, h = app.item_rects["From fit"]
    _click(app, x + w / 2, y + h / 2)
    assert app.menu_open
    _click(app, *_menu_rows(app)[row])
    index, (target, _label) = divmod(row, 3)[0], LOAD_TARGETS[row % 3]
    expected = FTestApp(fit_provider=_fits)
    expected.refresh_fits()
    expected.load_fit_into(index, target)
    assert {k: getattr(app.model, k) for k in STATS} == {
        k: getattr(expected.model, k) for k in STATS
    }
    assert not app.menu_open  # the pick closed it


def test_the_menu_rereads_the_open_fits_each_time_it_opens():
    fits = _fits()[:1]
    app = FTestApp(fit_provider=lambda: list(fits))
    _frames(app)
    x, y, w, h = app.item_rects["From fit"]
    _click(app, x + w / 2, y + h / 2)
    assert len(app.fits) == 1
    _click(app, x + w / 2, y + h / 2)  # close
    fits.append(_fits()[1])
    _click(app, x + w / 2, y + h / 2)  # reopen: the new fit is listed
    assert [f.name for f in app.fits] == ["decay 1-exp", "decay 2-exp"]


# 2. errors reach the user
def test_errors_are_reported_in_the_window():
    app = FTestApp(fit_provider=lambda: [SimpleNamespace(name="broken", chi2r=1.0)])
    app.refresh_fits()
    assert not app.load_fit_into(0, "model1")
    assert "Could not load fit statistics" in app.status
    assert not app.load_fit_into(3, "model1")
    assert "No such open fit" in app.status

    def boom():
        raise RuntimeError("registry gone")

    app = FTestApp(fit_provider=boom)
    app.refresh_fits()
    assert app.fits == [] and "registry gone" in app.status
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    assert any("registry gone" in s for s in painter.strings)


def test_an_empty_menu_says_so(monkeypatch):
    from emtk import im

    app = FTestApp(fit_provider=list)
    rows = []
    original = im.menu_item
    monkeypatch.setattr(
        im,
        "menu_item",
        lambda label, *a, **k: (
            rows.append((label, k.get("enabled", True))),
            original(label, *a, **k),
        )[1],
    )
    _frames(app)
    x, y, w, h = app.item_rects["From fit"]
    _click(app, x + w / 2, y + h / 2)
    assert ("(no open fits)", False) in rows


# 3. spec keys: every field is a model attribute and carries a description
def test_every_spec_field_is_a_model_attribute_with_a_description():
    app = make_app()
    for panel in app.spec["sections"]:
        for field in panel["sections"]:
            assert hasattr(app.model, field["attr"]), field["attr"]
            assert field.get("description"), field["attr"]


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size):
    app = FTestApp(fit_provider=list)
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert {"From fit", "Guide", "?"} <= set(painter.strings)
    app = FTestApp(fit_provider=_fits)
    app.refresh_fits()
    for index, target in LOADS:
        app.load_fit_into(index, target)
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert any(s.startswith("1.3100") for s in painter.strings)  # χ²(1) of the loaded fit
    assert set(app.forms[1].rects) >= {"chi2_max"}


# guide: the From fit step waits for a load, whichever row it was
def test_the_guide_step_on_from_fit_waits_for_a_load():
    app = FTestApp(fit_provider=_fits)
    _frames(app)
    app.tour.start(1)
    assert app.tour.awaiting
    x, y, w, h = app.item_rects["From fit"]
    _click(app, x + w / 2, y + h / 2)
    _click(app, *_menu_rows(app)[4])
    assert not app.tour.awaiting


# 6. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("f_test")
    assert result["ok"], result["output"]


# 7. tooltips, the From fit one as the Qt button's
def test_every_control_has_a_tooltip(qt, monkeypatch):
    sys.path.insert(0, str(REPO))
    from emtk import im

    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("f_test"))["controls_without_tooltip"] == []
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    _frames(make_app(), 1, painter=RecordingPainter)
    assert qt["tooltip"] in tips
