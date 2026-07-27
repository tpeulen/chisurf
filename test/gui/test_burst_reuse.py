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
    from chisurf.core import analysis_cache
    from chisurf.plugins.burst.burst_2cde.core import computation as core

    # A result object, so the tool holds "a result" the way a real run leaves it.
    computed = _runs(monkeypatch, core, "compute_2cde", returns=object())
    monkeypatch.setattr(core, "read_burst_analysis", lambda *a, **k: (None, None))
    monkeypatch.setattr(two_cde, "_draw", lambda *a, **k: None)

    two_cde.run()
    assert len(computed) == 1

    # A result in memory is not enough — the 2c4 companions must exist for this
    # fingerprint, else a downstream reader would find nothing.
    two_cde._df = object()
    two_cde._result_cache.remember(two_cde.analysis_fingerprint())
    two_cde.run()
    assert len(computed) == 2, "no stamp on disk means the companions are not there"

    out = burst_folder / "2c4"
    out.mkdir(exist_ok=True)
    (out / "m000.2c4").write_text("x")
    analysis_cache.write_stamp(
        out / "2cde.stamp.json", two_cde.analysis_fingerprint(),
        outputs=[out / "m000.2c4"], tool="2cde",
    )
    two_cde.run()
    assert len(computed) == 2, "with results on disk and nothing changed, do not recompute"

    two_cde._tau.setValue(two_cde._tau.value() * 2)
    two_cde.run()
    assert len(computed) == 3, "a changed tau must recompute"


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
    from chisurf.core import analysis_cache
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    wizard = MLELifetimeAnalysisWizard()
    try:
        bur = burst_folder / "bi4_bur" / "m000.bur"
        monkeypatch.setattr(wizard, "batch_input_files", lambda: [bur])
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
    from chisurf.core import analysis_cache

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
