"""The ALEX Suite's own native step apps (card AS2 and the hub's step apps), operated with real input, no Qt."""

from __future__ import annotations

import numpy as np

from chisurf.plugins.emtk_test_input import Driver


def _table(path, e_true, n=150, seed=0):
    rng = np.random.default_rng(seed)
    total = rng.poisson(200, n).astype(float) + 20.0
    green = total * 0.5
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    cols = {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }
    lines = ["\t".join(cols)] + [
        "\t".join(f"{v:.10g}" for v in row) for row in np.column_stack(list(cols.values()))
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_titration_takes_burst_runs_from_the_workspace(tmp_path, monkeypatch):
    """The Input section lists the workspace's burst runs; a pick adds one row per run (no file
    chooser: data enters ChiSurf by the drop)."""
    from chisurf.core.project import analysis
    from chisurf.plugins.burst.alex_suite.gui.native import receive_titration
    from chisurf.plugins.burst.alex_suite.gui.step_apps import TitrationStepApp
    from test.gui.burst_workspace import burst_run_in_workspace, restore_workspace

    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setattr(analysis, "_SESSION", None)
    with restore_workspace():
        run = burst_run_in_workspace(tmp_path)
        app = TitrationStepApp()
        drv = Driver(app, (1200, 800))
        drv.draw(2)
        assert "add_files" not in app.item_rects and app.item_rects.get("workspace_input_rows")
        drv.click_text(run.name)  # pick the run (several may be picked) ...
        drv.click_text("Use selected")  # ... and hand them over
        assert [r["file"] for r in app.model.rows] == [run.address]
        receive_titration(app.step, {"files": [run.address]})  # already listed: not added twice
        assert len(app.model.rows) == 1
        drv.draw(2)


def test_titration_is_seeded_once_and_takes_the_corrections(tmp_path):
    from chisurf.plugins.burst.alex_suite.gui.step_apps import TitrationStep

    step = TitrationStep()
    step.set_burst_files([tmp_path / "a.bur"])
    step.model.rows[0]["concentration"] = 5.0
    step.set_burst_files([tmp_path / "b.bur"])
    assert [r["name"] for r in step.model.rows] == ["a.bur"], (
        "typed concentrations are never replaced"
    )
    step.set_corrections(gamma=0.9, beta=1.2)
    assert (step.model.gamma, step.model.beta) == (0.9, 1.2)


def test_titration_fit_and_export_on_a_series(tmp_path):
    from chisurf.plugins.burst.alex_suite.gui.step_apps import TitrationStep

    step = TitrationStep()
    paths = [_table(tmp_path / f"c{i}.bur", 0.25 if i < 2 else 0.65, seed=i) for i in range(4)]
    step.model.add_files([str(p) for p in paths])
    for i, c in enumerate((0.0, 10.0, 100.0, 1000.0)):
        step.model.update_series_cell(i, "concentration", c)
    step.model.run()
    written = step.export_csv(str(tmp_path / "titration.csv"))
    assert written is not None and written.is_file(), step.model.summary
    step.export_csv()
    assert step.dialog.open_now, "Export CSV without a path asks where (save mode)"


def test_alternation_step_app_polls_its_job(tmp_path, monkeypatch):
    from chisurf.plugins.burst.alex_suite import demo
    from chisurf.plugins.burst.alex_suite.gui.step_apps import AlternationStepApp

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    stream = demo.make_demo(tmp_path / "data")
    app = AlternationStepApp()
    drv = Driver(app, (1000, 700))
    drv.draw(2)
    app.model.set_files([stream])  # what the hub hands it from the Files step
    while app.running:
        drv.draw(1)
    drv.draw(2)  # the frame applies the finished job
    assert app.model.period == demo.PERIOD and app.model.converted
    assert app.item_rects.get("phase_plot")


def test_data_step_load_demo_button(tmp_path, monkeypatch):
    from chisurf.plugins.burst.alex_suite.gui.step_apps import AlexDataSelectionApp

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app = AlexDataSelectionApp()
    drv = Driver(app, (1200, 800))
    drv.draw(2)
    drv.click(app.item_rects["load_example"])
    assert [p.name for p in app.model.paths()] == ["alex_demo.spc"]
    drv.draw(2)
    assert app.item_rects.get("proceed")
