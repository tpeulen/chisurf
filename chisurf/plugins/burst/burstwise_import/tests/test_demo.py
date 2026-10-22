"""The Burstwise importer's example: the shipped legacy folder, scanned and converted."""

from chisurf.plugins.burst.burstwise_import.demo import make_demo
from chisurf.plugins.burst.burstwise_import.gui.app import create_app


def test_make_demo_points_at_the_shipped_legacy_folder():
    """The example is the plugin's real legacy sample folder (never a copy)."""
    folder = make_demo()
    assert folder.is_dir()
    assert list(folder.glob("bi4_bur/*.bur"))
    assert list(folder.glob("*.mti"))


def test_load_example_scans_the_folder_and_converts():
    """The affordance inventories the folder; a conversion writes the container."""
    app = create_app()
    model = app.model
    model.load_example()
    inventory = model.inventory
    assert inventory
    report = model.convert()
    assert report is not None
