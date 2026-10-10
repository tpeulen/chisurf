"""The demo folder the merger tour loads holds curves on one shared lag grid."""

from chisurf.plugins.fcs.fcs_merger.demo import make_demo
from chisurf.plugins.fcs.fcs_merger.gui.model import read_folder


def test_demo_folder_reads_back_as_equal_grid_curves(tmp_path):
    folder = make_demo(tmp_path)
    curves, paths, skipped = read_folder(folder)
    assert len(curves) == len(paths) == 4 and not skipped
