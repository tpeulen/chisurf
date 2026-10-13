"""The Pipelines panel of the native MMFDB Admin (ported from the Qt ``PipelinesView`` tests).

List the registered pipelines and, on a row click, show the pipeline's nodes, typed wiring
and recorded runs -- through the emtk Driver over a seeded temporary MMFDB.
"""

from __future__ import annotations

from chisurf.core.pipeline import (
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PipelineRun,
    record_pipeline_run,
    save_pipeline,
)
from chisurf.plugins.emtk_test_input import Driver

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    database,
    driver,
    open_panel,
    seeded_template,
)


def _demo_pipeline() -> Pipeline:
    return Pipeline(
        name="raw->shift->burst",
        nodes=(
            PipelineNode("shift", "microtime_shift", {"global_shift": 5}),
            PipelineNode("burst", "burst_selection", {}),
        ),
        edges=(PipelineEdge("shift", "shifted", "burst", "raw"),),
    )


def test_view_lists_pipelines(driver, app, database):  # noqa: F811
    save_pipeline(database, _demo_pipeline())
    panel = open_panel(driver, "pipelines", "Pipelines")
    assert {p["name"] for p in panel.pipelines} == {"raw->shift->burst"}
    assert driver.drawn("raw->shift->burst")


def test_view_shows_structure_and_runs_on_select(driver, app, database):  # noqa: F811
    pid = save_pipeline(database, _demo_pipeline())
    run = PipelineRun(
        pipeline_name="raw->shift->burst",
        node_outputs={"shift": ["a1"], "burst": ["a2"]},
        operation_ids=["op-1", "op-2"],
    )
    record_pipeline_run(database, run, pipeline_id=pid, status="succeeded", name="run-1")
    panel = open_panel(driver, "pipelines", "Pipelines")
    driver.click(Driver.text_rect(driver.draw(2), "raw->shift->burst", last=False))
    assert {n["name"] for n in panel.nodes} == {"shift", "burst"}
    # one wiring edge: shift.shifted -> burst.raw
    assert [(e["from"], e["to"]) for e in panel.edges] == [("shift.shifted", "burst.raw")]
    # one recorded run with two operations
    assert len(panel.runs) == 1
    assert panel.runs[0]["status"] == "succeeded"
    assert str(panel.runs[0]["operation_count"]) == "2"
    assert driver.drawn("burst.raw")
