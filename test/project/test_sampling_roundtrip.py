"""A fit's sampling run survives capture, save, load, restore and history edits.

``fit.sampling_chain`` and ``fit.sampling_diagnostics`` are scientific results:
they travel inside the ``.cs.pto`` as a tab-separated chain table and a JSON
report, named by a stub in the fit member's record.
"""

from __future__ import annotations

import numpy as np
import pytest

from test.project.test_e2e_undo_redo_save_reload import owner  # noqa: F401 - fixture


def _synthetic_run():
    rng = np.random.default_rng(7)
    chains = rng.normal(size=(3, 50, 2))
    chain = {
        "parameter_names": ["E2ELinearModel:p0", "E2ELinearModel:p1"],
        "parameter_values": chains.reshape(-1, 2),
        "chains": chains,
        "burn_in": 5,
    }
    diagnostics = {
        "n_runs": 1,
        "n_chains": 3,
        "n_draws": 50,
        "burn_in": 5,
        "acceptance_rate": None,
        "parameters": [{"name": "p0", "rhat": float("nan"), "ess": np.float64(120.0)}],
        "warnings": ["R-hat could not be estimated"],
    }
    return chain, diagnostics


def _member(fit):
    """The fit that owns a run: a group's selected member, as ``sample_fit`` sets it."""
    return fit.selected_fit if getattr(fit, "grouped_fits", None) else fit


def _fit_with_run(cs):
    from chisurf.macros.core_fit import add_fit

    add_fit(dataset_indices=[0], model_name="E2ELinearModel")
    fit = cs.fits[0]
    fit.fit_range = (0, 8)
    chain, diagnostics = _synthetic_run()
    member = _member(fit)
    member.sampling_chain = chain
    member.sampling_diagnostics = diagnostics
    return member, chain


def test_the_chain_survives_save_load_and_restore(owner, tmp_path):  # noqa: F811
    from chisurf.core.project import storage
    from chisurf.core.project.lifecycle import snapshot_fingerprint
    from chisurf.core.project.session import restore_session
    from chisurf.macros.core_fit import get_project_payload

    cs, _history = owner
    fit, chain = _fit_with_run(cs)
    project = get_project_payload("sampling")
    stub = project.fits[0]["members"][0]["sampling"]
    uid = fit.unique_identifier
    assert stub["chain"] == f"sampling/{uid}/chain.er4"
    assert stub["diagnostics"] == f"sampling/{uid}/diagnostics.json"
    assert stub["burn_in"] == 5

    path = storage.save_file(project, tmp_path / "s.cs.pto")
    loaded = storage.load_file(path)
    assert snapshot_fingerprint(loaded) == snapshot_fingerprint(project)
    restored = _member(restore_session(loaded).fits[0])
    got = restored.sampling_chain
    assert got["chains"].shape == (3, 50, 2)
    assert np.allclose(got["chains"], chain["chains"])
    assert got["burn_in"] == 5
    assert got["parameter_names"] == chain["parameter_names"]
    report = restored.sampling_diagnostics
    assert report["warnings"] == ["R-hat could not be estimated"]
    # strict JSON: a NaN statistic is stored as null, not as an invalid token
    assert report["parameters"][0]["rhat"] is None
    assert report["parameters"][0]["ess"] == 120.0


def test_a_history_edit_keeps_the_chain(owner):  # noqa: F811
    cs, history = owner
    _fit, chain = _fit_with_run(cs)
    history.record("fit.range.set", "fit range 0-8", persist=False)

    def set_p0(session):
        session.fits[0].model.p0.value = 2.5

    history.apply_edit(set_p0, "parameter.value", "set p0", persist=False)
    edited = history.cursor_index()
    assert np.allclose(_member(cs.fits[0]).sampling_chain["chains"], chain["chains"])
    # Undo and redo restore the snapshot, the chain with it.
    assert history.navigate(edited - 1)["ok"] is True
    assert history.navigate(edited)["ok"] is True
    assert np.allclose(_member(cs.fits[0]).sampling_chain["chains"], chain["chains"])
    assert _member(cs.fits[0]).sampling_diagnostics["n_chains"] == 3


def test_a_new_run_replaces_the_entries_of_the_restored_one(owner):  # noqa: F811
    """Restored curves keep the loaded resources; their stale chain must not
    collide with the live one at the next capture."""
    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.macros.core_fit import get_project_payload

    cs, _history = owner
    fit, _chain = _fit_with_run(cs)
    first = get_project_payload("first")
    restored = restore_session(first)
    member = _member(restored.fits[0])
    new_chains = np.ones((2, 20, 2))
    member.sampling_chain = {
        "chains": new_chains,
        "parameter_names": ["a", "b"],
        "burn_in": 0,
        "parameter_values": new_chains.reshape(-1, 2),
    }
    member.sampling_diagnostics = None
    second = capture_session(restored.datasets, restored.fits, name="second")
    uid = member.unique_identifier
    assert f"sampling/{uid}/diagnostics.json" not in second.resources.entries
    again = _member(restore_session(second).fits[0])
    assert np.array_equal(again.sampling_chain["chains"], new_chains)
    assert again.sampling_diagnostics is None


def test_the_fingerprint_hashes_a_chain_by_size_not_bytes(owner):  # noqa: F811
    from chisurf.core.project.lifecycle import snapshot_fingerprint
    from chisurf.core.project.project import ResourceContext

    cs, _history = owner
    _fit_with_run(cs)
    from chisurf.macros.core_fit import get_project_payload

    project = get_project_payload("fp")
    entries = dict(project.resources.entries)
    name = next(n for n in entries if n.endswith("chain.er4"))
    before = snapshot_fingerprint(project)
    entries[name] = b"x" * len(entries[name])
    project.resources = ResourceContext(entries)
    assert snapshot_fingerprint(project) == before
    entries[name] = entries[name] + b"x"
    project.resources = ResourceContext(entries)
    assert snapshot_fingerprint(project) != before


def test_ndx_reads_the_saved_chain_without_chisurf(owner, tmp_path):  # noqa: F811
    """The saved project is what ndX's ``cs_project`` importer opens."""
    pytest.importorskip("ndxplorer.io.project_reader")
    from ndxplorer.io import project_reader

    from chisurf.core.project import storage
    from chisurf.macros.core_fit import get_project_payload

    cs, _history = owner
    fit, chain = _fit_with_run(cs)
    path = storage.save_file(get_project_payload("ndx"), tmp_path / "n.cs.pto")
    stores = project_reader.list_stores(path)
    assert [s["name"] for s in stores] == [f"sampling/{fit.unique_identifier}/chain.er4"]
    assert stores[0]["rows"] == 150
    source = project_reader.read_store(path)
    assert source.size == 150
