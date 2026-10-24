"""The app: windows in both modes, tooltips, guide targets, help, ndX hosting.

Drawn headless (emtk's RecordingPainter): no window, no GPU -- the same code
the page and the desktop run.
"""
import json
import pathlib

import pytest

pytest.importorskip("emtk")
tttrlib = pytest.importorskip("tttrlib")
if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib without the simulator", allow_module_level=True)

from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.burst.fret_check.app import frame  # noqa: E402

APP_DIR = pathlib.Path(frame.__file__).parent


def grab(app, size, frames=2):
    """Run *frames* frames of *app* (drawing recorded, not rasterised)."""
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def _sections(spec):
    for sec in spec.get("sections", []):
        yield sec
        yield from _sections(sec)


@pytest.fixture(scope="module")
def app():
    a = frame.make_app(runner="sync")
    a.session.demo = "PIE MFD (0/8, 1/9)"
    a.session.simulate()
    grab(a, (1300, 860), frames=3)
    return a


def test_every_control_has_a_tooltip():
    view = json.loads((APP_DIR / "view.json").read_text())
    missing = []
    for sec in _sections(view):
        if sec.get("type") in ("value", "choice", "toggle") and not sec.get("description"):
            missing.append(sec.get("attr"))
        for b in sec.get("buttons", []):
            if not b.get("description"):
                missing.append(b.get("action"))
    assert not missing, missing


def test_every_action_exists_on_the_session():
    view = json.loads((APP_DIR / "view.json").read_text())
    s = frame.Session(runner="sync")
    for sec in _sections(view):
        for b in sec.get("buttons", []):
            assert callable(getattr(s, b["action"], None)), b["action"]
        if sec.get("attr"):
            assert hasattr(s, sec["attr"]), sec["attr"]
        if sec.get("source"):
            assert hasattr(s, sec["source"]), sec["source"]
        if sec.get("options_source"):
            assert callable(getattr(s, sec["options_source"])), sec["options_source"]


def test_guide_targets_exist():
    guide = json.loads((APP_DIR / "guide.json").read_text())
    view = json.loads((APP_DIR / "view.json").read_text())
    names = {"data_loaded", "analysed"} | set(frame.WINDOWS)
    for sec in _sections(view):
        names.add(sec.get("attr"))
        names.update(b["action"] for b in sec.get("buttons", []))
    for step in guide["steps"]:
        target = step.get("target") or {}
        key = next((target[k] for k in ("name", "action", "attr") if target.get(k)), None)
        assert key is None or key in names, (step["title"], key)
        if step.get("window"):
            assert step["window"] in frame.WINDOWS, step["window"]


def test_help_says_data_stays_local():
    text = (APP_DIR / "help.md").read_text()
    head = text[: text.index("# Opening data")]
    assert "in your browser" in head and "server" in head
    assert "# Privacy" in text


@pytest.mark.parametrize("mode", ["simple", "advanced"])
def test_windows_of_each_mode_draw(app, mode):
    app.session.mode = mode
    grab(app, (1300, 860), frames=2)
    for key, (_title, _region, modes) in frame.WINDOWS.items():
        assert app.docks.windows[key].visible == (mode in modes), key
        if mode in modes:
            app.docks.focus(key)
            grab(app, (1300, 860), frames=2)
    app.session.mode = "simple"


def test_help_and_guide_open(app):
    if app.help is None:
        pytest.skip("emtk without help_guide")
    app.show_help()
    grab(app, (1300, 860), frames=2)
    app.help.hide()
    app.start_guide()
    grab(app, (1300, 860), frames=2)
    assert app.tour.active
    app.tour.stop()


def test_ndx_gets_the_burst_table(app):
    if not app.ndx.available():
        pytest.skip("ndX not importable")
    app.session.mode = "advanced"
    grab(app, (1300, 860), frames=2)
    app.docks.focus("ndx")
    grab(app, (1300, 860), frames=3)
    assert app.ndx.app is not None, app.ndx.error
    assert len(app.ndx.app.model.source) == app.session.bursts.n
    assert "Tau (green)" in app.ndx.app.model.parameter_names
    app.session.mode = "simple"


def test_exports(app, tmp_path, monkeypatch):
    got = {}
    app.session.download = lambda name, data, mime: got.setdefault(name, data)
    app.session.export_csv()
    app.session.export_report()
    csv_name = next(n for n in got if n.endswith(".csv"))
    header = got[csv_name].decode().splitlines()[0]
    assert "Proximity ratio" in header and "QC flags" in header
    report = json.loads(next(v for n, v in got.items() if n.endswith(".json")))
    assert report["experiment"]["kind"] == "MFD (PIE + pol)"


# -- the analysis as a job (a thread here, a Web Worker in a page) ---------- #
threads = pytest.mark.skipif(frame.Session().runner != "jobs", reason="no threads here")


@threads
def test_the_analysis_runs_as_a_job_and_reports_progress():
    s = frame.Session(runner="jobs")
    s.demo = "cw 2c"
    s.simulate()
    assert s.busy and s.job is not None
    seen = set()
    while s.poll():
        if s.progress is not None:
            seen.add(round(s.progress, 1))
    assert not s.busy and s.bursts is not None and s.bursts.n > 50, s.status
    assert len(seen) >= 1
    # Apply: the same measurement, re-analysed from the job's cache.
    s.min_photons = 60
    s.run()
    s.wait()
    assert s.bursts.n > 0 and int(s.bursts.size.min()) >= 60


@threads
def test_a_file_goes_through_the_job(tmp_path):
    from chisurf.plugins.burst.fret_check.sim import SCENARIOS, simulate

    data = simulate(next(sc for sc in SCENARIOS if sc.name == "cw 2c"))
    path = tmp_path / "cw.ptu"
    data.write(str(path))
    s = frame.Session(runner="jobs")
    s.open(str(path))
    s.wait()
    assert s.bursts is not None and s.bursts.n > 50, s.status
    assert s.exp.donor_channels == [0] and s.exp.acceptor_channels == [1]


@threads
def test_cancel_stops_the_job_and_keeps_the_page_usable():
    s = frame.Session(runner="jobs")
    s.demo = "PIE 2c"
    s.simulate()
    s.cancel()
    s.wait()
    assert not s.busy and s.status == "Cancelled."
    s.simulate()
    s.wait()
    assert s.bursts is not None
