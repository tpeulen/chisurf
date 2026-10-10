"""The trajectory FRET tool keeps its standalone launcher (the Qt hub that hosted it is retired)."""


def test_standalone_fret_launcher_uses_the_shared_native_entrypoint(monkeypatch):
    """The shipped GUI script keeps its plugin identity and native launch options."""
    from chisurf.emtk import __main__ as native
    from chisurf.plugins.traj.fret_trajectory import __main__ as fret

    calls = []
    monkeypatch.setattr(native, "main", lambda args: calls.append(args) or 0)
    assert fret.main(["--size", "1100x780"]) == 0
    assert calls == [["--plugin", "traj_fret", "--size", "1100x780"]]
