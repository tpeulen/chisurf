"""Photon Table on a real Becker & Hickl image scan; writes ``figures/108_photon_table.png`` (guide 108).

The page sits at a frame boundary, where pixel-clock, line-start and frame
markers interleave with the photons, so every marker kind's colour is in view.
"""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver  # noqa: E402

from screenshots.emtk_shot import FIG, app_from  # noqa: E402

FILE = "~/dev/tttr-data/imaging/bh/spcm/FocalCheck_A1_20x_8xzoom_750nm_m1.spc"
#: The record 21 rows before the second frame marker.
FIRST = 456_375


def main():
    """Open the scan, page to the frame boundary, settle and grab."""
    app = app_from("photon_table")
    driver = Driver(app, (1300, 760))
    driver.frame(2)
    model = app.model
    assert model.load_path(str(pathlib.Path(FILE).expanduser())), model.notice
    model.set_rows(30)
    model.set_first(FIRST)
    driver.frame(4)
    driver.hover((12.0, float(driver.size[1]) - 12.0))
    driver.frame(2)
    driver.screenshot(FIG / "108_photon_table.png")


if __name__ == "__main__":
    main()
