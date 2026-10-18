"""A burst step does not redo work whose inputs and settings are unchanged.

The workflow shell asks each step to run on every *Next*, and hands a panel its
burst folder again on every visit — which the panel reads as "a setting changed,
recompute". Walking back through the steps therefore recomputed BVA, 2CDE, the
H2MM scan over byte-identical inputs, which on a real
burst folder is minutes each time.

These drive the decision, not the computation: each test replaces the expensive
call with a counter, so what is pinned is *whether* a step decides to compute —
the part that was wrong — rather than what it computes.
"""

from __future__ import annotations

import os

import pytest



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


def _count_submits(monkeypatch, controller):
    """Replace the controller's worker submission with a counter (what is pinned is the decision to compute)."""
    calls: list = []

    def submit(fn, *args, **kwargs):
        calls.append(1)
        return None

    monkeypatch.setattr(controller._executor, "submit", submit)
    return calls


def _came_back(controller, fingerprint):
    """As if the run had returned a result: not running, a result in memory, remembered by the cache."""
    controller.model.is_running = False
    controller.model.is_locked = False
    controller._future = None
    controller.model.df = object()
    controller._cache.remember(fingerprint)


# ── BVA ──────────────────────────────────────────────────────────────


@pytest.fixture
def bva(burst_folder):
    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    app = create_app()
    app.model.auto_update = False
    app.model.set_folder(burst_folder)
    yield app
    app.close()


def test_bva_skips_a_run_that_would_reproduce_its_own_plot(bva, monkeypatch):
    ctl = bva.controller
    started = _count_submits(monkeypatch, ctl)

    ctl.run(write_output=False)
    assert len(started) == 1, "the first run must compute"
    _came_back(ctl, ctl._fingerprint)

    ctl.run(write_output=False)
    assert len(started) == 1, "an identical request must not recompute"

    ctl.run(write_output=False, force=True)
    assert len(started) == 2, "force must recompute"


def test_bva_recomputes_when_a_setting_changes(bva, monkeypatch):
    ctl = bva.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.run(write_output=False)
    _came_back(ctl, ctl._fingerprint)

    bva.model.photons_per_slice += 5
    ctl.run(write_output=False)
    assert len(started) == 2, "a changed setting must recompute"


def test_bva_recomputes_when_a_burst_file_changes(bva, burst_folder, monkeypatch):
    ctl = bva.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.run(write_output=False)
    _came_back(ctl, ctl._fingerprint)

    (burst_folder / "bi4_bur" / "m002.bur").write_text("First File\n\nm002.spc\n")
    ctl.run(write_output=False)
    assert len(started) == 2, "another burst file is different input"


def test_bva_writes_when_the_previous_run_only_previewed(bva, monkeypatch):
    """A preview satisfies a preview, never a Run: the BV4 files are not there."""
    ctl = bva.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.run(write_output=False)
    _came_back(ctl, ctl._fingerprint)

    ctl.run(write_output=True)
    assert len(started) == 2, "the outputs still have to be written"


# ── 2CDE ─────────────────────────────────────────────────────────────


@pytest.fixture
def two_cde(burst_folder):
    from chisurf.plugins.burst.burst_2cde.gui.app import create_app

    app = create_app()
    app.model.set_folder(burst_folder)
    yield app
    app.close()


def test_2cde_skips_only_when_its_companion_files_are_current(two_cde, burst_folder, monkeypatch):
    from chisurf.core.runtime import analysis_cache

    ctl = two_cde.controller
    started = _count_submits(monkeypatch, ctl)

    ctl.run()
    assert len(started) == 1
    _came_back(ctl, ctl._fingerprint)

    # A result in memory is not enough -- the 2c4 companions must exist for this
    # fingerprint, else a downstream reader would find nothing.
    ctl.run()
    assert len(started) == 2, "no stamp on disk means the companions are not there"
    _came_back(ctl, ctl._fingerprint)

    out = burst_folder / "Info"
    out.mkdir(exist_ok=True)
    companion = burst_folder / "m000.2c4"
    companion.write_text("x")
    analysis_cache.write_stamp(
        out / "2cde.stamp.json",
        two_cde.model.analysis_fingerprint(),
        outputs=[companion],
        tool="2cde",
    )
    ctl.run()
    assert len(started) == 2, "with results on disk and nothing changed, do not recompute"

    two_cde.model.tau_us = two_cde.model.tau_us * 2
    ctl.run()
    assert len(started) == 3, "a changed tau must recompute"


def test_2cde_computes_when_the_step_is_opened(two_cde, monkeypatch):
    """Landing on the step shows the result, not an empty plot and a button."""
    ctl = two_cde.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.auto_run()
    assert len(started) == 1, "being shown with a folder must start the computation"


def test_2cde_does_not_start_a_second_run_on_top_of_a_running_one(two_cde, monkeypatch):
    ctl = two_cde.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.run()
    ctl.auto_run()
    assert len(started) == 1, "a run in flight must not be doubled by arriving"


def test_2cde_stop_cancels_and_leaves_nothing_to_reuse(two_cde, monkeypatch):
    ctl = two_cde.controller
    _count_submits(monkeypatch, ctl)
    ctl.run()
    ctl._future = object()  # the run is in flight
    assert two_cde.model.is_running, "Stop is offered while the run is going"

    ctl._cache.remember(ctl._fingerprint)
    ctl.stop()
    assert ctl._cancel.is_set(), "Stop must reach the running task"
    assert not ctl._cache.matches(two_cde.model.analysis_fingerprint()), (
        "a stopped run computed part of an answer, not an answer"
    )


# ── the shared fingerprint, as the tools use it ──────────────────────


def test_every_step_fingerprints_its_own_inputs(bva, two_cde, burst_folder):
    """Two steps reading the same folder must not share a fingerprint.

    They are told apart by ``extra``; without it, one step's stamp would answer
    for another's outputs.
    """
    assert (
        bva.model.analysis_fingerprint(bva.model.bva_settings())
        != two_cde.model.analysis_fingerprint()
    )


# ── burst search (step 2) ────────────────────────────────────────────


def test_burst_search_is_not_repeated_for_an_identical_request(tmp_path):
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

    assert cache.matches(analysis_cache.fingerprint([raw], request, extra="burst_selection")), (
        "the same files and the same settings are the same search"
    )

    changed = dict(request, settings={"min_photons": 30})
    assert not cache.matches(analysis_cache.fingerprint([raw], changed, extra="burst_selection")), (
        "a changed burst-search setting must search again"
    )

    raw.write_bytes(b"different photons")
    assert not cache.matches(analysis_cache.fingerprint([raw], request, extra="burst_selection")), (
        "re-recorded data must search again"
    )


def test_a_stopped_2cde_run_does_not_start_itself_again(two_cde, monkeypatch):
    ctl = two_cde.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.auto_run()
    assert len(started) == 1

    ctl._future = object()
    ctl.stop()
    ctl._future = None
    two_cde.model.is_running = False
    ctl.auto_run()
    assert len(started) == 1, "revisiting must not restart what was stopped"

    # Asking explicitly overrides the stop -- that is what Run means.
    ctl.run()
    assert len(started) == 2


def test_restart_runs_what_the_gate_would_have_skipped(two_cde, burst_folder, monkeypatch):
    """The override has to be reachable from the controller, not only from the cache."""
    from chisurf.core.runtime import analysis_cache

    ctl = two_cde.controller
    started = _count_submits(monkeypatch, ctl)
    ctl.run()
    _came_back(ctl, ctl._fingerprint)
    out = burst_folder / "Info"
    out.mkdir(exist_ok=True)
    companion = burst_folder / "m000.2c4"
    companion.write_text("x")
    analysis_cache.write_stamp(
        out / "2cde.stamp.json",
        two_cde.model.analysis_fingerprint(),
        outputs=[companion],
        tool="2cde",
    )

    ctl.run()
    assert len(started) == 1, "unchanged: skipped"
    assert two_cde.model.restart_attention is True, (
        "the button is drawn attention to exactly when it is the thing you want"
    )

    ctl.restart()
    assert len(started) == 2, "Recompute must run what the gate skipped"


def test_a_changed_lut_recomputes_every_photon_reading_step(two_cde):
    """The LUT is ambient, so nothing in the panel's settings mentions it."""
    np = pytest.importorskip("numpy")
    from chisurf.core.fio import lut_context

    lut_context.clear_active_setup_lut()
    before = two_cde.model.analysis_fingerprint()
    try:
        lut_context.set_active_setup_lut(
            channel_luts={0: np.arange(16)}, channel_shifts={}, apply_lut=True
        )
        assert two_cde.model.analysis_fingerprint() != before, (
            "linearising the micro-times changes what 2CDE computes"
        )
    finally:
        lut_context.clear_active_setup_lut()
    assert two_cde.model.analysis_fingerprint() == before, "and switching back is the old state"


def test_h2mm_fits_the_same_answer_twice(burst_folder):
    """A reported state count is only reproducible if its seed travels with it."""
    from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel

    model = H2mmViewModel()
    model.data_folder = str(burst_folder)
    assert model.build_settings().seed == model.seed
    first = model.analysis_fingerprint(model.build_settings())
    model.seed += 1
    assert model.analysis_fingerprint(model.build_settings()) != first, (
        "a different seed is a different sample, not a cache hit"
    )
