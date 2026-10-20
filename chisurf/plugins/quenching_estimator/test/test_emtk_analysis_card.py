"""The Analysis page of the QuEst window, driven the way a person does, on temporary settings.

The page builds Qt-free beside the forward model, every control carries a tooltip, **Load example** reads the
shipped MalE measurements (titrations, lifetimes and kQ show before any fit), **Run** runs every stage in the
background without blocking the frame and fills the result tabs, **Cancel** stops a run, every table is headed by
its declared columns, and every step of the page's tour points at a control the page draws.

The run uses the analytic stand-in site model of ``test_inference_graph_fit`` (seconds, no site tables); the real
MalE numbers are ``test_male_reproduction.py``'s.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, hermetic_env

GUIDE = Path(__file__).resolve().parents[1] / "gui" / "analysis_guide.json"
FAST = dict(
    n_starts=2,
    search_maxiter=4,
    joint_max_nfev=2,
    profile_likelihood=dict(points=3, span_sd=1.0, max_nfev=2),
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


@pytest.fixture
def app():
    from chisurf.plugins.quenching_estimator.gui.analysis_card import AnalysisModel
    from chisurf.plugins.quenching_estimator.gui.app import make_app
    from chisurf.plugins.quenching_estimator.test.test_inference_graph_fit import FakeLibrary

    window = make_app()
    model = AnalysisModel(library=FakeLibrary(), fit_overrides=FAST)
    model.workers = 1
    card = window.analysis
    card.model = model
    model.used_hook, model.wake = card.used, card.request_frame
    yield window
    window.close()


class Ui(Driver):
    """The driver, finding controls on whichever page is shown."""

    def rect(self, name: str) -> tuple:
        self.draw(1)
        card = self.app.analysis
        found = (
            card.form.rects.get(name) or card.item_rects.get(name) or self.app.item_rects.get(name)
        )
        assert found, f"{name!r} was not drawn: {sorted(card.item_rects)[:60]}"
        return tuple(found)


def _open(app, size=(1280, 820)) -> Ui:
    ui = Ui(app, size)
    ui.draw(3)
    ui.click("tab_Analysis")
    assert app.page == "analysis"
    ui.draw(2)
    return ui


def _settle(ui: Ui, timeout: float = 120.0) -> None:
    model = ui.app.analysis.model
    end = time.monotonic() + timeout
    while model.busy and time.monotonic() < end:
        time.sleep(0.02)
        ui.draw(1)
    assert not model.busy, model.progress_text()
    ui.draw(2)


def test_the_page_switch_shows_the_analysis_and_back(app):
    ui = Ui(app, (1280, 820))
    ui.draw(3)
    assert "Simulate" in ui.strings()
    ui.click("tab_Analysis")
    text = " | ".join(ui.strings())
    assert "Run" in text and "Load example" in text and "Simulate" not in text
    ui.click("tab_Forward model")
    assert app.page == "forward" and "Simulate" in ui.strings()


@pytest.mark.parametrize("size", [(1280, 820), (800, 600)])
def test_the_page_draws_at_default_and_narrow_sizes(app, size):
    ui = _open(app, size)
    for name in (
        "load_example",
        "choose_folder",
        "run_analysis",
        "cancel_analysis",
        "write_results",
        "preset",
        "results.data",
        "results.summary",
    ):
        ui.rect(name)


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import emtk_inventory

    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    inventory = emtk_inventory(app)
    assert inventory["controls_without_tooltip"] == []


def test_load_example_shows_the_measurements_before_any_fit(app):
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    model = app.analysis.model
    assert Path(model.data_folder).name == "male" and model.preset == "quick"
    assert len(model.tables.site_lifetimes.rows()) == 64
    assert len(model.tables.k_posterior.rows()) == 17
    assert len(model.tables.kq_contact.rows()) == 15
    assert model.stern_volmer() and model.water_rows()
    for plot in ("stern_volmer", "hyper_posterior", "water_bars"):
        ui.rect(plot)
    assert not any("No titrations yet" in s for s in ui.strings())


def test_a_folder_without_the_tables_is_refused_with_the_reason(app, tmp_path):
    model = app.analysis.model
    assert model.open_folder(str(tmp_path)) is False
    assert model.status_error and "tcspc_fit_results.csv" in model.status


def test_tables_are_headed_by_their_declared_columns(app):
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    model = app.analysis.model
    for name in ("k_posterior", "site_lifetimes", "free_dye_lifetimes", "kq_contact"):
        view = getattr(model.tables, name)
        keys = [c["key"] for c in view.columns()]
        assert keys == list(view.rows()[0]), name
        assert all(c["description"] for c in view.columns()), name


def test_run_by_clicks_fills_every_tab_without_blocking_the_frame(app):
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    ui.click("run_analysis")
    model = app.analysis.model
    assert model.busy == "run"
    started = time.monotonic()
    ui.draw(1)  # a frame while the worker runs returns at once
    assert time.monotonic() - started < 5.0
    _settle(ui)
    assert not model.status_error, model.status
    assert list(model.result_stages()) == ["A", "B", "naive_h2o", "C", "summary"]
    assert model.progress_fraction == 1.0
    assert len(model.tables.site_tables.rows()) == len(model.site_keys()) > 0

    ui.click("results.fit")
    assert model.fit_stage_options() == ["A", "B", "naive_h2o", "C"]
    assert model.view_stage == "A" and model.view_block == "AF488 in H2O"
    assert len(model.tables.estimates.rows()) > 5 and len(model.tables.predictions.rows()) == 18
    for plot in ("parity", "forest", "loo", "profile", "k_graph"):
        ui.reveal(plot)
    model.view_stage = "C"
    model.stage_changed()
    assert model.view_block == "Atto655 in D2O and H2O"
    assert {r["solvent"] for r in model.tables.predictions.rows()} == {"D2O", "H2O"}

    ui.click("results.water")
    assert len(model.tables.water_access.rows()) == 18 and len(model.tables.exposure.rows()) == 2
    for plot in ("water_access", "exposure", "scale_compare"):
        ui.reveal(plot)
    ui.click("results.summary")
    assert len(model.tables.dye_summary.rows()) == 3
    for plot in ("summary_scale", "summary_stickiness"):
        ui.reveal(plot)
    assert "Plot failed" not in " ".join(ui.strings())


def test_write_results_writes_the_declared_tables(app, tmp_path):
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    ui.click("run_analysis")
    _settle(ui)
    written = app.analysis.model.write_to(str(tmp_path / "out"))
    assert (tmp_path / "out" / "A.estimates.csv") in written
    assert (tmp_path / "out" / "report.md").is_file()


def test_cancel_stops_the_run_and_keeps_the_page_usable(app):
    from chisurf.plugins.quenching_estimator.gui.analysis_card import AnalysisModel
    from chisurf.plugins.quenching_estimator.test.test_inference_graph_fit import FakeLibrary

    slow = AnalysisModel(
        library=FakeLibrary(), fit_overrides=dict(FAST, n_starts=40, search_maxiter=40)
    )
    slow.workers = 1
    app.analysis.model = slow
    slow.used_hook, slow.wake = app.analysis.used, app.analysis.request_frame
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    ui.click("run_analysis")
    ui.click("cancel_analysis")
    _settle(ui)
    assert "Cancelled" in slow.status
    assert slow.enabled("run_analysis")


def test_every_tour_step_points_at_a_control_the_page_draws(app):
    ui = _open(app)
    ui.click("load_example")
    _settle(ui)
    ui.click("run_analysis")
    _settle(ui)
    card = app.analysis
    steps = json.loads(GUIDE.read_text(encoding="utf-8"))["steps"]
    assert card.tour.steps and steps[1]["target"] == {"name": "load_example"}
    unresolved = []
    for step in steps:
        key = card.tour._target_key(step.get("target"))
        if not key:
            continue
        if key.startswith("results."):
            ui.click(key)
        try:
            ui.reveal(key)
        except AssertionError:
            unresolved.append(step["title"])
    assert unresolved == []
    assert all("await" not in s or s["target"] for s in steps)


def test_the_guide_follows_the_scheme():
    from chisurf.core.dataspec.schema import validate_guide

    assert validate_guide(json.loads(GUIDE.read_text(encoding="utf-8"))) == []


def test_settings_survive_a_restart(app):
    app.analysis.model.preset = "full"
    app.show_page("analysis")
    saved = json.loads(json.dumps(app.export_settings()))
    from chisurf.plugins.quenching_estimator.gui.app import make_app

    again = make_app()
    try:
        again.restore_settings(saved)
        assert again.page == "analysis" and again.analysis.model.preset == "full"
    finally:
        again.close()


def test_a_site_table_row_reads_the_site_model_arrays(app):
    """The row of a real site model (numpy ``count``, ``table.exposure``/``neighbours``), not only the stand-in's."""
    import types

    import numpy as np

    table = types.SimpleNamespace(
        exposure=np.array([0.2, 0.4, 1.3]), neighbours=np.ones((3, 4), np.int8)
    )
    site = types.SimpleNamespace(table=table, count=np.array([2.0, 1.0]), n_positions=3)
    model = app.analysis.model
    model.site_models = {("AF488", "APO", 72, 20.4): site}
    (row,) = model.site_table_rows()
    assert (row["positions"], row["distinct"], row["neighbours"]) == (3, 2, 4.0)
    assert row["exposure"] == pytest.approx((0.2 + 0.4 + 1.0) / 3)
    model.select_site_table(row)
    assert len(model.selected_site_exposure()) == 3
