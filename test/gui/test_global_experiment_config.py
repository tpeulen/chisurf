"""The ``global`` experiment section must not take the startup stage down (RF-463).

Every other section in ``experiment_configs.yaml`` survives a class path that no
longer resolves — ``_setup_experiment`` skips a ``None`` class and wraps each
reader in ``try``. The ``global`` branch of ``init_setups`` did neither, so a
user copy carrying a pre-``core/``-move reader
(``chisurf.experiments.globalfit.GlobalFitSetup``) raised
``TypeError: 'NoneType' object is not callable`` out of the ``init_setups``
startup stage. The splash then stopped at stage 5 of 11 — ``define_actions``,
``load_tools`` and ``arrange_widgets`` never ran, and the only trace was a single
``Splash startup failed`` traceback.

These tests pin the fallback: a broken, empty or malformed ``global`` section
leaves a usable global-fit experiment behind instead of raising.
"""

from __future__ import annotations

import pytest
import yaml

import chisurf as cs
from chisurf.core.experiments import get_experiment_config_files
from chisurf.core.experiments.globalfit import GlobalFitSetup
from chisurf.gui.main_helper import SetupMixin

#: A reader class path from before the ``chisurf.core`` move — the exact kind of
#: stale entry an upgraded user profile keeps.
STALE_READER = "chisurf.experiments.globalfit.GlobalFitSetup"

#: A reader class that resolves but explodes on construction.
BOOM_READER = "test.gui.test_global_experiment_config._BoomReader"


class _BoomReader:
    """Reader stand-in that fails to construct."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError("reader construction failed")


class _ComboStub:
    """Minimal stand-in for the main window's experiment combo box."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def clear(self) -> None:
        self.items = []

    def addItems(self, items) -> None:
        self.items.extend(items)


class _Host(SetupMixin):
    """``SetupMixin`` host that stubs out the per-experiment setup."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.comboBox_experimentSelect = _ComboStub()
        self.experiment_names: list[str] = []

    def _setup_experiment(self, exp_type, config) -> None:
        self.seen.append(exp_type)


def _write_user_config(settings_dir, global_section) -> None:
    """Write a user configuration whose ``global`` section is ``global_section``."""
    packaged, _ = get_experiment_config_files()
    shipped = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    config = {"tcspc": shipped["tcspc"], "global": global_section}
    (settings_dir / "experiment_configs.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def _run_init_setups(host: _Host):
    """Run ``init_setups`` and undo the session-global state it creates."""
    datasets = list(cs.imported_datasets)
    experiments = dict(cs.experiment)
    try:
        host.init_setups()
        return dict(cs.experiment)
    finally:
        cs.imported_datasets[:] = datasets
        cs.experiment.clear()
        cs.experiment.update(experiments)


@pytest.mark.parametrize(
    "global_section",
    [
        pytest.param(
            {
                "name": "Global",
                "hidden": True,
                "readers": [
                    {"reader_class": STALE_READER, "reader_params": {"name": "Global-Fit"}}
                ],
            },
            id="unresolvable-reader-class",
        ),
        pytest.param(
            {
                "name": "Global",
                "hidden": True,
                "readers": [{"reader_class": BOOM_READER, "reader_params": {"name": "Global-Fit"}}],
            },
            id="reader-fails-to-construct",
        ),
        pytest.param(
            {"name": "Global", "hidden": True, "readers": [{}]},
            id="reader-entry-without-a-class",
        ),
    ],
)
def test_a_broken_global_reader_falls_back_instead_of_raising(
    tmp_path, monkeypatch, global_section
) -> None:
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_user_config(tmp_path, global_section)

    experiments = _run_init_setups(_Host())

    global_fit = experiments.get("Global")
    assert global_fit is not None, "the global experiment must still be registered"
    assert isinstance(global_fit.readers[0], GlobalFitSetup), (
        "a broken configured reader must fall back to the built-in global-fit reader"
    )


@pytest.mark.parametrize(
    "global_section",
    [pytest.param(None, id="empty-section"), pytest.param("Global", id="not-a-mapping")],
)
def test_a_malformed_global_section_falls_back_to_the_defaults(
    tmp_path, monkeypatch, global_section
) -> None:
    """An empty ``global:`` key merges to ``None`` — that must not raise either."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    _write_user_config(tmp_path, global_section)

    experiments = _run_init_setups(_Host())

    global_fit = experiments.get("Global")
    assert global_fit is not None
    assert isinstance(global_fit.readers[0], GlobalFitSetup)


def test_the_shipped_global_section_still_builds_its_configured_reader(
    tmp_path, monkeypatch
) -> None:
    """Guard the happy path: a valid section is used, not silently replaced."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    packaged, _ = get_experiment_config_files()
    shipped = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    _write_user_config(tmp_path, shipped["global"])

    experiments = _run_init_setups(_Host())

    global_fit = experiments.get("Global")
    assert global_fit is not None
    assert isinstance(global_fit.readers[0], GlobalFitSetup)
    assert global_fit.readers[0].name == "Global-Fit"
    assert global_fit.model_classes, "the configured model classes must be registered"
