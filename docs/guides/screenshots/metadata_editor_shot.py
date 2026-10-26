"""Guide 113: the Metadata Editor on its own (headless emtk).

``main`` writes two figures into ``docs/guides/figures``:

* ``113_metadata_editor_flrcif.png`` -- the *flrCIF* schema over an opened ``metadata.json``:
  typed fields filled, two free-form extras in the entries table, and one value that fails its
  check (*Ionic strength* typed with its unit), so the message shows and **Apply** is grey;
* ``113_metadata_editor_zenodo.png`` -- the *Zenodo* schema on a fresh record: the required
  *Title* / *Creators* marked ``*`` and reported until they are filled.

Read every PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/metadata_editor_shot.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402

#: An analysis-metadata file as burst selection's flrCIF export would carry it.
FLRCIF_RECORD = {
    "pH": "7.5",
    "temperature": "295.15",
    "ionic_strength": "150 mM",
    "buffer_composition": "50 mM HEPES, 150 mM NaCl, 1 mM TCEP",
    "solvent_phase": "aqueous",
    "labeling_efficiency": "0.92",
    "donor_only_fraction": "0.18",
    "operator": "TP",
    "sample_id": "T4L-S44pAcF-I150C",
}


def flrcif_file(folder: pathlib.Path) -> None:
    """flrCIF schema, a JSON file opened, one value that does not parse."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.metadata_editor.gui.app import make_app

    path = folder / "metadata.json"
    path.write_text(json.dumps(FLRCIF_RECORD, indent=2) + "\n", encoding="utf-8")
    app = make_app()
    app.pick_schema("flrCIF")
    app.path = path
    app.editor.open(app._schema(), app._read(path))
    driver = RealisticDriver(app, (900, 480), real_painter=True)
    driver.frame(4)
    driver.screenshot(FIG / "113_metadata_editor_flrcif.png")
    print("wrote 113_metadata_editor_flrcif.png", flush=True)
    getattr(app, "close", lambda: None)()


def zenodo_fresh() -> None:
    """Zenodo schema on an empty record: the required fields are reported."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.metadata_editor.gui.app import make_app

    app = make_app()
    app.pick_schema("Zenodo")
    values = app.editor.editor.values
    values["upload_type"] = "dataset"
    values["publication_date"] = "2026-10-26"
    values["license"] = "CC-BY-4.0"
    values["access_right"] = "open"
    driver = RealisticDriver(app, (900, 625), real_painter=True)
    driver.frame(4)
    driver.screenshot(FIG / "113_metadata_editor_zenodo.png")
    print("wrote 113_metadata_editor_zenodo.png", flush=True)
    getattr(app, "close", lambda: None)()


def main() -> None:
    """Draw the two figures."""
    with tempfile.TemporaryDirectory() as folder:
        flrcif_file(pathlib.Path(folder))
    zenodo_fresh()


if __name__ == "__main__":
    main()
