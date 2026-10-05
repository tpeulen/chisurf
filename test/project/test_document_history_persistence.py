"""Ordinary project persistence owns scientific history, not just event text."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys

import numpy as np
import pytest


def _local_history(monkeypatch, tmp_path):
    """Use shipped ParseModels with duplicate names and a true cross-fit link."""
    import chisurf as cs
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.parse import ParseModel
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.transition import replace_project
    from chisurf.history.core import OperationHistory
    from chisurf.macros.core_fit import get_project_payload

    raw = tmp_path / "owned-data.csv"
    raw.write_bytes(b"0,2\n1,6\n2,10\n")
    curves = [
        DataCurve(
            x=np.arange(8.0),
            y=4 * np.arange(8.0) + 2,
            ex=np.ones(8),
            ey=np.ones(8),
            name="same-name",
        )
        for _ in range(2)
    ]
    fits = [Fit(data=curve, model_class=ParseModel, name="same-fit") for curve in curves]
    for fit in fits:
        fit.model.func = "a*x+b"
        fit.model.parameters_all_dict["a"].value = 4
        fit.model.parameters_all_dict["b"].value = 2
        fit.model.update()
    fits[1].model.parameters_all_dict["a"].link = fits[0].model.parameters_all_dict["a"]
    history = OperationHistory()
    monkeypatch.setattr(cs, "history", history, raising=False)
    monkeypatch.setattr(cs, "imported_datasets", curves)
    monkeypatch.setattr(cs, "fits", fits)
    monkeypatch.setattr(cs, "cs", None, raising=False)
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(
        cs,
        "project_resources",
        ResourceContext(sources={str(raw): raw.read_bytes()}),
        raising=False,
    )
    history.configure_science(
        get_project_payload, lambda project: replace_project(project, owner=cs)
    )
    return cs, history, raw


def _edit(cs, history, value):
    """Record acknowledged real parameter edits with canonical science."""
    parameter = cs.fits[0].model.parameters_all_dict["a"]
    parameter.value = value
    for fit in cs.fits:
        fit.model.update()
    history.record(
        "parameter.value",
        "set slope",
        {"new_value": value},
        target_uid=parameter.unique_identifier,
        persist=False,
    )


def test_ordinary_macro_save_captures_history_cursor_baseline_and_redo(monkeypatch, tmp_path):
    """The PTO document owns complete replay state when saved after undo."""
    from chisurf.core.project.storage import load_file
    from chisurf.macros.core_fit import get_project_payload, save_project

    cs, history, raw = _local_history(monkeypatch, tmp_path)
    _edit(cs, history, 7)
    assert history.navigate(-1)["ok"] is True
    expected = history.export_state()
    assert expected["cursor"] == -1
    assert expected["baseline"] and expected["states"]
    project = get_project_payload("undone session")
    destination = save_project(str(tmp_path / "history.cs.pto"))
    readback = load_file(destination)
    assert project.extra["history_state"] == expected
    assert readback.extra["history_state"] == expected
    raw.unlink()
    np.testing.assert_array_equal(cs.fits[1].model.y, 4 * np.arange(8.0) + 2)


def test_fresh_project_load_can_redo_after_deleted_original_source(monkeypatch, tmp_path):
    """A new interpreter needs no old callbacks, original files or MMFDB."""
    from chisurf.macros.core_fit import save_project

    cs, history, raw = _local_history(monkeypatch, tmp_path)
    fit_uids = [fit.unique_identifier for fit in cs.fits]
    parameter_uid = cs.fits[0].model.parameters_all_dict["a"].unique_identifier
    _edit(cs, history, 7)
    history.navigate(-1)
    destination = save_project(str(tmp_path / "fresh-history.cs.pto"))
    raw.unlink()
    report_path = tmp_path / "fresh-report.json"
    code = r"""
import importlib, json, sys
import numpy as np
import chisurf as cs
from chisurf.core.project.transition import replace_project
from chisurf.history.core import OperationHistory
from chisurf.macros.core_fit import get_project_payload, load_project, save_project
cs.cs = None
cs.__client__ = None
cs.imported_datasets = []
cs.fits = []
cs.history = OperationHistory()
old_lock = cs.history._lock
assert load_project(sys.argv[1])["ok"] is True
history = importlib.import_module("chisurf.history").get_history()
assert history is cs.history
assert history._lock is old_lock
assert history.cursor_index() == -1, (history.cursor_index(), [(e['action_type'], e['summary']) for e in history.list_events()])
assert history.can_navigate(0)
history.configure_science(get_project_payload, lambda project: replace_project(project, owner=cs))
assert [fit.unique_identifier for fit in cs.fits] == json.loads(sys.argv[3])
assert cs.fits[0].model.parameters_all_dict["a"].unique_identifier == sys.argv[4]
assert cs.fits[1].model.parameters_all_dict["a"].link is cs.fits[0].model.parameters_all_dict["a"]
np.testing.assert_array_equal(cs.fits[1].model.y, 4 * np.arange(8.) + 2)
assert history.navigate(0)["ok"] is True
np.testing.assert_array_equal(cs.fits[1].model.y, 7 * np.arange(8.) + 2)
assert history.navigate(-1)["ok"] is True
np.testing.assert_array_equal(cs.fits[1].model.y, 4 * np.arange(8.) + 2)
second = save_project(sys.argv[1] + ".second.cs.pto")
json.dump({"ok": True, "cursor": history.cursor_index(), "events": len(history.list_events()), "resaved": str(second), "source_count": len(cs.project_resources.sources)}, open(sys.argv[2], "w"))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(destination),
            str(report_path),
            json.dumps(fit_uids),
            parameter_uid,
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
    )
    (tmp_path / "fresh.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text())
    assert report["ok"] is True
    assert report["cursor"] == -1
    assert report["events"] == 1
    assert report["source_count"] == 1


@pytest.mark.parametrize("route", ["service", "local-api"])
def test_server_and_api_capture_the_owners_complete_history(monkeypatch, tmp_path, route):
    """A different process-global history cannot replace the owning envelope."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.history.core import OperationHistory
    from chisurf.server.services.projects import _capture_project
    from chisurf.server.session import SessionState

    cs, history, _raw = _local_history(monkeypatch, tmp_path)
    _edit(cs, history, 7)
    assert history.navigate(-1)["ok"] is True
    expected = history.export_state()
    state = SessionState(datasets=cs.imported_datasets, fits=cs.fits)
    setattr(state, "history", history)
    setattr(state, "project_resources", cs.project_resources)
    monkeypatch.setattr(cs, "history", OperationHistory())
    project = (
        _capture_project(state)
        if route == "service"
        else ChiSurfAPI(mode="local", state=state).capture_project()
    )
    assert project.extra["history_state"] == expected
    assert project.extra["history_events"] == expected["events"]
    assert history.export_state() == expected
    assert cs.history.list_events() == []


def test_history_facade_resolves_explicit_runtime_owner_without_namespace_mutation(monkeypatch):
    """Module and runtime access must address the same installed history and lock."""
    import chisurf as cs
    from chisurf.history.core import OperationHistory

    facade = importlib.import_module("chisurf.history")
    facade.get_history()
    owned = OperationHistory()
    monkeypatch.setattr(cs, "history", owned)
    namespace = dict(vars(facade))
    assert facade.get_history() is owned
    assert facade.get_history()._lock is owned._lock
    assert vars(facade).keys() == namespace.keys()
    assert all(vars(facade)[name] is value for name, value in namespace.items())


@pytest.mark.parametrize("with_envelope", [True, False])
def test_owner_publishes_history_notification_only_after_acknowledgement(
    monkeypatch, tmp_path, with_envelope
):
    """Views see one committed history change and never the tentative import."""
    from chisurf.core.project.transition import OwnerTransaction
    from chisurf.macros.core_fit import get_project_payload

    cs, history, _raw = _local_history(monkeypatch, tmp_path)
    _edit(cs, history, 7)
    assert history.navigate(-1)["ok"] is True
    incoming = get_project_payload()
    if not with_envelope:
        incoming.extra.clear()
    history.clear()
    observations = []
    history.subscribe_state(
        lambda state: observations.append((state, cs.fits[0].model.parameters_all_dict["a"].value))
    )
    transaction = OwnerTransaction(cs, incoming)
    transaction.begin()
    assert observations == []
    transaction.finish(commit=True)
    assert observations == [({"cursor": -1, "event_count": 1 if with_envelope else 0}, 4.0)]


def test_failed_publication_restores_state_subscriber_identity(monkeypatch, tmp_path):
    """A tentative controller subscription cannot leak into the retained owner."""
    from chisurf.core.project import capture_session
    from chisurf.core.project.transition import replace_project

    cs, history, _raw = _local_history(monkeypatch, tmp_path)
    original_list = history._state_subscribers
    original_callbacks = tuple(original_list)

    def reject(*_args):
        history.subscribe_state(lambda _state: None)
        raise RuntimeError("controller rejected")

    with pytest.raises(RuntimeError, match="controller rejected"):
        replace_project(capture_session([], []), owner=cs, present=reject)
    assert history._state_subscribers is original_list
    assert tuple(history._state_subscribers) == original_callbacks


def test_failed_document_publication_retains_full_history_state(monkeypatch, tmp_path):
    """Failure restores scientific cursor state and runtime identity together."""
    from chisurf.core.project import capture_session
    from chisurf.core.project.transition import replace_project

    cs, history, raw = _local_history(monkeypatch, tmp_path)
    _edit(cs, history, 7)
    original = history.export_state()
    original_fit = cs.fits[0]
    original_lock = history._lock
    incoming = capture_session([], [])

    def fail(*args):
        history.clear()
        raise RuntimeError("synchronous view failed")

    with pytest.raises(RuntimeError, match="synchronous view failed"):
        replace_project(incoming, owner=cs, present=fail)
    assert cs.fits[0] is original_fit
    assert history._lock is original_lock
    assert history.export_state() == original
    assert history.navigate(-1)["ok"] is True
    np.testing.assert_array_equal(cs.fits[1].model.y, 4 * np.arange(8.0) + 2)
