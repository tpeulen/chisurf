"""Native histogram launch keeps the real legacy BID-folder command-line contract."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def native_launch(monkeypatch):
    """Observe startup and host lifecycle without opening a GPU or Qt application."""
    from emtk import native

    from chisurf.plugins.tttr.microtime_histogram.gui import app

    calls = []
    surface = SimpleNamespace(
        load_bid_folder=lambda folder, setup_name=None, auto_transfer=False: (
            calls.append(("bid", str(folder), setup_name, auto_transfer)) or True
        ),
    )
    monkeypatch.setattr(app, "create_app", lambda: surface)

    class Host:
        """Keep the existing public host seam explicit and record its lifecycle."""

        def __init__(self, actual, **kwargs):
            """Ensure the launched object is the original factory's native surface."""
            assert actual is surface
            calls.append(("host",))

        def run(self):
            """Record a real event-loop launch request without using hardware."""
            calls.append(("run",))

        def close(self):
            """Record cleanup after the native event loop returns."""
            calls.append(("close",))

    monkeypatch.setattr(native, "NativeHost", Host)
    return calls


def test_plain_launcher_uses_the_native_surface_and_closes(native_launch):
    """The GUI entry point uses the existing native surface without a legacy widget."""
    from chisurf.plugins.tttr.microtime_histogram.__main__ import main

    assert main([]) == 0
    assert native_launch == [("host",), ("run",), ("close",)]


def test_bid_arguments_reach_the_existing_native_loader(tmp_path, native_launch):
    """Named setup and automatic transfer remain explicit operational inputs."""
    from chisurf.plugins.tttr.microtime_histogram.__main__ import main

    assert main(["--bid-folder", str(tmp_path), "--setup-name", "measured", "--auto-transfer"]) == 0
    assert native_launch == [
        ("bid", str(tmp_path), "measured", True),
        ("host",),
        ("run",),
        ("close",),
    ]


def test_bid_setup_is_inferred_from_measurement_info(tmp_path, native_launch):
    """The existing parent-Info lookup still selects the measurement's stored setup."""
    from chisurf.plugins.tttr.microtime_histogram.__main__ import main

    folder = tmp_path / "BID"
    folder.mkdir()
    info = tmp_path / "Info"
    info.mkdir()
    (info / "photon_selection_parameters.json").write_text(
        json.dumps({"selected_setup": "measured"})
    )
    assert main(["--bid-folder", str(folder)]) == 0
    assert native_launch[0] == ("bid", str(folder), "measured", False)


def test_missing_bid_folder_does_not_open_a_window(tmp_path, native_launch):
    """A bad batch path remains an error and never starts a GUI or worker."""
    from chisurf.plugins.tttr.microtime_histogram.__main__ import main

    assert main(["--bid-folder", str(tmp_path / "missing")]) == 1
    assert native_launch == []


def test_setup_info_grandparent_fallback_requires_missing_parent_info(tmp_path, native_launch):
    """Keep the established metadata search order without silently changing precedence."""
    from chisurf.plugins.tttr.microtime_histogram.__main__ import main

    folder = tmp_path / "measurement" / "bi4_bur"
    folder.mkdir(parents=True)
    info = tmp_path / "Info"
    info.mkdir()
    (info / "photon_selection_parameters.json").write_text(
        json.dumps({"selected_setup": "grandparent"})
    )
    assert main(["--bid-folder", str(folder)]) == 0
    assert native_launch[0] == ("bid", str(folder), "grandparent", False)
    native_launch.clear()
    (folder.parent / "Info").mkdir()
    assert main(["--bid-folder", str(folder)]) == 0
    assert native_launch[0] == ("bid", str(folder), None, False)


def test_manifest_and_public_package_retire_the_legacy_wizard():
    """Discovery declares the native factory and cannot leave a live legacy UI route."""
    import chisurf.plugins.tttr.microtime_histogram as plugin

    folder = Path(plugin.__file__).parent
    entrypoints = json.loads((folder / "manifest.json").read_text())["entrypoints"]
    assert "gui" not in entrypoints
    assert entrypoints["emtk"] == "chisurf.plugins.tttr.microtime_histogram.gui.app:create_app"
    assert not (folder / "wizard.py").exists()
    assert not (folder / "wizard.ui").exists()
    assert not hasattr(plugin, "MicrotimeHistogram")
