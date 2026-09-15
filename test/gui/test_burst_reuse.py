"""A burst step does not redo work whose inputs and settings are unchanged.

The workflow shell asks each step to run on every *Next*, and hands a panel its
burst folder again on every visit — which the panel reads as "a setting changed,
recompute". Walking back through the steps therefore recomputed BVA, 2CDE, the
burst MLE export and the H2MM scan over byte-identical inputs, which on a real
burst folder is minutes each time.

These drive the decision, not the computation: each test replaces the expensive
call with a counter, so what is pinned is *whether* a step decides to compute —
the part that was wrong — rather than what it computes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")


@pytest.fixture
def burst_folder(tmp_path):
    """A minimal burst-analysis folder: what every step reads."""
    bur = tmp_path / "bi4_bur"
    bur.mkdir()
    for i in range(2):
        (bur / f"m00{i}.bur").write_text("First File\tNumber of Photons\n\nm000.spc\t42\n")
    return tmp_path


def _runs(monkeypatch, module_or_obj, name="run", returns=None):
    """Replace a call with a counter and return the counter list."""
    calls: list = []

    def _record(*_args, **_kwargs):
        calls.append(1)
        return returns

    monkeypatch.setattr(module_or_obj, name, _record)
    return calls


class _RunningTask:
    """A task that is still going, as ``ChiSurfProgress.run`` returns one."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def is_running(self) -> bool:
        return not self.cancelled


def _drain_timers(ms: int = 20) -> None:
    """Let deferred (singleShot) work run — that is how arrival starts a run."""
    from qtpy import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    deadline = QtCore.QTime.currentTime().addMSecs(ms)
    while QtCore.QTime.currentTime() < deadline:
        app.processEvents(QtCore.QEventLoop.AllEvents, 5)


# ── BVA ──────────────────────────────────────────────────────────────


@pytest.fixture
def bva(qapp, burst_folder):
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    tool = BVATool(embedded=True)
    tool.data_folder = burst_folder
    tool.analysis_folder = burst_folder
    yield tool
    tool.close()


def test_bva_skips_a_run_that_would_reproduce_its_own_plot(bva, monkeypatch):
    import pandas as pd

    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")

    bva._start_analysis(write_output=False)
    assert len(started) == 1, "the first run must compute"

    # Pretend that run finished and produced a plot.
    bva._df = pd.DataFrame({"Proximity Ratio Std": [0.1]})
    bva._result_cache.remember(bva._running_fingerprint)

    bva._start_analysis(write_output=False)
    assert len(started) == 1, "an identical request must not recompute"

    bva._start_analysis(write_output=False, force=True)
    assert len(started) == 2, "force must recompute"


def test_bva_recomputes_when_a_setting_changes(bva, monkeypatch):
    import pandas as pd

    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")
    bva._start_analysis(write_output=False)
    bva._df = pd.DataFrame({"Proximity Ratio Std": [0.1]})
    bva._result_cache.remember(bva._running_fingerprint)

    bva.le_photons_per_slice.setText(str(int(bva.le_photons_per_slice.text() or 10) + 5))
    bva._start_analysis(write_output=False)
    assert len(started) == 2, "a changed setting must recompute"


def test_bva_recomputes_when_a_burst_file_changes(bva, burst_folder, monkeypatch):
    import pandas as pd

    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")
    bva._start_analysis(write_output=False)
    bva._df = pd.DataFrame({"Proximity Ratio Std": [0.1]})
    bva._result_cache.remember(bva._running_fingerprint)

    (burst_folder / "bi4_bur" / "m002.bur").write_text("First File\n\nm002.spc\n")
    bva._start_analysis(write_output=False)
    assert len(started) == 2, "another burst file is different input"


def test_bva_writes_when_the_previous_run_only_previewed(bva, monkeypatch):
    """A preview satisfies a preview, never a Run: the BV4 files are not there."""
    import pandas as pd

    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")
    bva._start_analysis(write_output=False)
    bva._df = pd.DataFrame({"Proximity Ratio Std": [0.1]})
    bva._result_cache.remember(bva._running_fingerprint)

    bva._start_analysis(write_output=True)
    assert len(started) == 2, "the outputs still have to be written"


# ── 2CDE ─────────────────────────────────────────────────────────────


@pytest.fixture
def two_cde(qapp, burst_folder):
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool

    tool = BurstTwoCdeTool(embedded=True)
    tool.set_folder(burst_folder)
    yield tool
    tool.close()


def test_2cde_skips_only_when_its_companion_files_are_current(
    two_cde, burst_folder, monkeypatch
):
    from chisurf.core.runtime import analysis_cache
    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")

    two_cde.run()
    assert len(started) == 1

    # As if that run had come back.
    two_cde._df = object()
    two_cde._result_cache.remember(two_cde._running_fingerprint)

    # A result in memory is not enough — the 2c4 companions must exist for this
    # fingerprint, else a downstream reader would find nothing.
    two_cde.run()
    assert len(started) == 2, "no stamp on disk means the companions are not there"
    two_cde._df = object()
    two_cde._result_cache.remember(two_cde._running_fingerprint)

    out = burst_folder / "2c4"
    out.mkdir(exist_ok=True)
    (out / "m000.2c4").write_text("x")
    analysis_cache.write_stamp(
        out / "2cde.stamp.json", two_cde.analysis_fingerprint(),
        outputs=[out / "m000.2c4"], tool="2cde",
    )
    two_cde.run()
    assert len(started) == 2, "with results on disk and nothing changed, do not recompute"

    two_cde._tau.setValue(two_cde._tau.value() * 2)
    two_cde.run()
    assert len(started) == 3, "a changed tau must recompute"


def test_2cde_computes_when_the_step_is_opened(two_cde, monkeypatch):
    """Landing on the step shows the result, not an empty plot and a button."""
    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")
    two_cde.show()
    _drain_timers()
    assert len(started) == 1, "being shown with a folder must start the computation"


def test_2cde_does_not_start_a_second_run_on_top_of_a_running_one(two_cde, monkeypatch):
    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run", returns=_RunningTask())
    two_cde.run()
    two_cde.show()
    _drain_timers()
    assert len(started) == 1, "a run in flight must not be doubled by arriving"


def test_2cde_stop_cancels_and_leaves_nothing_to_reuse(two_cde, monkeypatch):
    from chisurf.gui.progress import ChiSurfProgress

    task = _RunningTask()
    _runs(monkeypatch, ChiSurfProgress, "run", returns=task)
    two_cde.run()
    assert two_cde._stop.isEnabled(), "Stop is offered while the run is going"

    two_cde._df = object()
    two_cde._result_cache.remember(two_cde._running_fingerprint)
    two_cde.stop()
    assert task.cancelled, "Stop must reach the running task"
    assert not two_cde._result_cache.matches(two_cde.analysis_fingerprint()), (
        "a stopped run computed part of an answer, not an answer"
    )


# ── H2MM ─────────────────────────────────────────────────────────────


def test_h2mm_skips_a_refit_of_the_displayed_model(qapp, burst_folder, monkeypatch):
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        tool._set_folder(str(burst_folder))
        started = _runs(monkeypatch, ChiSurfProgress, "run")

        tool._run_analysis()
        assert len(started) == 1

        tool._result = object()  # as if that fit had come back
        tool._result_cache.remember(tool._running_fingerprint)
        tool._run_analysis()
        assert len(started) == 1, "an identical fit request must not refit"

        tool.sb_max_states.setValue(tool.sb_max_states.value() + 1)
        tool._run_analysis()
        assert len(started) == 2, "a wider state scan is a different fit"
    finally:
        tool.close()


# ── the shared fingerprint, as the tools use it ──────────────────────


def test_every_step_fingerprints_its_own_inputs(bva, two_cde, burst_folder):
    """Two steps reading the same folder must not share a fingerprint.

    They are told apart by ``extra``; without it, one step's stamp would answer
    for another's outputs.
    """
    assert bva.analysis_fingerprint(bva._get_bva_settings()) != two_cde.analysis_fingerprint()


# ── MLE batch export ─────────────────────────────────────────────────


def test_mle_export_is_skipped_when_the_files_on_disk_are_current(
    qapp, burst_folder, monkeypatch
):
    """The batch's product is the b{g,r,y}4 files, so current files are the answer.

    This one is deliberately disk-based rather than in-memory: the wizard keeps
    no batch result in memory, and a fresh session that still has the exported
    fits must not refit every burst to end up writing the same numbers.
    """
    from chisurf.core.runtime import analysis_cache
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    wizard = MLELifetimeAnalysisWizard()
    try:
        bur = burst_folder / "bi4_bur" / "m000.bur"
        # The stamp sits beside the selected burst files, so the selection is
        # what has to be stubbed — the fingerprint's input list is wider than it.
        monkeypatch.setattr(
            wizard.burst_files_list, "get_selected_files", lambda: [str(bur)]
        )
        # Enough state to get past the "no data" guard.
        wizard.df_bursts = object()
        wizard.tttrs = {"m000": object()}

        saved = _runs(monkeypatch, wizard, "_save_burst_results_fast")

        out = burst_folder / "bg4" / "m000.bg4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("fit results")
        analysis_cache.write_stamp(
            wizard.batch_stamp_path(), wizard.batch_fingerprint(),
            outputs=[out], tool="burst_mle",
        )

        wizard.process_bursts()
        assert saved == [], "current exports must not be refitted"
        assert "Unchanged" in wizard.statusBar().currentMessage()

        # A changed threshold is a different fit, so the gate must open again.
        wizard.min_photons = float(wizard.min_photons) + 5
        assert not analysis_cache.is_current(
            wizard.batch_stamp_path(), wizard.batch_fingerprint()
        ), "a changed setting must invalidate the exported fits"
    finally:
        wizard.close()


# ── burst search (step 2) ────────────────────────────────────────────


def test_burst_search_is_not_repeated_for_an_identical_request(qapp, tmp_path):
    """The longest step in the workflow, asked for again with nothing changed."""
    from chisurf.core.runtime import analysis_cache

    # The gate is the decision, and it is worth pinning on its own: building the
    # whole selection tool here would test the wizard, not the rule.
    raw = tmp_path / "m000.spc"
    raw.write_bytes(b"photons")
    request = {"settings": {"min_photons": 20}, "filetype": "SPC-130"}

    cache = analysis_cache.ResultCache()
    first = analysis_cache.fingerprint([raw], request, extra="burst_selection")
    cache.remember(first)

    assert cache.matches(
        analysis_cache.fingerprint([raw], request, extra="burst_selection")
    ), "the same files and the same settings are the same search"

    changed = dict(request, settings={"min_photons": 30})
    assert not cache.matches(
        analysis_cache.fingerprint([raw], changed, extra="burst_selection")
    ), "a changed burst-search setting must search again"

    raw.write_bytes(b"different photons")
    assert not cache.matches(
        analysis_cache.fingerprint([raw], request, extra="burst_selection")
    ), "re-recorded data must search again"


def test_h2mm_fits_when_the_step_is_opened_and_can_be_stopped(
    qapp, burst_folder, monkeypatch
):
    """Arriving starts the fit; Stop reaches it.

    An H2MM scan with restarts runs for minutes, so a fit that starts on its own
    is only reasonable if stopping it is one click away — and a stopped scan must
    not be remembered as the answer for these settings.
    """
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        tool._set_folder(str(burst_folder))
        task = _RunningTask()
        started = _runs(monkeypatch, ChiSurfProgress, "run", returns=task)

        assert not tool.btn_stop.isEnabled(), "nothing to stop before a fit"
        tool.show()
        _drain_timers()
        assert len(started) == 1, "being shown with a folder must start the fit"
        assert tool.btn_stop.isEnabled(), "Stop is offered while the fit runs"
        assert not tool.btn_run.isEnabled(), "Run is not offered twice over"

        tool.show()
        _drain_timers()
        assert len(started) == 1, "a fit in flight must not be doubled by arriving"

        tool._result = object()
        tool._result_cache.remember(tool._running_fingerprint)
        tool.stop()
        assert task.cancelled, "Stop must reach the running fit"
        assert not tool._result_cache.matches(
            tool.analysis_fingerprint(tool._gather_settings())
        ), "a stopped scan is not the answer for these settings"

        tool._on_fit_done()
        assert tool.btn_run.isEnabled() and not tool.btn_stop.isEnabled()
    finally:
        tool.close()


def test_a_stopped_h2mm_fit_does_not_start_itself_again(
    qapp, burst_folder, monkeypatch
):
    """Stop has to outlast the visit that started the fit.

    Each step computes on arrival, so without this a fit the user deliberately
    abandoned came straight back on the next *Next* — Stop only postponed
    minutes of work rather than cancelling it.
    """
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        tool._set_folder(str(burst_folder))
        started = _runs(monkeypatch, ChiSurfProgress, "run", returns=_RunningTask())
        tool.show()
        _drain_timers()
        assert len(started) == 1

        tool.stop()
        tool._on_fit_done()

        tool.hide()
        tool.show()
        _drain_timers()
        assert len(started) == 1, "revisiting must not restart what was stopped"

        # Changing the fit is a different request, and is not suppressed.
        tool.sb_max_states.setValue(tool.sb_max_states.value() + 1)
        tool.hide()
        tool.show()
        _drain_timers()
        assert len(started) == 2, "a different fit was never the one stopped"
    finally:
        tool.close()


def test_a_stopped_2cde_run_does_not_start_itself_again(
    two_cde, monkeypatch
):
    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run", returns=_RunningTask())
    two_cde.show()
    _drain_timers()
    assert len(started) == 1

    two_cde.stop()
    two_cde._analysis_over()
    two_cde.hide()
    two_cde.show()
    _drain_timers()
    assert len(started) == 1, "revisiting must not restart what was stopped"

    # Asking explicitly overrides the stop — that is what Run means.
    two_cde._on_run_clicked()
    assert len(started) == 2


def test_restart_runs_what_the_gate_would_have_skipped(two_cde, monkeypatch):
    """The override has to be reachable from the panel, not only from Python."""
    from chisurf.core.runtime import analysis_cache
    from chisurf.gui.progress import ChiSurfProgress

    started = _runs(monkeypatch, ChiSurfProgress, "run")
    folder = pathlib_path(two_cde)
    two_cde.run()
    two_cde._df = object()
    two_cde._result_cache.remember(two_cde._running_fingerprint)
    out = folder / "2c4"
    out.mkdir(exist_ok=True)
    (out / "m000.2c4").write_text("x")
    analysis_cache.write_stamp(
        out / "2cde.stamp.json", two_cde.analysis_fingerprint(),
        outputs=[out / "m000.2c4"], tool="2cde",
    )

    two_cde.run()
    assert len(started) == 1, "unchanged: skipped"
    assert two_cde._restart.property("attention") is True, (
        "the button is drawn attention to exactly when it is the thing you want"
    )

    two_cde._restart.click()
    assert len(started) == 2, "Recompute must run what the gate skipped"


def pathlib_path(tool):
    """The folder a 2CDE panel is pointed at."""
    import pathlib

    return pathlib.Path(tool._folder_edit.text().strip())


def test_a_changed_lut_recomputes_every_photon_reading_step(two_cde):
    """The LUT is ambient, so nothing in the panel's settings mentions it."""
    np = pytest.importorskip("numpy")
    from chisurf.core.fio import lut_context

    lut_context.clear_active_setup_lut()
    before = two_cde.analysis_fingerprint()
    try:
        lut_context.set_active_setup_lut(
            channel_luts={0: np.arange(16)}, channel_shifts={}, apply_lut=True
        )
        assert two_cde.analysis_fingerprint() != before, (
            "linearising the micro-times changes what 2CDE computes"
        )
    finally:
        lut_context.clear_active_setup_lut()
    assert two_cde.analysis_fingerprint() == before, "and switching back is the old state"


def test_a_corrected_estimator_does_not_inherit_the_old_exports(
    qapp, burst_folder, monkeypatch
):
    """MLE is the only gate that survives a restart — and the only one that could
    hand back another version's numbers without saying so."""
    from chisurf.core.runtime import analysis_cache
    from chisurf.plugins.burst.burst_mle_analysis import wizard as wizard_mod

    wizard = wizard_mod.MLELifetimeAnalysisWizard()
    try:
        bur = burst_folder / "bi4_bur" / "m000.bur"
        monkeypatch.setattr(
            wizard.burst_files_list, "get_selected_files", lambda: [str(bur)]
        )
        wizard.df_bursts = object()
        wizard.tttrs = {"m000": object()}
        saved = _runs(monkeypatch, wizard, "_save_burst_results_fast")

        out = burst_folder / "bg4" / "m000.bg4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("fit results")
        analysis_cache.write_stamp(
            wizard.batch_stamp_path(), wizard.batch_fingerprint(),
            outputs=[out], tool="burst_mle",
        )
        wizard.process_bursts()
        assert saved == [], "current exports are not refitted"

        # The estimator is corrected; the burst files and settings are untouched.
        # Relative to whatever the shipped version is: pinning a literal here
        # made this a no-op the day the estimator was bumped to that number,
        # and the test then asserted that nothing had changed.
        monkeypatch.setattr(
            wizard_mod, "ALGORITHM_VERSION", wizard_mod.ALGORITHM_VERSION + 1
        )
        assert not analysis_cache.is_current(
            wizard.batch_stamp_path(), wizard.batch_fingerprint()
        ), "results from the previous estimator are not current"
    finally:
        wizard.close()


def test_h2mm_fits_the_same_answer_twice(qapp, burst_folder):
    """A reported state count is only reproducible if its seed travels with it."""
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        tool._set_folder(str(burst_folder))
        assert tool._gather_settings().seed == tool.sb_seed.value()
        first = tool.analysis_fingerprint(tool._gather_settings())
        tool.sb_seed.setValue(tool.sb_seed.value() + 1)
        assert tool.analysis_fingerprint(tool._gather_settings()) != first, (
            "a different seed is a different sample, not a cache hit"
        )
    finally:
        tool.close()


def test_h2mm_does_not_refit_when_arriving_at_a_finished_step(
    qapp, burst_folder, monkeypatch
):
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        tool._set_folder(str(burst_folder))
        started = _runs(monkeypatch, ChiSurfProgress, "run")
        tool.show()
        _drain_timers()
        assert len(started) == 1

        tool._result = object()  # as if the fit had come back
        tool._result_cache.remember(tool._running_fingerprint)
        tool._on_fit_done()

        tool.hide()
        tool.show()
        _drain_timers()
        assert len(started) == 1, "coming back to a fitted step must not refit"
    finally:
        tool.close()
