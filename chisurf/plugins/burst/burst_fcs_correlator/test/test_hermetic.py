"""The settings the burst-FCS app writes go to the temporary folder, never to the account's ~/.chisurf."""

import os
import pwd
from pathlib import Path


def test_the_native_settings_path_is_the_temporary_folder(tmp_path):
    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    app.close()

    real = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
    before = sorted(p.stat().st_mtime_ns for p in real.rglob("burst_fcs*")) if real.exists() else []
    from chisurf.core.settings import get_path

    path = get_path("settings")
    assert str(tmp_path) in str(path) and real not in path.parents
    after = sorted(p.stat().st_mtime_ns for p in real.rglob("burst_fcs*")) if real.exists() else []
    assert before == after
