"""A populated, hermetic world for the Settings hub: temp settings, temp MMFDB with users, temp HOME.

Used by the parity tests and the evidence scripts. Nothing here touches the user's ``~/.chisurf``, the keyring
or the network (the updater's fakes stand in for every system action).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from chisurf.plugins.core.user_editor.test import seeded_db

SETUP = {
    "windows": {"prompt": [0, 64]},
    "detectors": {
        "green": {"chs": [0], "micro_time_ranges": [[0, 32]]},
        "red": {"chs": [1], "micro_time_ranges": [[0, 32]]},
    },
}


SETTINGS_YAML = """gui:
  language: en
  theme: dark
  plot:
    font_size: 12
    show_grid: true
    line_width: 1.5
  working_path: ""
acquisition:
  chunk_size: 8192
  device_type: Simulation
"""


def prepare(root, monkeypatch=None):
    """Point settings, MMFDB and HOME into *root*; seed users, detector setups, FCS pairs; install fakes."""
    root = Path(root)
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    folder = seeded_db.use_folder(root / "settings", monkeypatch)
    if monkeypatch is not None:
        monkeypatch.setenv("HOME", str(home))
    else:
        os.environ["HOME"] = str(home)
    # A provider key exported in the developer's shell would be read by the AI Settings panel: never show or use it.
    for name in list(os.environ):
        if name.endswith(("_API_KEY", "_KEY", "_TOKEN", "_API_TOKEN")):
            if monkeypatch is not None:
                monkeypatch.delenv(name)
            else:
                del os.environ[name]
    (folder / "detector_setups.json").write_text(
        json.dumps({"setups": {"Bench A": SETUP, "Bench B": SETUP}}), encoding="utf-8"
    )
    (folder / "settings_chisurf.yaml").write_text(SETTINGS_YAML, encoding="utf-8")
    client = seeded_db.admin_client()
    seeded_db.seed(client)
    if monkeypatch is not None:
        from chisurf.plugins.core.updater.test.fakes import Fakes
        from chisurf.plugins.core.user_editor.gui import model as user_model
        from chisurf.plugins.core.user_editor.gui import view_model as user_view_model

        Fakes().install(monkeypatch)
        # The user editor talks to the in-process MMFDB over the temporary database, as its own tests do.
        for module in (user_model, user_view_model):
            monkeypatch.setattr(module, "active_user_id", lambda: "admin")
        monkeypatch.setattr(user_view_model, "make_mmfdb_client", lambda: client)
        monkeypatch.setattr(user_model, "make_mmfdb_client", lambda: client, raising=False)
        # Settings are read once at import; show the seeded acquisition section.
        from chisurf.settings import gui as gui_settings

        gui_settings["acquisition"] = {
            "chunk_size": 8192,
            "device_type": "Simulation",
            "output_path": str(root / "acq"),
        }
    return folder
