"""Tests for the head-less experiment/reader/model bootstrap."""

from __future__ import annotations

import chisurf as cs
from chisurf.core.experiments.bootstrap import (
    describe_registry,
    ensure_experiments_registered,
    find_reader,
    resolve_class,
)


def test_readers_and_models_are_registered_without_the_main_window():
    registry = ensure_experiments_registered()
    assert "TCSPC" in registry
    assert "TXT/CSV" in registry["TCSPC"]["readers"]
    assert registry["TCSPC"]["models"], "no TCSPC model is available"


def test_find_reader_matches_by_experiment_and_name():
    ensure_experiments_registered()
    reader = find_reader("TCSPC", "TXT/CSV")
    assert reader is not None
    assert str(reader.name) == "TXT/CSV"


def test_find_reader_reports_a_miss_as_none():
    ensure_experiments_registered()
    assert find_reader("TCSPC", "No Such Reader") is None
    assert find_reader("No Such Experiment", None) is None


def test_resolve_class_tolerates_rubbish():
    assert resolve_class("") is None
    assert resolve_class("not.a.real.module.Class") is None
    assert resolve_class("chisurf.core.experiments.tcspc.TCSPCReader") is not None


def test_describe_registry_matches_the_session():
    ensure_experiments_registered()
    described = describe_registry()
    assert set(described) == {str(name) for name in cs.experiment}
    for entry in described.values():
        assert set(entry) == {"readers", "models", "hidden"}


def test_registration_is_idempotent():
    first = ensure_experiments_registered()
    second = ensure_experiments_registered()
    assert first == second
    for name, entry in second.items():
        assert len(entry["readers"]) == len(set(entry["readers"])), (
            f"{name} registered a reader twice"
        )


def test_a_stale_global_reader_falls_back_to_the_built_in_one(monkeypatch):
    """A user config naming a reader that no longer resolves still yields a usable global fit.

    The Qt shell's ``init_setups`` had this fallback (the ``global`` branch once took the
    whole startup down on a pre-``core`` class path); the headless bootstrap keeps it.
    """
    from chisurf.core.experiments import bootstrap
    from chisurf.core.experiments.globalfit import GlobalFitSetup

    config = {
        "global": {
            "name": "Global (stale test)",
            "hidden": True,
            "readers": [
                {
                    "reader_class": "chisurf.experiments.globalfit.GlobalFitSetup",
                    "reader_params": {"name": "Global-Fit"},
                }
            ],
            "models": [],
        }
    }
    monkeypatch.setattr(bootstrap, "_experiment_config", lambda: config)
    cs.experiment.pop("Global (stale test)", None)
    try:
        bootstrap.ensure_experiments_registered(force=True)
        experiment = cs.experiment["Global (stale test)"]
        assert [type(reader) for reader in experiment.readers] == [GlobalFitSetup]
    finally:
        cs.experiment.pop("Global (stale test)", None)
