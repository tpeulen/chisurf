"""Burst Selection opens on a fresh profile that still carries a legacy ``detector_setups.json``.

A new installation has an empty MMFDB with no row for the active user. Opening the tool imports the legacy JSON
setups into MMFDB, and that first write used to fail with ``FOREIGN KEY constraint failed`` (the setup row
references a user that did not exist), so the tool did not open. The store now creates the user row first
(``chisurf.core.fio.setup_store.save_setup_row``); this test drives the whole tool in a clean process, because
``DETECTOR_SETUPS_FILE`` and the database path are resolved from the settings directory at import time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]

SCRIPT = r"""
import json, logging, sys
records = []
class Grab(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())
logging.getLogger().addHandler(Grab(level=logging.WARNING))
from chisurf.core.data_io import detector_setups as ds
ds.DETECTOR_SETUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
ds.DETECTOR_SETUPS_FILE.write_text(json.dumps(
    {"setups": {"legacy setup": {"tttr_reading": {"file_type": "SPC-130"}}}, "last_used": "legacy setup"}))
from chisurf.emtk.plugins import load_plugin
app = load_plugin("burst_selection", persist=False)
names = list(ds.load_detector_setups()["setups"])
print(json.dumps({"setups": names, "json_left": ds.DETECTOR_SETUPS_FILE.exists(),
                  "foreign_key": [r for r in records if "FOREIGN KEY" in r]}))
"""


def test_burst_selection_opens_on_a_fresh_profile_with_legacy_setups(tmp_path):
    settings = tmp_path / "settings"
    settings.mkdir()
    env = dict(
        os.environ,
        CHISURF_SETTINGS_DIR=str(settings),
        QT_QPA_PLATFORM="offscreen",
        IMP_BFF_GPU="off",
        PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]),
    )
    for key in ("MMFDB_DATABASE_PATH", "MMFDB_SETTINGS_DIR"):
        env.pop(key, None)
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=REPO, env=env, capture_output=True, text=True, timeout=600
    )
    assert done.returncode == 0, done.stderr[-3000:]
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["foreign_key"] == []
    assert "legacy setup" in result["setups"]
    # Imported into MMFDB, so the legacy file is gone.
    assert result["json_left"] is False
