"""Photon Table on a real PicoQuant HT3 file; writes ``figures/108_photon_table.png`` (guide 108)."""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver  # noqa: E402

from screenshots.emtk_shot import FIG, app_from  # noqa: E402

FILE = "~/dev/tttr-data/pq/ht3/pq_ht3v1.0_hh_t3.ht3"


def main():
    """Open the file, filter to one channel, settle and grab."""
    app = app_from("photon_table")
    driver = Driver(app, (1300, 760))
    driver.frame(2)
    model = app.model
    assert model.load_path(str(pathlib.Path(FILE).expanduser())), model.notice
    model.set_first(1000)
    model.set_rows(25)
    driver.frame(4)
    driver.hover((12.0, float(driver.size[1]) - 12.0))
    driver.frame(2)
    driver.screenshot(FIG / "108_photon_table.png")


if __name__ == "__main__":
    main()
