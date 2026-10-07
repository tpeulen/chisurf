"""The remaining trajectory Qt hub hosts the native FRET surface during retirement."""

from threading import Event


def test_legacy_hub_fret_factory_hosts_the_existing_native_app(qapp, qtbot):
    """Removing the legacy selector cannot remove the FRET tab from its live caller."""
    from chisurf.plugins.traj.fret_trajectory.app import FretTrajectoryApp
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    factory = dict(TrajectoryToolsTool._tool_factories(object()))["FRET"]
    widget = factory()
    qtbot.addWidget(widget)
    assert isinstance(getattr(widget, "control", None), FretTrajectoryApp)
    widget.close()


def test_hub_close_closes_only_its_owned_native_fret_host_once(qapp, qtbot, monkeypatch):
    """Closing the parent cancels queued native work without closing the other tabs."""
    from chisurf.plugins.traj.fret_trajectory.app import FretTrajectoryApp
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    hub = TrajectoryToolsTool()
    qtbot.addWidget(hub)
    host = hub._tools["FRET"]
    assert isinstance(getattr(host, "control", None), FretTrajectoryApp)
    app = host.control
    blocked = Event()
    started = Event()

    def busy_worker():
        """Keep the one real worker occupied while a second job remains queued."""
        started.set()
        return blocked.wait(timeout=5)

    running = app._executor.submit(busy_worker)
    assert started.wait(timeout=1)
    queued = app._executor.submit(lambda: "should not run")
    closed = []
    original_close = host.close

    def close_owned_host():
        """Record real host closure and preserve its control cleanup."""
        closed.append("FRET")
        return original_close()

    monkeypatch.setattr(host, "close", close_owned_host)
    for name, widget in hub._tools.items():
        if name != "FRET":
            monkeypatch.setattr(widget, "close", lambda name=name: closed.append(name))
    try:
        hub.close()
        hub.close()
        assert closed == ["FRET"]
        assert host._control_closed
        assert queued.cancelled()
    finally:
        blocked.set()
        running.result(timeout=1)
        app.close()


def test_standalone_fret_launcher_uses_the_shared_native_entrypoint(monkeypatch):
    """The shipped GUI script keeps its plugin identity and native launch options."""
    from chisurf.emtk import __main__ as native
    from chisurf.plugins.traj.fret_trajectory import __main__ as fret

    calls = []
    monkeypatch.setattr(native, "main", lambda args: calls.append(args) or 0)
    assert fret.main(["--size", "1100x780"]) == 0
    assert calls == [["--plugin", "traj_fret", "--size", "1100x780"]]
