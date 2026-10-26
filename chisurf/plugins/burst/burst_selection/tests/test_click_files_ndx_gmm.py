"""Burst Selection: the workspace input, Clear, Refresh plots, Open in ndX and Fit GMM, pressed on the drawn controls.

Same input as ``test_emtk_native_app.py`` (two real BH SPC-132 files, 198 bursts); the outcomes are the file list, the
status line, the burst table, the opened path and the GMM rows the user reads.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import Driver

from .test_emtk_native_app import app, files, texts, wait  # noqa: F401


def feed(window, *paths) -> bool:
    """Hand photon files over as the workspace does (Input section / Open in… / a drag)."""
    from chisurf.plugins.burst.burst_selection.gui.native import receive_photons

    try:
        receive_photons(window, {"files": [str(p) for p in paths], "datasets": []})
    except ValueError:
        return False
    return True


def _run(drv, app, files):  # noqa: F811
    assert feed(drv.app, *files)
    drv.draw(2)
    drv.click_name("toolAction_run")
    wait(drv)
    assert app.model.n_bursts == 198, app.model.status_text


def test_photon_streams_come_from_the_workspace_and_their_runs_become_children(
    app,  # noqa: F811
    files,  # noqa: F811
    monkeypatch,
):
    """No Add files / Add folder / ndX-from-MMFDB buttons and no drop hook: the Input section lists
    the workspace's photon streams; a search's run is registered as a child of its stream."""
    from chisurf.core.api import dataset_container, dataset_objects
    from chisurf.core.plugin.workspace_input import register_result

    held = dataset_container()
    before = list(held)
    try:
        drv = Driver(app, (1200, 800))
        shown = texts(drv.draw(2))
        assert not {"Add files", "Add folder", "ndX from MMFDB"} & set(shown)
        assert not hasattr(app, "files_dropped") and not hasattr(app, "on_files_dropped")
        stream = register_result(str(files[0]), kind="photons")
        drv.draw(2)
        app.input.workspace_input_selection = [
            r for r in app.input.workspace_input_rows() if r["uid"] == stream.unique_identifier
        ]
        drv.click_name("workspace_input_use")
        assert [p.name for p in app.model.files] == ["m000.spc"]
        drv.click_name("toolAction_run")
        wait(drv)
        children = [
            d for d in dataset_objects() if getattr(d, "result_of", "") == stream.unique_identifier
        ]
        assert children and children[0].data_kind == "bursts", app.model.status_text
    finally:
        held[:] = before


def test_clear_removes_files_and_results_but_keeps_settings(app, files):  # noqa: F811
    drv = Driver(app, (1200, 800))
    _run(drv, app, files)
    app.model.min_photons = 37
    drv.click_name("toolAction_clear")
    drv.draw(2)
    assert app.model.files == [] and app.model.n_bursts == 0 and not app.model.has_processed
    assert app.model.display_frame is None and app.model.status_text.startswith("Cleared")
    assert app.model.min_photons == 37  # the settings stay
    shown = texts(drv.draw())
    assert "Cleared. Add TTTR files to begin." in shown and "No burst table yet" in shown
    # with nothing listed, Run is disabled and pressing it starts no search
    drv.click_name("toolAction_run")
    drv.draw(2)
    assert not app.job.busy and app.model.n_bursts == 0


def test_refresh_plots_recomputes_the_diagnostics(app, files):  # noqa: F811
    drv = Driver(app, (1200, 800))
    _run(drv, app, files)
    app._diag_due = 0.0
    drv.draw(2)
    assert app.model.diagnostic is not None
    app.model.diagnostic = None
    app._diag_due = None  # nothing pending: only the button can bring the plots back
    drv.draw(2)
    assert app.model.diagnostic is None
    drv.click_name("toolAction_refresh")
    drv.draw(3)
    assert app.model.diagnostic is not None


def test_open_in_ndx_sends_the_runs_output_folder(app, files, monkeypatch):  # noqa: F811
    from chisurf.plugins.ndxplorer import mmfdb_launcher

    opened = []
    monkeypatch.setattr(
        mmfdb_launcher, "open_path_in_ndxplorer", lambda path: opened.append(path) or object()
    )
    drv = Driver(app, (1200, 800))
    feed(drv.app, *files)
    drv.draw(2)
    drv.click_name("ndx_current")  # disabled before a run: nothing opens
    drv.draw(1)
    assert opened == []
    drv.click_name("toolAction_run")
    wait(drv)
    drv.click_name("ndx_current")
    drv.draw(2)
    assert len(opened) == 1 and app.model.output_path() == opened[0]
    from chisurf.core.fio.address import container_of

    # the run's address in its photon dataset's analysis container (no folder is written)
    assert container_of(opened[0]).is_file() and opened[0].endswith("#60")
    assert app.model.status_text == f"Opened {opened[0]} in ndX."
    assert "Opened" in texts(drv.draw())


def test_open_in_ndx_reports_a_window_that_could_not_open(app, files, monkeypatch):  # noqa: F811
    from chisurf.plugins.ndxplorer import mmfdb_launcher

    monkeypatch.setattr(mmfdb_launcher, "open_path_in_ndxplorer", lambda path: None)
    drv = Driver(app, (1200, 800))
    _run(drv, app, files)
    drv.click_name("ndx_current")
    drv.draw(2)
    assert app.model.status_text == "ndX could not be opened."


def test_fit_gmm_button_fits_the_requested_components(app, files):  # noqa: F811
    drv = Driver(app, (1200, 800))
    _run(drv, app, files)
    drv.click_text("Histogram")
    drv.draw(2)
    drv.type_into_name("gmm_components", "2")
    assert app.model.gmm_components == 2
    drv.click_name("fit_gmm")
    drv.draw(3)
    result = app.model.gmm_result
    assert result and result["n"] == 2 and len(result["components"]) == 2
    weights = [float(r["weight"]) for r in app.model.gmm_rows()]
    assert len(weights) == 2 and sum(weights) == pytest.approx(1.0, abs=0.01)
    assert np.all(np.isfinite(result["total"])) and result["total"].max() > 0
    shown = texts(drv.draw())
    assert "GMM" in shown and f"{weights[0]:.3f}" in shown
    # more components give more rows; 0 components with Auto switched off is refused with a message
    drv.type_into_name("gmm_components", "3")
    drv.click_name("fit_gmm")
    drv.draw(2)
    assert len(app.model.gmm_rows()) == 3
    app.model.gmm_auto_components = False
    drv.type_into_name("gmm_components", "0")
    drv.click_name("fit_gmm")
    drv.draw(2)
    assert (
        app.model.status_text == "GMM fitting skipped: not enough data points or zero components."
    )


def test_auto_components_choose_the_count_by_bic_and_settings_dialog_refits(app, files):  # noqa: F811
    drv = Driver(app, (1200, 800))
    _run(drv, app, files)
    drv.click_text("Histogram")
    drv.draw(2)
    app.model.gmm_auto_components = True
    drv.type_into_name("gmm_components", "0")
    drv.click_name("fit_gmm")
    drv.draw(2)
    auto = app.model.gmm_result["n"]
    assert 1 <= auto <= app.model.gmm_settings["max_components"]
    drv.click_name("gmm_settings")
    drv.draw(2)
    assert app.panel_dialog == "gmm"
    app.model.gmm_result = None
    drv.click_text("Fit GMM with these settings")
    drv.draw(2)
    assert app.model.gmm_result is not None and app.model.gmm_result["n"] == auto
