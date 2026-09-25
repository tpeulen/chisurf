"""Tests for the head-less experiment/reader/model bootstrap."""

from __future__ import annotations

import pytest

import chisurf as cs
from chisurf.core.experiments.bootstrap import (
    describe_registry,
    ensure_experiments_registered,
    ensure_qt_application,
    find_reader,
    qt_application_available,
    resolve_class,
)


def test_readers_and_models_are_registered_without_the_main_window():
    registry = ensure_experiments_registered(allow_widgets=False)
    assert "TCSPC" in registry
    assert "TXT/CSV" in registry["TCSPC"]["readers"]
    assert registry["TCSPC"]["models"], "no TCSPC model is available"


@pytest.mark.gui
@pytest.mark.widget
def test_the_offscreen_application_outlives_the_call():
    """A QApplication nobody references is collected the moment it returns.

    When that happened, every Qt-only reader and model silently disappeared
    from a head-less session — the daily-driver "Lifetime" model among them.
    """
    assert ensure_qt_application() is True
    assert qt_application_available() is True, "the application was garbage-collected"
    assert ensure_qt_application() is True, "a second call must be a no-op"


@pytest.mark.gui
@pytest.mark.widget
def test_qt_widget_models_appear_once_an_application_exists():
    ensure_qt_application()
    registry = ensure_experiments_registered(allow_widgets=True, force=True)
    names = [name.strip() for name in registry["TCSPC"]["models"]]
    assert "Lifetime" in names, f"the hand-written lifetime model is missing: {names}"


def test_find_reader_matches_by_experiment_and_name():
    ensure_experiments_registered(allow_widgets=False)
    reader = find_reader("TCSPC", "TXT/CSV")
    assert reader is not None
    assert str(reader.name) == "TXT/CSV"


def test_find_reader_reports_a_miss_as_none():
    ensure_experiments_registered(allow_widgets=False)
    assert find_reader("TCSPC", "No Such Reader") is None
    assert find_reader("No Such Experiment", None) is None


def test_resolve_class_tolerates_rubbish():
    assert resolve_class("") is None
    assert resolve_class("not.a.real.module.Class") is None
    assert resolve_class("chisurf.core.experiments.tcspc.TCSPCReader") is not None


def test_describe_registry_matches_the_session():
    ensure_experiments_registered(allow_widgets=False)
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
