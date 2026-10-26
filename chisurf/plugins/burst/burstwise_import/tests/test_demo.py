"""The Burstwise importer's example: a legacy folder written on demand, scanned and converted."""

from pathlib import Path

from chisurf.plugins.burst.burstwise_import.demo import SIDECAR_NAME, make_demo
from chisurf.plugins.burst.burstwise_import.gui.app import create_app
from chisurf.plugins.burst.burstwise_import.sample import FOLDER, write_sample

FIXTURE = Path(__file__).resolve().parent / "data" / "burstwise" / FOLDER


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_make_demo_writes_the_legacy_folder_with_its_sidecar(tmp_path):
    """The example is generated into the given folder, beside a sidecar; a second call reuses it."""
    folder = make_demo(tmp_path)
    assert folder == tmp_path / FOLDER
    assert list(folder.glob("bi4_bur/*.bur"))
    assert list(folder.glob("*.mti"))
    assert (tmp_path / SIDECAR_NAME).is_file()
    stamp = (folder / "Info" / "Paris_info.txt").stat().st_mtime_ns
    assert make_demo(tmp_path) == folder
    assert (folder / "Info" / "Paris_info.txt").stat().st_mtime_ns == stamp


def test_the_shipped_writer_reproduces_the_committed_test_fixture(tmp_path):
    """The test fixture and the example are the same bytes: one writer, no drift."""
    assert _files(write_sample(tmp_path)) == _files(FIXTURE)


def test_load_example_scans_the_folder_and_converts():
    """The affordance inventories the folder; a conversion writes the container."""
    app = create_app()
    model = app.model
    model.load_example()
    inventory = model.inventory
    assert inventory
    report = model.convert()
    assert report is not None
