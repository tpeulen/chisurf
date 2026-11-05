"""A search in this process hands its burst tables over as they are; a remote one sends rows.

Serialising 21 808 bursts as row dictionaries walked 1.9 M objects (12 s) and the model rebuilt
the table from them (2 s), all inside one process. Through an ``InProcessClient`` the result now
carries ``tables`` (``{file: burst table}``) and no rows; a JSON-RPC caller still gets the rows
the contract describes, and cannot ask for the tables (the marker is an object, not a value).

On copies of the in-repository BH SPC-132 photons (two small files).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column, row_count
from chisurf.plugins.burst.burst_selection.api.contract import IN_PROCESS, RESULT_TABLES
from chisurf.plugins.burst.burst_selection.gui.client import BurstSelectionClient

from .test_search_ahead import step  # noqa: F401  (fixture)
from .test_emtk_native_app import files  # noqa: F401  (fixture)


class _JsonClient:
    """A remote client as the server sees it: parameters and result cross JSON."""

    def __init__(self) -> None:
        self._dispatcher = BurstSelectionClient._make_local_client()._dispatcher

    def call(self, method, params=None, timeout=None):
        sent = json.loads(json.dumps(params or {}, default=str))
        return json.loads(json.dumps(self._dispatcher.dispatch(method, sent)))


def _search(client: BurstSelectionClient, model) -> dict:
    return client.analyze_files(list(model.files), **model.search_ahead_request())


def test_in_process_search_returns_the_tables_and_no_rows(step):  # noqa: F811
    m = step.model
    assert m.client._client.__class__.__name__ == "InProcessClient"
    result = _search(m.client, m)
    tables = result[RESULT_TABLES]
    assert set(tables) == {str(p) for p in m.files}
    assert not any(result["dataframes"].get(str(p)) for p in m.files), "rows were built anyway"
    assert sum(row_count(t) for t in tables.values()) > 0
    m.show_ahead(result)
    for path in m.files:  # the model shows the search's own tables, not a rebuilt copy
        assert m.frames_by_file[str(path)] is tables[str(path)]
    assert row_count(m.display_frame) > 0


def test_a_remote_search_gets_rows_and_the_same_bursts(step):  # noqa: F811
    m = step.model
    local = _search(m.client, m)
    remote = _search(BurstSelectionClient(_JsonClient()), m)
    assert RESULT_TABLES not in remote
    assert remote["metadata"]["n_bursts"] == local["metadata"]["n_bursts"]
    frames = m._result_frames(remote)
    for path in m.files:
        assert len(remote["dataframes"][str(path)]) > 0
        table = local[RESULT_TABLES][str(path)]
        assert row_count(frames[str(path)]) == row_count(table)
        for column in ("Number of Photons", "Duration (ms)"):
            np.testing.assert_allclose(
                numeric_column(frames[str(path)], column), numeric_column(table, column)
            )


def test_a_json_request_cannot_ask_for_the_tables(step):  # noqa: F811
    m = step.model
    dispatcher = BurstSelectionClient._make_local_client()._dispatcher
    params = {"files": [str(p) for p in m.files], **m.search_ahead_request(),
              "in_process": repr(IN_PROCESS)}
    out = json.loads(json.dumps(dispatcher.dispatch("burst_selection.jobs.analyze_files",
                                                    json.loads(json.dumps(params)))))
    assert out["ok"], out
    assert RESULT_TABLES not in out["result"]
    assert all(out["result"]["dataframes"][str(p)] for p in m.files)


@pytest.mark.parametrize("remote", [False, True], ids=["in-process", "json"])
def test_store_results_writes_tables_or_rows(step, remote):  # noqa: F811
    m = step.model
    client = BurstSelectionClient(_JsonClient()) if remote else m.client
    found = _search(client, m)
    stored = client.store_results(list(m.files), found, **m.request())
    by_file = stored["output_paths_by_file"]
    assert all(".pto/" in by_file[str(p)]["output_folder"] for p in m.files)
    m._finish(stored)
    assert m.has_processed and row_count(m.display_frame) > 0
