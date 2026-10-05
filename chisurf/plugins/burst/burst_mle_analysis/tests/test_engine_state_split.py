"""Split by H2MM state in the Qt-free engine (what the native Burst Analysis step 8 runs).

The H2MM photon table is written here for the in-repository BH sample: within every burst of ``m000`` the first half
of the photons is state 0 and the second half state 1. ``MleSession.run_batch`` with ``split_by_state`` must then give
``Tau S0 (green)`` / ``Tau S1 (green)`` beside ``Tau (green)``, a pooled lifetime per state and detector, and write
``Info/state_lifetimes.csv`` beside the analysis. The wizard's state methods are the same functions.
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column, store_from_arrays, write_csv_table
from chisurf.plugins.burst.burst_mle_analysis import engine, state_split

from .conftest import BURST_TABLE, CHANNEL_SETTINGS


@pytest.fixture(scope="module")
def split_session(sample_copy, tmp_path_factory):
    folder = tmp_path_factory.mktemp("split") / "data"
    shutil.copytree(sample_copy, folder)
    analysis = folder / BURST_TABLE.parent.parent
    h2mm = analysis / "h2mm"
    shutil.rmtree(h2mm, ignore_errors=True)
    h2mm.mkdir()
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    session.add_burst_files([folder / BURST_TABLE])
    table = session.df_bursts
    stems = [
        str(v).replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0] for v in table["First File"]
    ]
    first, last = numeric_column(table, "First Photon"), numeric_column(table, "Last Photon")
    photon, state = [], []
    for stem, a, b in zip(stems, first, last):
        if stem != "m000" or not np.isfinite(a) or b <= a:
            continue
        idx = np.arange(int(a), int(b) + 1)
        half = idx.size // 2
        photon.append(idx)
        state.append(np.r_[np.zeros(half, dtype=int), np.ones(idx.size - half, dtype=int)])
    photon, state = np.concatenate(photon), np.concatenate(state)
    write_csv_table(
        h2mm / "h2mm_photons.csv",
        store_from_arrays({"Photon": photon, "State": state, "Source": np.zeros_like(photon)}),
        delimiter=",",
    )
    (h2mm / "h2mm_result.json").write_text(json.dumps({"output_paths": {"sources": "m000.spc"}}))
    for det in ("green", "red"):
        session.current_detector = det
        session.auto_extract()
    session.split_by_state = True
    session.run_batch(max_workers=2)
    return session, analysis


def test_the_batch_has_a_column_block_per_state(split_session):
    session, _ = split_session
    assert session.n_states == 2
    keys = set().union(*(r.keys() for r in session.burst_results))
    for column in ("Tau (green)", "Tau S0 (green)", "Tau S1 (green)", "Tau S0 (red)"):
        assert column in keys, column
    m000 = [r for r in session.burst_results if "m000" in str(r["First File"])]
    fitted = [r["Tau S0 (green)"] for r in m000 if np.isfinite(r.get("Tau S0 (green)", np.nan))]
    assert fitted, "no state of m000 was fitted"


def test_each_state_has_a_pooled_lifetime(split_session):
    session, _ = split_session
    rows = session.state_lifetimes
    assert {(r["Detector"], r["State"]) for r in rows} == {
        ("green", 0),
        ("green", 1),
        ("red", 0),
        ("red", 1),
    }
    green = {r["State"]: r for r in rows if r["Detector"] == "green"}
    assert green[0]["Photons"] > 1000 and green[1]["Photons"] > 1000
    assert 0.1 < green[0]["Tau"] < 10.0 and 0.1 < green[1]["Tau"] < 10.0


def test_export_writes_state_columns_and_the_state_table(split_session):
    session, analysis = split_session
    written = session.export_results()
    table = analysis / "Info" / "state_lifetimes.csv"
    assert table in written and table.is_file()
    header = next(p for p in written if p.suffix == ".bg4").read_text().splitlines()[0]
    assert "Tau S0 (green)" in header and "Tau S1 (green)" in header


def test_without_an_h2mm_run_the_split_says_why(sample_copy, tmp_path):
    arrays, n_states, message = state_split.load_state_arrays(tmp_path, {})
    assert (arrays, n_states) == ({}, 0) and message.startswith("Split by state:")
    assert state_split.load_state_arrays(None, {})[1] == 0


def test_the_wizard_delegates_to_the_same_functions():
    from chisurf.plugins.burst.burst_mle_analysis import wizard

    source = open(wizard.__file__).read()
    for name in (
        "load_state_arrays",
        "pool_state_decays",
        "fit_pooled_state_decays",
        "state_lifetime_rows",
        "seed_state_fits",
        "write_state_lifetimes",
    ):
        assert f"state_split.{name}(" in source, name
