"""The quenching analysis through its headless surfaces: the API facade and the RPC methods.

``quest.analysis.{template,run,result,site_table}`` and the job methods, through the
in-process client every other surface uses (``rpc.local_client``) and through the wire
conversion (``rpc.contract.to_payload`` + JSON), on the analytic stand-in site model of
``test_inference_graph_fit.py`` so a run takes seconds. The run on the real MalE site tables is
``test_inference_cli.py`` (a subprocess of ``csc quest analyse``).
"""

from __future__ import annotations

import csv
import json
import time

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.core import runs, tasks
from chisurf.plugins.quenching_estimator.core.inference import columns, site_model
from chisurf.plugins.quenching_estimator.core.inference import graph_fit as gf
from chisurf.plugins.quenching_estimator.rpc import RemoteError, local_client, to_payload
from chisurf.plugins.quenching_estimator.rpc.contract import _manifest

from .test_inference_graph_fit import FakeLibrary

#: A run of stage B that takes a second on the stand-in model.
TINY = dict(n_starts=2, search_maxiter=4, joint_max_nfev=2)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Stand-in site models, a private run root and a fresh job manager per test."""
    monkeypatch.setattr(site_model, "SiteLibrary", lambda **kwargs: FakeLibrary())
    monkeypatch.setenv(runs.QUEST_RUNS_DIR_ENV, str(tmp_path / "runs"))
    monkeypatch.setattr(tasks, "_DEFAULT", tasks.JobManager())
    monkeypatch.setattr(api, "_CLIENT", None)


def _wire(value):
    """What a remote caller receives: the transport's payload, through JSON."""
    return json.loads(json.dumps(to_payload(value)))


def _schema(name, key):
    (method,) = [m for m in _manifest()["rpc_methods"] if m["name"] == name]
    return method[key]


def _validate(instance, schema):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(instance, schema)


def test_the_template_is_the_declaration():
    template = api.analysis_template()
    assert template["order"] == ["A", "B", "naive_h2o", "C", "summary"]
    assert [s["name"] for s in template["stages"]] == template["order"]
    assert template["presets"]["quick"]["n_starts"] == 8 and template["presets"]["full"] == {}
    assert template["fit_settings"] == gf.settings()
    assert {"fit_estimates", "fit_predictions"} <= set(template["result_tables"])
    _validate(_wire(template), _schema("quest.analysis.template", "result_schema"))


def test_a_run_writes_the_declared_tables_and_a_run_record(tmp_path):
    reply = api.analyse("B", preset="quick", fit_overrides=TINY, workers=1, profile=False)
    result = reply["result"]
    assert reply["status"] == "completed" and reply["run_id"] == reply["job_id"]
    # native in process: record arrays, not lists
    assert isinstance(result.stages["B"].tables["estimates"], np.ndarray)
    folder = runs.runs_directory() / reply["run_id"]
    assert reply["directory"] == str(folder)
    record = json.loads((folder / runs.RUN_FILE).read_text())
    assert record["kind"] == runs.ANALYSIS_KIND and record["stages"] == ["B"]
    assert set(record["tables"]) == set(result.tables())
    # every CSV carries exactly the declared columns of its table
    with open(folder / "B.estimates.csv", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == [c["column"] for c in columns.columns("fit_estimates", gf.RESULT_COLUMNS)]
    assert {"B.predictions.csv", "summary.json", "report.md", "run.json"} <= set(reply["files"])
    # the run is listed and readable like any other run
    listed = runs.list_runs()["runs"]
    assert listed[0]["job_id"] == reply["run_id"] and listed[0]["kind"] == "analysis"
    assert runs.read_run_table(reply["run_id"], "B.estimates") == folder / "B.estimates.csv"


def test_the_rpc_round_trip_returns_the_in_process_estimates():
    native = api.analyse("B", preset="quick", fit_overrides=TINY, workers=1, profile=False,
                         save_outputs=False)
    client = local_client()
    envelope = client.call("quest.analysis.run", dict(
        stages=["B"], preset="quick", fit_overrides=TINY, workers=1, profile=False,
        save_outputs=False))
    assert envelope["ok"], envelope
    wire = _wire(envelope["result"])
    _validate(wire, _schema("quest.analysis.run", "result_schema"))
    assert wire["directory"] is None and wire["files"] == []
    remote = wire["result"]["stages"]["B"]
    local = native["result"].stages["B"].tables["estimates"]
    assert [r["parameter"] for r in remote["tables"]["estimates"]] == list(local["parameter"])
    np.testing.assert_allclose([r["value"] for r in remote["tables"]["estimates"]],
                               local["value"], rtol=1e-12)
    assert "parity:Atto655 in D2O" in remote["plots"] and remote["text"]
    # the finished job answers quest.analysis.result from memory, with the same numbers
    again = _wire(client.result("quest.analysis.result", {"job_id": wire["job_id"]}))
    assert again["result"]["stages"]["B"]["tables"] == remote["tables"]


def test_a_stored_run_is_read_back_from_disk(tmp_path):
    reply = api.analyse("B", preset="quick", fit_overrides=TINY, workers=1, profile=False,
                        project_dir=tmp_path)
    tasks._DEFAULT = tasks.JobManager()  # a new server: the job is no longer in memory
    stored = api.analysis_result(reply["job_id"], project_dir=tmp_path)
    assert stored["status"] == "completed" and stored["directory"] == reply["directory"]
    table = stored["result"]["stages"]["B"]["tables"]["estimates"]
    assert [r["parameter"] for r in table] == list(
        reply["result"].stages["B"].tables["estimates"]["parameter"])
    assert stored["result"]["run"]["kind"] == "analysis"


def test_a_continued_job_reuses_the_solved_graph():
    first = api.analyse("B", preset="quick", fit_overrides=TINY, workers=1, profile=False,
                        save_outputs=False)
    second = api.analyse("naive_h2o", continue_from=first["job_id"], save_outputs=False)
    assert second["result"].graphs["heavy_water"] is first["result"].graphs["heavy_water"]
    assert list(second["result"].stages) == ["B", "naive_h2o"]


def test_a_background_job_reports_progress_and_can_be_cancelled():
    started = api.analyse("A", preset="quick", workers=1, profile=False, save_outputs=False,
                          fit_overrides=dict(n_starts=64, search_maxiter=200), background=True)
    job_id = started["job_id"]
    assert started["background"] and started["status"] in ("queued", "running")
    assert job_id in [j["job_id"] for j in api.client().result("quest.jobs.list")["jobs"]]
    deadline = time.monotonic() + 60
    while api.job(job_id)["progress"] == 0 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert api.job(job_id)["progress"] > 0, "no progress reported"
    with pytest.raises(RemoteError) as running:
        api.analysis_result(job_id)
    assert running.value.error_code in ("job_not_finished",)
    assert api.cancel_job(job_id)
    tasks.default_manager().wait(job_id, timeout=120)
    assert api.job(job_id)["status"] == "cancelled"
    with pytest.raises(RemoteError) as cancelled:
        api.analysis_result(job_id)
    assert cancelled.value.error_code == "operation_cancelled"


@pytest.mark.parametrize("params, needle", [
    (dict(stages=["Z"]), "Unknown stage"),
    (dict(preset="slow"), "Unknown fit preset"),
    (dict(fit_overrides={"no_such": 1}), "Undeclared fit setting"),
    (dict(data="/no/such/folder"), "not found"),
    (dict(continue_from="00000000-0000-0000-0000-000000000000"), "No finished analysis job"),
])
def test_malformed_inputs_fail_before_any_work(params, needle):
    with pytest.raises(RemoteError) as err:
        api.client().result("quest.analysis.run", params)
    assert err.value.error_code == "invalid_analysis" and needle in str(err.value)
    assert api.client().result("quest.jobs.list")["jobs"] == []


def test_the_site_table_summary(monkeypatch, tmp_path):
    from chisurf.plugins.quenching_estimator.core.inference import site_table as st

    seen = {}

    def fake_site_table(structure, site, linker_length, chain=None, settings_=None,
                        cache_dir=None):
        seen.update(structure=structure, site=site, linker_length=linker_length)
        n_types = len(st.residue_types(settings_))
        return st.SiteTable(neighbours=np.ones((4, n_types), np.int8),
                            contacts=np.zeros((4, 1, 1, 2), np.float16),
                            exposure=np.array([0.1, 0.2, 0.3, 0.4], np.float32),
                            meta={"dg": 0.5}, path=tmp_path / "t.npz")

    monkeypatch.setattr(st, "site_table", fake_site_table)
    summary = _wire(api.site_table("APO", 72, dye="Atto655"))
    _validate(summary, _schema("quest.analysis.site_table", "result_schema"))
    assert seen["linker_length"] == 20.12 and seen["structure"].endswith("1OMP.cif")
    assert summary["n_voxels"] == 4 and summary["neighbour_totals"][0] == 4
    assert summary["exposure"]["mean"] == pytest.approx(0.25)
    with pytest.raises(RemoteError) as err:
        api.site_table("APO", 72)
    assert err.value.error_code == "invalid_analysis"
