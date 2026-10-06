"""Run the Qt tool and the emtk toolbar through the same setup workflow, MMFDB mode, in one process.

Run as ``python reference.py <tmp_dir>`` with ``QT_QPA_PLATFORM=offscreen``; the environment is
pointed at the temporary folder *before* anything of ChiSurf is imported, so neither the user's
settings, their MMFDB nor their keyring is touched. Prints one JSON document with, for each of
the two implementations, the stored setups after every step. The test compares the two halves.
"""

import json
import os
import sys
from pathlib import Path

tmp = Path(sys.argv[1])
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "settings")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mmfdb")
(tmp / "settings").mkdir(parents=True, exist_ok=True)
(tmp / "mmfdb").mkdir(parents=True, exist_ok=True)
QT_DB, EMTK_DB = str(tmp / "qt.sqlite"), str(tmp / "emtk.sqlite")

from chisurf.plugins.core.setup_channel_definition.test.driver import (  # noqa: E402
    CAL,
    DATA,
    STAMP,
    norm,
)


def rows(db_path):
    """Names and the stored public flag of the setups of the detector-setup type."""
    from mmfdb.repository import MFDatabase

    db = MFDatabase(db_path)
    try:
        out = {}
        for row in db.list_setups():
            cfg = json.loads(row.get("configuration_json") or "{}")
            if cfg.get("setup_type") == "tttr_detector_setup":
                out[row["name"]] = {
                    "public": bool(row.get("is_public")),
                    "owner": row.get("created_by_user_id"),
                }
        return out
    finally:
        db.close()


def seed_user(db_path):
    """A fresh MMFDB has no row for the active user and the first save would be lost."""
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio import setup_store

    db = MFDatabase(db_path)
    db.ensure_user(setup_store.resolve_active_user_id())
    db.conn.commit()
    db.close()


def add_calibration(db_path, name):
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio import setup_store

    user = setup_store.resolve_active_user_id()
    db = MFDatabase(db_path)
    key = setup_store.setup_id_for_name(name, user, "tttr_detector_setup")
    for channel, (g, l1, l2) in CAL.items():
        db.add_setup_calibration(
            key,
            channel,
            g_factor=g,
            l1=l1,
            l2=l2,
            calibrated_at=STAMP,
            method="manual",
            created_by_user_id=user,
        )
    db.conn.commit()
    db.close()


def run_qt():
    os.environ["MMFDB_DATABASE_PATH"] = QT_DB
    seed_user(QT_DB)
    from qtpy import QtWidgets

    run_qt.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.gui import dialogs
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod
    from chisurf.plugins.core.setup_channel_definition.gui.tool import SetupChannelDefinitionWidget

    for kind in ("information", "warning", "error"):
        setattr(dialogs, kind, lambda *a, **k: None)
    dialogs.question = lambda *a, **k: mod.QMessageBox.Yes
    widget = SetupChannelDefinitionWidget()
    page = widget.page
    page._load_data(DATA)
    log = {}
    asked = {"name": "Lab A"}
    mod.QInputDialog.getText = staticmethod(lambda *a, **k: (asked["name"], True))

    def snap(step):
        from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
            load_detector_setups,
        )

        setups = load_detector_setups()["setups"]
        log[step] = {
            "names": sorted(setups),
            "rows": rows(QT_DB),
            "setups": {n: norm(s) for n, s in setups.items()},
        }

    page._on_save_setup()
    snap("saved")
    log["public_enabled_after_save"] = page.public_checkbox.isEnabled()
    page.public_checkbox.setChecked(True)
    page._on_save_setup()
    snap("saved_public")
    add_calibration(QT_DB, "Lab A")
    page._populate_calibration_combo("Lab A")
    log["calibration_items"] = [
        page.calibration_combo.itemText(i) for i in range(page.calibration_combo.count())
    ]
    page.calibration_combo.addItem(
        STAMP
    )  # the Qt combo lists nothing (see test), so add it by hand
    page.calibration_combo.setCurrentText(STAMP)
    cells = {}
    for r in range(page.detectors_form.rowCount()):
        name = page.detectors_form.item(r, 0).text()
        cells[name] = [float(page.detectors_form.cellWidget(r, c).text()) for c in (3, 4, 5)]
    log["calibration_cells"] = cells
    asked["name"] = "Lab B"
    page._on_rename_setup()
    snap("renamed")
    page._on_delete_setup()
    snap("deleted")
    return log


def run_emtk():
    from mmfdb.repository import MFDatabase

    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget
    from chisurf.plugins.core.setup_channel_definition.gui.model import SetupToolbar

    seed_user(EMTK_DB)
    db = MFDatabase(EMTK_DB)
    page = ChannelDefinitionWidget(model=ChannelDefinition(DATA, db=db))
    bar = SetupToolbar(page)
    bar.reload()
    log = {}

    def snap(step):
        definition = bar.definition
        definition.refresh_setups()
        log[step] = {
            "names": sorted(definition.setups),
            "rows": rows(EMTK_DB),
            "setups": {n: norm(s) for n, s in definition.setups.items()},
        }

    bar.request_save()
    bar.name_text = "Lab A"
    bar.confirm()
    snap("saved")
    log["public_enabled_after_save"] = bar.can_public()
    bar.select_public(True)
    bar.request_save()
    bar.confirm()
    snap("saved_public")
    add_calibration(EMTK_DB, "Lab A")
    bar.select("Lab A")
    log["calibration_items"] = bar.calibration_items()
    bar.select_calibration(STAMP)
    log["calibration_cells"] = {
        n: [d["g_factor"], d["l1"], d["l2"]]
        for n, d in sorted(bar.definition.data["detectors"].items())
    }
    bar.request_rename()
    bar.name_text = "Lab B"
    bar.confirm()
    snap("renamed")
    bar.request_delete()
    bar.confirm()
    snap("deleted")
    db.close()
    return log


if __name__ == "__main__":
    print("RESULT " + json.dumps({"qt": run_qt(), "emtk": run_emtk()}))
