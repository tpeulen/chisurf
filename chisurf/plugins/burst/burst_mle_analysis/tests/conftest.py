"""Hermetic settings for every test of this plugin, and a guard on the user's real ``~/.chisurf``.

* ``CHISURF_SETTINGS_DIR``, ``MMFDB_SETTINGS_DIR``, ``MMFDB_DATABASE_PATH`` and ``HOME`` point into the test's temp
  folder, so no test reads or writes the user's settings, keyring or database.
* A module-scoped guard lists the real ``~/.chisurf`` (the home found in the password database, not ``$HOME``)
  before the first test of a module and after the last one: any file added, removed or changed fails the module.
  ``~/.chisurf/logs`` and ``~/.chisurf/cache`` (bytecode) are ignored.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest

REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def _listing() -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    if not REAL_CHISURF.is_dir():
        return found
    for path in REAL_CHISURF.rglob("*"):
        rel = path.relative_to(REAL_CHISURF)
        # logs: every ChiSurf process appends there; cache: the interpreter's bytecode cache is redirected there
        if (rel.parts and rel.parts[0] in ("logs", "cache")) or "__pycache__" in rel.parts:
            continue
        try:
            if not path.is_file():  # a directory's mtime moves when a lock file comes and goes
                continue
            stat = path.stat()
        except OSError:
            continue
        found[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return found


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _listing()
    yield
    after = _listing()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert not changed, f"the tests touched the real ~/.chisurf: {changed[:10]}"


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    yield


# --------------------------------------------------------------------------------------------------------------------
# The in-repository real data (BH SPC-132 smFRET DNA, burst_selection/tests/data) as a ready-to-use wizard.
# Real photons and a real fit: no invented or externally downloaded fixture. The wizard writes beside the burst
# files, so everything runs on a temporary copy.
# --------------------------------------------------------------------------------------------------------------------
REPO_DATA = (
    Path(__file__).resolve().parents[2] / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
)
BURST_TABLE = Path("burstwise_All 0.1000#15") / "bi4_bur" / "m000.bur"
#: BH SPC-132 dual-colour polarisation routing: green 0/1, red 8/9 (the detector page's definition).
CHANNEL_SETTINGS = {
    "detectors": {
        "green": {
            "chs": [0, 1],
            "micro_time_ranges": [],
            "g_factor": 1.0,
            "l1": 0.0308,
            "l2": 0.0368,
        },
        "red": {
            "chs": [8, 9],
            "micro_time_ranges": [],
            "g_factor": 1.0,
            "l1": 0.0308,
            "l2": 0.0368,
        },
    },
    "windows": {},
    "file_type": "SPC-130",
}


@pytest.fixture(scope="module")
def hermetic_env(tmp_path_factory):
    """Settings, MMFDB and HOME in a temp folder for the whole module.

    Module-scoped fixtures (a wizard that is closed after the last test) outlive the per-test environment above, and
    a wizard saves its dock layout when it closes: without this they wrote into the real ``~/.chisurf``. Every
    module fixture below depends on this one, so it is still set when they are torn down.
    """
    root = tmp_path_factory.mktemp("module_env")
    patch = pytest.MonkeyPatch()
    for name in ("home", "settings", "mmfdb"):
        (root / name).mkdir()
    patch.setenv("HOME", str(root / "home"))
    patch.setenv("CHISURF_SETTINGS_DIR", str(root / "settings"))
    patch.setenv("MMFDB_SETTINGS_DIR", str(root / "mmfdb"))
    patch.setenv("MMFDB_DATABASE_PATH", str(root / "mmfdb.sqlite"))
    yield root
    patch.undo()


@pytest.fixture(scope="module")
def sample_copy(tmp_path_factory, hermetic_env):
    """A temporary copy of the in-repo sample folder."""
    import shutil

    target = tmp_path_factory.mktemp("bh_spc132_sm_dna") / "data"
    shutil.copytree(REPO_DATA, target, ignore=shutil.ignore_patterns(".DS_Store"))
    return target


@pytest.fixture(scope="module")
def qapp_module(hermetic_env):
    from qtpy import QtWidgets

    yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def build_wizard(sample: Path):
    """A wizard with detectors and one burst file loaded (no IRF/background, no fit yet)."""
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    w = MLELifetimeAnalysisWizard()
    QtWidgets.QApplication.processEvents()
    w.channel_definer.load_data_into_tables(CHANNEL_SETTINGS)
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    w.burst_files_list.add_file(str(sample / BURST_TABLE))
    w.load_burst_data()
    w.update_burst_files()
    w.comboBox_window.setCurrentText("green")
    QtWidgets.QApplication.processEvents()
    return w


@pytest.fixture(scope="module")
def fresh_wizard(qapp_module):
    """A wizard nothing was loaded into: the honest empty state of every window.

    (Loading a burst file already builds an IRF/background and fits, so "no fit" needs a wizard with no file.)
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    w = MLELifetimeAnalysisWizard()
    yield w
    w.close()


@pytest.fixture(scope="module")
def fitted_green(qapp_module, sample_copy):
    """Auto IRF/background and one fit of the green detector on the real photons."""
    from qtpy import QtWidgets

    w = build_wizard(sample_copy)
    w.auto_extract_irf_bg()
    QtWidgets.QApplication.processEvents()
    assert w.fit_curves is not None
    yield w
    w.close()
