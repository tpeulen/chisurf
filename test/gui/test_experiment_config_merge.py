"""The experiment configuration merges the *shipped* file with the user's copy.

The registry used to be built from the user's copy alone, so a copy written before a
section existed (``ics``, ``pda``) never saw it: no exception, just a registry built from a
stale file. ``chisurf.core.experiments.bootstrap._experiment_config`` reads the packaged
file first and merges the user's copy over it.
"""

from __future__ import annotations

import yaml

from chisurf.core.experiments import get_experiment_config_files

#: Experiment sections present in the packaged configuration. A user copy
#: predating them is exactly the situation the bug made permanent. These are
#: checked against the packaged file first, so that renaming a section fails
#: with "no longer shipped" rather than looking like a broken merge.
SHIPPED_ONLY_SECTIONS = ("ics", "pda")

#: A section the user's stale copy carries and the shipped file does not.
STALE_SECTION = "rics"


def _write_stale_user_config(settings_dir) -> None:
    """Write a user configuration from before the shipped sections existed."""
    packaged, _ = get_experiment_config_files()
    shipped = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    for section in SHIPPED_ONLY_SECTIONS:
        assert section in shipped, f"{section!r} is no longer shipped — update this test"
    stale = {
        "tcspc": shipped["tcspc"],
        STALE_SECTION: {"name": "RICS", "readers": [], "models": []},
    }
    (settings_dir / "experiment_configs.yaml").write_text(yaml.safe_dump(stale), encoding="utf-8")


def test_stale_user_config_still_gets_the_shipped_experiments(tmp_path, monkeypatch) -> None:
    from chisurf.core.experiments.bootstrap import _experiment_config

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_stale_user_config(tmp_path)

    seen = set(_experiment_config())

    for section in SHIPPED_ONLY_SECTIONS:
        assert section in seen, f"{section!r} missing — shipped defaults were not merged"
    assert STALE_SECTION in seen, "the user's own sections must survive the merge"


def test_the_pre_fix_path_is_what_dropped_them(tmp_path, monkeypatch) -> None:
    """Negative control: with an unreadable packaged path only the user copy is used."""
    from chisurf.core.experiments.bootstrap import _experiment_config

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_stale_user_config(tmp_path)
    monkeypatch.setattr(
        "chisurf.core.experiments.get_experiment_config_files",
        lambda: (
            tmp_path / "nowhere" / "experiment_configs.yaml",
            tmp_path / "experiment_configs.yaml",
        ),
    )

    assert sorted(_experiment_config()) == sorted(["tcspc", STALE_SECTION])
