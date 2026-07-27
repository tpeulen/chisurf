"""``init_setups`` must merge the *shipped* experiment configuration (RF-022/RF-264).

The GUI used to resolve the packaged ``experiment_configs.yaml`` through
``get_path('cs')``, a path type that does not exist. Nothing raised — the file
simply was not there, so ``default_configs`` loaded empty and the registry was
built from the user's copy alone.

A fresh profile hides this completely: importing ``chisurf`` copies every
packaged settings file into an empty settings directory, so the user copy *is*
the shipped one. The bug only shows on an upgraded install, where the user copy
is a stale snapshot — which is what this test sets up. Sections that exist only
in the shipped file must still reach ``_setup_experiment``, and the user's own
sections must survive the merge.
"""

from __future__ import annotations

import yaml

import chisurf as cs
from chisurf.core.experiments import get_experiment_config_files
from chisurf.gui.main_helper import SetupMixin

#: Experiment sections present in the packaged configuration. A user copy
#: predating them is exactly the situation the bug made permanent.
SHIPPED_ONLY_SECTIONS = ("ics", "pda3c")

#: A section the user's stale copy carries and the shipped file does not.
STALE_SECTION = "rics"


class _ComboStub:
    """Minimal stand-in for the main window's experiment combo box."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def clear(self) -> None:
        self.items = []

    def addItems(self, items) -> None:
        self.items.extend(items)


class _Host(SetupMixin):
    """``SetupMixin`` host that records the sections it is asked to set up."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.comboBox_experimentSelect = _ComboStub()
        self.experiment_names: list[str] = []

    def _setup_experiment(self, exp_type, config) -> None:
        self.seen.append(exp_type)


def _write_stale_user_config(settings_dir) -> None:
    """Write a user configuration from before the shipped sections existed."""
    packaged, _ = get_experiment_config_files()
    shipped = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    stale = {
        "tcspc": shipped["tcspc"],
        STALE_SECTION: {"name": "RICS", "readers": [], "models": []},
    }
    (settings_dir / "experiment_configs.yaml").write_text(yaml.safe_dump(stale), encoding="utf-8")


def _run_init_setups(host: _Host) -> None:
    """Run ``init_setups`` and undo the session-global state it creates."""
    datasets = list(cs.imported_datasets)
    experiments = dict(cs.experiment)
    try:
        host.init_setups()
    finally:
        cs.imported_datasets[:] = datasets
        cs.experiment.clear()
        cs.experiment.update(experiments)


def test_stale_user_config_still_gets_the_shipped_experiments(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_stale_user_config(tmp_path)

    host = _Host()
    _run_init_setups(host)

    for section in SHIPPED_ONLY_SECTIONS:
        assert section in host.seen, f"{section!r} missing — shipped defaults were not merged"
    assert STALE_SECTION in host.seen, "the user's own sections must survive the merge"


def test_the_pre_fix_path_is_what_dropped_them(tmp_path, monkeypatch) -> None:
    """Negative control: with an unreadable packaged path only the user copy is used.

    This is what ``get_path('cs')`` produced, and it is why the defect was
    silent — no exception, just a registry built from a stale file.
    """
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_stale_user_config(tmp_path)
    monkeypatch.setattr(
        "chisurf.core.experiments.get_experiment_config_files",
        lambda: (
            tmp_path / "nowhere" / "experiment_configs.yaml",
            tmp_path / "experiment_configs.yaml",
        ),
    )

    host = _Host()
    _run_init_setups(host)

    assert sorted(host.seen) == sorted(["tcspc", STALE_SECTION])
