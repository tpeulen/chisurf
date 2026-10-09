"""The ebFRET host reads the raw main spec and preserves native geometry."""

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.burst_ebfret.api.client import EbfretClient
from chisurf.plugins.burst.burst_ebfret.gui import app as owner


@pytest.fixture
def app():
    """Use the production in-process backend with an isolated empty session."""
    client = EbfretClient(seed=5)
    window = owner.App(owner.EbfretGui(client), on_exit=client.close)
    yield window
    client.close()


def test_primary_dimensions_reach_constructor(app):
    """The actual host adapter consumes native main-spec dimensions."""
    assert app.window_size == (1100, 720)


def test_authored_dimensions_are_read(monkeypatch):
    """The common reader receives metadata from the already loaded raw primary."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Exercise valid alternate host dimensions without adapting panel data."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    client = EbfretClient(seed=5)
    try:
        window = owner.App(owner.EbfretGui(client), on_exit=client.close)
        assert window.window_size == (960, 680)
        assert received == [{"width": 1100, "height": 720}]
    finally:
        client.close()


def test_both_layouts_preserve_backend_controls(app):
    """The host dimensions do not mutate backend settings or create data."""
    before = app.gui.client.status()["controls"]
    for size in [(1100, 720), (736, 552)]:
        Driver(app, size).draw(3)
        assert app.gui.client.status()["controls"] == before
        assert app.gui.client.view()["n_series"] == 0


def test_saved_geometry_wins(app, tmp_path, monkeypatch):
    """Native host preferences override the declaration on reopening."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("ebfret_window_contract", app)
    first.window_resized(1330, 870)
    first.close()
    client = EbfretClient(seed=5)
    reopened = attach_native_state(
        "ebfret_window_contract", owner.App(owner.EbfretGui(client), on_exit=client.close)
    )
    try:
        assert reopened.window_size == (1330, 870)
    finally:
        reopened.close()
        client.close()


def test_export_traces_opens_the_existing_channels_form(app, tmp_path):
    """Choosing an export path reaches the real current spec-dialog factory."""
    from chisurf.plugins.burst.burst_ebfret.gui.dialogs import SpecDialog

    app.gui.export_traces()
    chooser = app.gui.dialogs[-1]
    chooser.on_ok([str(tmp_path / "traces.dat")], 1)
    channels = app.gui.dialogs[-1]
    assert isinstance(channels, SpecDialog)
    assert channels.title == "Channels"
