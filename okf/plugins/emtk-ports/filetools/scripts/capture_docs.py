"""Guide figures from the emtk hub (guide 74): Split / Convert with an SPC file loaded, Time Windows with the file added.
Usage: <out_dir> (writes docs_file_tools_split.png, docs_file_tools.png)."""
import pathlib, sys, tempfile, shutil
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.tttr.filetools.gui.app import FileToolsApp


def main():
    out = pathlib.Path(sys.argv[1]).resolve()
    repo = pathlib.Path(__file__).resolve().parents[5]
    work = pathlib.Path(tempfile.mkdtemp())
    spc = work / "BH_SPC132.spc"; shutil.copy2(repo / "test/data/tttr/BH/132/BH_SPC132.spc", spc)
    app = FileToolsApp(); size = (1200, 800)
    def draw(n=4):
        for _ in range(n): app.draw(RecordingPainter(), 0, 0, *size)
    app.select("split_convert"); draw()
    app.child.tool.load_input(str(spc)); draw(); emtk_screenshot(app, out / "docs_file_tools_split.png", size)
    app.select("tttr_time_windows"); draw()
    ptu = work / "PQ_Olympus_MFIS.ht3"; shutil.copy2(repo / "test/data/clsm/PQ_Olympus_MFIS.ht3", ptu)
    app.child.tool.add_paths([str(ptu)]); draw(8)
    import time; time.sleep(2); draw(4); emtk_screenshot(app, out / "docs_file_tools.png", size)
    app.close()


if __name__ == "__main__":
    main()
