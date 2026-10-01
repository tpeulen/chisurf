"""A saved setup can be written for a user the database has never seen.

``created_by_user_id`` is a foreign key to the users table. On a fresh database (a new
installation, or a configured ``default_user_id`` that was never seeded) the first setup save --
and with it the one-time migration of a legacy ``detector_setups.json`` -- failed with
``FOREIGN KEY constraint failed`` and rolled back, so a user with an existing JSON file and no
database could not open any tool that reads detector setups.
"""

from __future__ import annotations

import json

import pytest

mmfdb = pytest.importorskip("mmfdb.repository")

from chisurf.core.fio import setup_store  # noqa: E402
from chisurf.core.setup_channel_definition import CONFIG  # noqa: E402

SETUP = {
    "setup_name": "ALEX Suite (auto)",
    "windows": {"prompt": [0, 100]},
    "detectors": {"green": {"chs": [1], "micro_time_ranges": [[0, 100]]}},
    "tttr_reading": {"file_type": "Auto"},
}


def _fresh_db(tmp_path):
    return mmfdb.MFDatabase(str(tmp_path / "fresh.db"))


def test_migrating_a_legacy_json_into_a_fresh_database_works(tmp_path):
    legacy = tmp_path / "detector_setups.json"
    legacy.write_text(json.dumps({"setups": {"ALEX Suite (auto)": SETUP}, "last_used": "ALEX Suite (auto)"}))
    db = _fresh_db(tmp_path)

    assert setup_store.migrate_json_to_mmfdb(db, CONFIG, legacy, user_id="a_user_nobody_seeded") is True

    owned = [s for s in db.list_setups() if s.get("created_by_user_id") == "a_user_nobody_seeded"]
    assert len(owned) == 1


def test_saving_one_setup_for_an_unknown_user_creates_that_user(tmp_path):
    db = _fresh_db(tmp_path)
    setup_store.save_setup_row(db, CONFIG, "Mine", SETUP, user_id="brand_new_user")
    assert any(u["user_id"] == "brand_new_user" for u in db.get_users())


def test_the_first_save_for_a_new_user_survives_closing_the_database(tmp_path):
    path = str(tmp_path / "reopen.db")
    db = mmfdb.MFDatabase(path)
    setup_store.save_setup_row(db, CONFIG, "Mine", {"windows": {}}, user_id="new_user")
    assert len(db.list_setups()) == 1
    db.close()

    assert len(mmfdb.MFDatabase(path).list_setups()) == 1
