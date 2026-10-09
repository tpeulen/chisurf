"""H2MM host metadata preserves settings, routing and native geometry."""

from dataclasses import asdict

from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.burst_h2mm.gui import native as owner
from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel


def test_primary_dimensions_reach_constructor():
    """The raw H2MM primary owns the initial tool-family dimensions."""
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_authored_dimensions_are_read(monkeypatch):
    """A different valid declaration reaches the common production reader."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Use real validation before the loaded sections are adapted."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.create_app()
    try:
        assert app.window_size == (960, 680)
        assert received == [{"width": 1100, "height": 720}]
    finally:
        app.close()


def test_default_and_narrow_preserve_settings_and_routing():
    """Rendering retains the configured model and actual detector editor inputs."""
    model = H2mmViewModel()
    model.min_states = model.max_states = 2
    model.restarts = 1
    model.max_iter = 40
    settings = model.settings_dict()
    routing = asdict(model.build_settings())
    app = owner.H2mmNativeApp(model)
    try:
        for size in [(1100, 720), (736, 552)]:
            Driver(app, size).draw(3)
            assert model.settings_dict() == settings
            assert asdict(model.build_settings()) == routing
            assert model.result is None
    finally:
        app.close()


def test_saved_native_geometry_wins(tmp_path, monkeypatch):
    """The existing native seam restores host size without inventing result state."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("h2mm_window_contract", owner.create_app())
    first.window_resized(1330, 870)
    first.close()
    reopened = attach_native_state("h2mm_window_contract", owner.create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.model.result is None
    finally:
        reopened.close()


def test_narrow_output_labels_fit_the_control_dock():
    """The output checkboxes expose complete labels within the narrow dock."""
    app = owner.create_app()
    try:
        driver = Driver(app, (736, 552))
        driver.draw(3)
        driver.wheel(-20, at=(280, 480))
        painter = driver.draw(3)
        box = app.docks.windows["controls"].content
        assert box is not None
        for label in ["State photons as PTU", "State photons sidecar"]:
            rows = [row for row in painter.texts if row[5] == label]
            assert rows, label
            assert any(row[0] + row[2] <= box[0] + box[2] for row in rows), label
    finally:
        app.close()


def test_typed_folder_dialog_keeps_the_selected_directory(tmp_path):
    """The real file chooser retains the folder and default filter after type repair."""
    model = H2mmViewModel()
    model.data_folder = str(tmp_path)
    app = owner.H2mmNativeApp(model)
    try:
        app.browse("folder")
        assert app.dialog.directory == str(tmp_path)
        assert app.dialog.filters == [("All files", ["*"])]
        assert app._dialog_window.open
    finally:
        app.close()
