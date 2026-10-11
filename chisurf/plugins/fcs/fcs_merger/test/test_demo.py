"""The demo folder the merger tour loads holds curves on one shared lag grid."""

from chisurf.plugins.fcs.fcs_merger.demo import make_demo
from chisurf.plugins.fcs.fcs_merger.gui.model import read_folder


def test_demo_folder_reads_back_as_equal_grid_curves(tmp_path):
    folder = make_demo(tmp_path)
    curves, paths, skipped = read_folder(folder)
    assert len(curves) == len(paths) == 4 and not skipped


def test_the_cache_is_reused_until_overwritten(tmp_path):
    folder = make_demo(tmp_path)
    first = {p.name: p.stat().st_mtime_ns for p in folder.glob("*.json.gz")}
    assert make_demo(tmp_path) == folder
    assert {p.name: p.stat().st_mtime_ns for p in folder.glob("*.json.gz")} == first
    (folder / "demo_00.json.gz").write_bytes(b"damaged")
    make_demo(tmp_path)
    assert len(read_folder(folder)[0]) == 4
