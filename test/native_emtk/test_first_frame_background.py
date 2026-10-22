"""A hub's first frame does not import or build the tool it shows: that runs on a worker thread.

The first frame of a hub used to pay for the embedded tool (its imports, a database, a dictionary) -- 200 ms to
1.6 s on the UI thread. These tests hold the worker on a gate, so they prove that the first frame returns while
the tool is still being made, shows the "Opening" placeholder, and adopts the tool on a later frame.
"""

from __future__ import annotations

import threading

import pytest
from emtk.app import ImApp
from emtk.testing import RecordingPainter


@pytest.fixture(autouse=True)
def private_settings(tmp_path, monkeypatch):
    for name, suffix in [
        ("CHISURF_SETTINGS_DIR", "settings"),
        ("MMFDB_SETTINGS_DIR", "mmfdb"),
        ("MMFDB_DATABASE_PATH", "mmfdb.sqlite"),
    ]:
        monkeypatch.setenv(name, str(tmp_path / suffix))


class Tool(ImApp):
    def __init__(self):
        super().__init__(lambda: None)


def gated(gate, made):
    def factory():
        gate.wait(30)
        made.append(threading.current_thread().name)
        return Tool()

    return factory


def strings(app, size=(1100, 720)):
    painter = RecordingPainter()
    app.draw(painter, 0, 0, *size)
    return painter.strings


def test_background_build_collects_once_and_joins():
    from chisurf.emtk.background_build import BackgroundBuild, join_all

    woke = []
    build = BackgroundBuild(wake=lambda: woke.append(1))
    gate = threading.Event()
    assert build.start({"a": lambda: gate.wait(30) or 1, "b": lambda: 1 / 0})
    assert build.busy and build.building("a") and not build.start({"c": lambda: 3})
    assert build.collect() is None  # still running
    gate.set()
    join_all()
    done = build.collect()
    assert done["a"] == (1, None) and isinstance(done["b"][1], ZeroDivisionError)
    assert woke == [1] and not build.busy and build.collect() is None


def test_tool_hub_first_frame_shows_a_placeholder_and_adopts_the_tool_later():
    from chisurf.emtk.background_build import join_all
    from chisurf.emtk.tool_hub import ToolHubApp

    gate, made = threading.Event(), []
    hub = ToolHubApp(
        "Hub",
        [
            {"name": "First tool", "role": "first", "factory": gated(gate, made)},
            {"name": "Second", "role": "second", "factory": Tool},
        ],
    )
    try:
        shown = strings(hub)
        assert hub.building and hub.child is None and hub.animating()
        assert any("Opening First tool" in s for s in shown)
        gate.set()
        join_all()
        strings(hub)
        assert isinstance(hub.child, Tool) and not hub.building
        assert made and made[0] != threading.current_thread().name  # made on the worker
    finally:
        gate.set()
        hub.close()


def test_tool_hub_ensure_child_joins_a_build_under_way():
    from chisurf.emtk.tool_hub import ToolHubApp

    gate, made = threading.Event(), []
    hub = ToolHubApp("Hub", [{"name": "First", "role": "first", "factory": gated(gate, made)}])
    strings(hub)
    threading.Timer(0.05, gate.set).start()
    assert isinstance(hub.ensure_child("first"), Tool) and len(made) == 1  # joined, not built twice
    hub.close()


def test_the_imaging_pipeline_builds_the_shown_step_in_the_background():
    from chisurf.emtk.background_build import join_all
    from chisurf.plugins.microscopy.imaging_tools.gui.app import ImagingToolsApp

    class Client:
        def get_current(self):
            return {"detectors": {"green": {"chs": [0]}}}

        def set_current(self, setup):
            pass

    gate, made = threading.Event(), []
    factory = gated(gate, made)
    hub = ImagingToolsApp(client=Client(), factories={"browser": lambda **_kw: factory()})
    try:
        shown = strings(hub)
        assert hub.building and hub.child is None
        assert any(s.startswith("Opening") for s in shown)
        gate.set()
        join_all()
        strings(hub)
        assert isinstance(hub.child, Tool) and not hub.error and len(made) == 1
    finally:
        gate.set()
        hub.close()


def test_setup_store_is_read_off_the_first_frame_and_a_newer_read_wins(tmp_path, monkeypatch):
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.emtk.channel_setup_bar import SetupToolbar

    gate = threading.Event()
    model = ChannelDefinition()
    monkeypatch.setattr(model, "db", None, raising=False)
    monkeypatch.setattr(
        model,
        "read_setups_payload",
        lambda: gate.wait(30) and {"setups": {"old": {}}, "last_used": "old"},
    )
    page = type("Page", (), {"model": model, "status": ""})()
    bar = SetupToolbar(page)
    bar.reload_async()
    assert bar.loading and "Loading" in page.status
    model.apply_setups_payload({"setups": {"new": {}}})  # a save meanwhile re-read the store
    gate.set()
    bar.wait()
    bar.poll()
    assert not bar.loading and sorted(model.setups) == [
        "new"
    ]  # the stale background read is dropped


def test_registry_prefetch_reports_ready_once_read():
    from chisurf.core.registry import catalog

    catalog.refresh()  # an earlier test in the process may have read the registries already
    assert not catalog.ready()
    catalog.prefetch()
    catalog._prefetch_thread.join(60)
    assert catalog.ready() and catalog.prefetch()


def test_background_job_runs_inline_when_no_thread_can_start(monkeypatch):
    """The Pyodide shape: ThreadPoolExecutor.submit cannot spawn a worker.

    BackgroundJob (the FCS Filter Calculator's worker, among others) then
    runs the work inline and hands poll() an already finished future, so
    publication and error reporting flow the exact same path as on a
    thread-capable host -- the real-browser run caught the open dying with
    ``RuntimeError: can't start new thread``.
    """
    from concurrent.futures import ThreadPoolExecutor

    from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

    def no_workers(self, fn):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(ThreadPoolExecutor, "submit", no_workers)

    job = BackgroundJob()
    got, failed = [], []
    assert job.start(lambda: "done", got.append, failed.append)
    assert job.running  # the finished future keeps the job busy until poll()
    job.poll()
    assert got == ["done"] and failed == []
    assert not job.running
    job.close()

    # An inline failure reaches the error callback through the same poll().
    job = BackgroundJob()
    boom = RuntimeError("work exploded")
    assert job.start(lambda: (_ for _ in ()).throw(boom), got.append, failed.append)
    job.poll()
    assert failed == [boom] and got == ["done"]
    job.close()


def test_registry_prefetch_runs_inline_when_no_thread_can_start(monkeypatch):
    """Same shape for the registry prefetch: compile inline, report ready."""
    import threading

    from chisurf.core.registry import catalog

    def no_start(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", no_start)
    catalog.refresh()
    catalog._prefetch_thread = None
    assert not catalog.ready()
    assert catalog.prefetch() and catalog.ready()


def test_plugin_manifests_are_read_once_and_handed_out_as_copies(monkeypatch):
    from chisurf.emtk import plugins

    first = plugins.manifests()
    monkeypatch.setattr(
        plugins, "_read_manifests", lambda root: pytest.fail("the shipped tree was walked again")
    )
    second = plugins.manifests()
    assert first == second and first is not second
    second[next(iter(second))]["id"] = "changed"
    assert plugins.manifests() == first


def test_i18n_catalogs_are_parsed_once(monkeypatch):
    from chisurf.emtk import i18n

    i18n.install()
    monkeypatch.setattr(
        i18n, "read_catalog", lambda *a, **k: pytest.fail("a catalog was parsed again")
    )
    i18n.install()


def test_chimol_view_starts_in_the_background_and_says_so(monkeypatch):
    from emtk import im
    from emtk.testing import Driver

    from chisurf.emtk.chimol_view import ChimolView

    gate, fake = threading.Event(), object()
    view = ChimolView()
    monkeypatch.setattr(view, "_make", lambda warm=False: gate.wait(30) and fake)

    class Host(ImApp):
        def __init__(self):
            super().__init__(self.render)

        def render(self):
            im.begin("view", (0, 0, 800, 600))
            assert view.draw()  # not "unavailable" while it starts
            im.end()

    driver = Driver(Host(), (800, 600))
    painter = driver.frame()
    assert view.starting and view.app is None
    assert any("Starting ChiMOL" in s for s in painter.strings)
    assert (
        view.screen_points([[0.0, 0.0, 0.0]])[0].size == 0
    )  # per-frame queries never wait for the start
    gate.set()
    assert view.ensure() and view.app is fake and not view.starting  # joins the start
