"""Saving and reloading a session.

"Save all of this so I can carry on tomorrow" is one of the documented
example prompts, and it did not work: three separate defects sat between the
request and a file on disk. These tests keep that path honest.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

import chisurf as cs
from chisurf.core.agent import ToolError
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import fitting as fitting_tools
from chisurf.history.core import json_safe_payload
from test.agent.conftest import DATA_DIR

DECAY = DATA_DIR / "tcspc" / "EasyTau300" / "215-268 D0.dat"
IRF = DATA_DIR / "tcspc" / "EasyTau300" / "215-268 D0 irf.dat"


@pytest.fixture()
def fitted_session(clean_session, tmp_path):
    """Return a context with one loaded, fitted decay in a scratch directory."""
    from chisurf.core.agent import AgentContext

    for source in (DECAY, IRF):
        shutil.copy(source, tmp_path)
    context = AgentContext(working_directory=str(tmp_path))
    data_tools.load_data(context, directory=".", pattern="*.dat")
    fitting_tools.create_fit(context, model_name="Lifetime", datasets=[0])
    fitting_tools.run_fit(context, fit=0)
    return context


# ── the payload sanitiser ─────────────────────────────────────────────


def test_a_live_object_in_a_payload_becomes_text():
    """dataset.add records the reader it was handed; JSON cannot encode it."""

    class Reader:
        def __repr__(self):
            return "Reader()"

    cleaned = json_safe_payload({"filename": "a.dat", "experiment_reader": Reader()})
    assert cleaned["filename"] == "a.dat"
    assert cleaned["experiment_reader"].startswith("<Reader")


def test_the_sanitiser_keeps_ordinary_values_intact():
    payload = {"a": 1, "b": 1.5, "c": "text", "d": True, "e": None, "f": [1, {"g": 2}]}
    assert json_safe_payload(payload) == payload


def test_the_sanitiser_reaches_into_nested_structures():
    cleaned = json_safe_payload({"outer": {"inner": [object()]}})
    assert cleaned["outer"]["inner"][0].startswith("<object")


def test_the_sanitiser_survives_a_cycle():
    payload: dict = {"name": "loop"}
    payload["self"] = payload
    import json

    json.dumps(json_safe_payload(payload))


# ── saving ────────────────────────────────────────────────────────────


def test_a_session_with_loaded_data_can_be_saved(fitted_session, tmp_path):
    """A live reader in the history used to make this impossible."""
    result = fitting_tools.save_project(fitted_session, path="session.csp")

    assert result["ok"]
    saved = pathlib.Path(result["path"])
    assert saved.is_file() and saved.stat().st_size > 0
    assert result["n_fits"] == 1


def test_the_archive_extension_is_added_when_missing(fitted_session):
    result = fitting_tools.save_project(fitted_session, path="no_extension")
    assert pathlib.Path(result["path"]).suffix == ".csp"


def test_saving_into_a_new_directory_works(fitted_session):
    result = fitting_tools.save_project(fitted_session, path="output/run1.csp")
    assert pathlib.Path(result["path"]).is_file()


def test_the_history_of_the_session_is_serialisable(fitted_session, tmp_path):
    """The whole event log goes into the archive, so it must encode."""
    history = getattr(cs, "history", None)
    if history is None or not hasattr(history, "save_jsonl"):
        pytest.skip("no history in this build")
    target = tmp_path / "history.jsonl"
    history.save_jsonl(target)
    assert target.is_file() and target.stat().st_size > 0


# ── reloading ─────────────────────────────────────────────────────────


def test_a_saved_session_reloads_with_its_data_and_fit(fitted_session):
    """The loader iterated the fit list as a mapping and skipped everything."""
    from chisurf.macros import core_fit

    before_chi2r = round(float(cs.fits[0].chi2r), 4)
    before_datasets = len(cs.imported_datasets)
    saved = fitting_tools.save_project(fitted_session, path="session.csp")["path"]

    cs.imported_datasets[:] = []
    cs.fits[:] = []
    core_fit.load_fit_project(saved)

    assert len(cs.imported_datasets) == before_datasets
    assert len(cs.fits) == 1, "the fit records were skipped on load"
    assert round(float(cs.fits[0].chi2r), 4) == pytest.approx(before_chi2r, rel=1e-6)


def test_saving_an_empty_session_still_produces_an_archive(clean_session, tmp_path):
    from chisurf.core.agent import AgentContext

    context = AgentContext(working_directory=str(tmp_path))
    result = fitting_tools.save_project(context, path="empty.csp")
    assert pathlib.Path(result["path"]).is_file()
    assert result["n_fits"] == 0


def test_an_unwritable_target_is_reported(fitted_session):
    with pytest.raises((ToolError, OSError)):
        fitting_tools.save_project(fitted_session, path="/proc/nope/session.csp")
