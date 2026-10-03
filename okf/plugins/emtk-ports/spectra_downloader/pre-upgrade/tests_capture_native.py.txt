"""Reproduce populated native GPU renders without Qt."""

import tempfile
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from chisurf.plugins.spectra_downloader.gui.app import create_app
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase


def populated_db(path):
    db = FluorophoreDatabase(path)
    db.connect()
    x = np.arange(400.0, 701.0, 5.0)
    for name, source, kind, center in (
        ("EGFP", "fpbase", "fluorescent_protein", 509),
        ("Alexa Fluor 488", "atto", "organic_dye", 519),
        ("ET525/50m", "chroma", "bandpass", 525),
        ("DMLP550", "thorlabs", "dichroic", 550),
        ("SPAD 650", "thorlabs", "apd", 650),
    ):
        db.register_component(
            name=name,
            source=source,
            kind=kind,
            properties={"em_max": center, "description": "Reference fixture"},
            spectra={"emission": (x, np.exp(-0.5 * ((x - center) / 22.0) ** 2))},
        )
    return db


def main():
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        db = populated_db(Path(temp) / "spectra.db")
        for width, height, name in ((1000, 700, "normal"), (640, 700, "narrow")):
            for panel in ("Overview", "Browse", "Download", "Add to MMFDB"):
                app = create_app(db)
                app.panel = panel
                app.model.endpoint.db_path = str(Path(temp) / "live-MMFDB.db")
                app.check_session()
                app.model.select(app.model.rows[0]["probe_id"])
                host = NativeHost(app, size=(width, height), backend="offscreen")
                for _ in range(2):
                    pixels = host.draw_frame()
                Image.fromarray(np.asarray(pixels)).save(
                    out / f"native-{name}-{panel.lower().replace(' ', '-')}.png"
                )
                if name == "narrow" and panel == "Browse":
                    app.wheel(width - 40, height - 80, -12)
                    pixels = host.draw_frame()
                    Image.fromarray(np.asarray(pixels)).save(
                        out / "native-narrow-browse-scrolled.png"
                    )
                host.close()
        db.close()


if __name__ == "__main__":
    main()
