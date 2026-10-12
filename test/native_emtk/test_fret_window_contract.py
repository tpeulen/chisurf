"""The FRET window (docking + pair selection) reads its own metadata and preserves child state."""

from emtk.testing import Driver

from chisurf.plugins.modelling.fret.gui import app as owner


def test_primary_dimensions_reach_the_window():
    """The window takes its declared size rather than a host fallback."""
    app = owner.make_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_authored_dimensions_are_used(monkeypatch):
    """An authored declaration reaches the shared reader in the real constructor."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Keep the real validation while exercising another valid declaration."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.make_app()
    try:
        assert app.window_size == (960, 680)
        assert received == [{"width": 1100, "height": 720}]
    finally:
        app.close()


def test_resize_preserves_the_actual_child_and_its_settings():
    """Resizing keeps the same loaded tool and the list, Guide and Help controls."""
    app = owner.make_app()
    try:
        child = app.select("Docking & Screening")
        child.session.n_frames = 77
        settings = app.export_settings()
        for size in [(1100, 720), (736, 552)]:
            Driver(app, size).draw(3)
            assert app.child is child
            assert app.export_settings() == settings
            assert {"nav_Docking & Screening", "nav_Pair Selection", "guide", "help"} <= (
                app.item_rects.keys()
            )
    finally:
        app.close()


def test_saved_host_geometry_wins(tmp_path, monkeypatch):
    """The native preference seam restores geometry and the selected tool."""
    from chisurf.emtk.state import attach_native_state

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    first = attach_native_state("fret_window_contract", owner.make_app())
    first.select("Pair Selection")
    first.window_resized(1330, 870)
    first.close()
    reopened = attach_native_state("fret_window_contract", owner.make_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.selected == "Pair Selection"
    finally:
        reopened.close()
