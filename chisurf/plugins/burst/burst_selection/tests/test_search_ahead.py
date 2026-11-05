"""The pipeline's Burst Selection searches ahead and shows the visible window above its plots.

* A search of the current settings runs in the background as soon as files, setup and settings are
  known; it writes nothing. Next with the same settings only writes its bursts (no second search),
  and no blur covers the window meanwhile.
* A change of a setting drops the search of the old settings and searches again.
* The display range (start, length, bin) sits above the plots, in Simple mode too, and no longer in
  Filter settings.

On copies of the in-repository BH SPC-132 photons (two small files).
"""

from __future__ import annotations

import threading
import time

import pytest

from chisurf.plugins.emtk_test_input import Driver

from .test_emtk_native_app import SETUP, files  # noqa: F401  (fixture)

# --- the search ahead on its own --------------------------------------------------------------------- #


class _Client:
    """Stands in for the backend: counts searches, can hold one until released."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.gate = threading.Event()
        self.gate.set()

    def analyze_files(self, paths, progress_callback=None, **request):
        self.calls.append(request)
        for i, path in enumerate(paths):
            self.gate.wait(5.0)
            if progress_callback is not None:
                progress_callback(i + 1, len(paths), str(path))
        return {"dataframes": {str(p): [] for p in paths},
                "metadata": {"n_files": len(paths), "n_bursts": len(self.calls)}}


def test_a_wanted_search_starts_once_the_settings_are_still_and_is_kept():
    from chisurf.plugins.burst.burst_selection.gui.speculative import SpeculativeSearch

    client = _Client()
    spec = SpeculativeSearch(client, delay_s=10.0)
    spec.want("a", ["f1"], {"x": 1}, now=0.0)
    assert not spec.tick(now=5.0) and spec.pending  # still settling
    assert spec.tick(now=10.0) and spec.wait(5.0)
    assert spec.result_for("a")["metadata"]["n_bursts"] == 1
    assert spec.result_for("b") is None
    spec.want("a", ["f1"], {"x": 1}, now=11.0)  # the same settings again: nothing searched
    assert not spec.tick(now=100.0) and len(client.calls) == 1
    line, fraction = spec.status()
    assert "Searched ahead: 1 bursts" in line and fraction == 1.0


def test_a_changed_setting_drops_the_old_search_and_searches_again():
    from chisurf.plugins.burst.burst_selection.gui.speculative import SpeculativeSearch

    client = _Client()
    client.gate.clear()  # the first search stays inside its first file
    spec = SpeculativeSearch(client, delay_s=0.0)
    spec.want("old", ["f1", "f2"], {"x": 1})
    spec.tick()
    assert spec.running and spec.has("old")
    spec.want("new", ["f1", "f2"], {"x": 2})
    assert spec.tick() and spec.has("new") and not spec.has("old")
    client.gate.set()
    assert spec.wait(5.0)
    assert spec.result_for("new") is not None and spec.result_for("old") is None
    assert [c["x"] for c in client.calls] == [1, 2]


# --- the app in the pipeline -------------------------------------------------------------------------- #


@pytest.fixture
def step(files):  # noqa: F811
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    window = create_app(restore=False, pipeline=True)
    window.apply_setup(SETUP, "probe")
    window.set_advanced(False)
    window.use_files(files)
    yield window
    window.close()


def _until(drv, predicate, timeout=120.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        drv.draw(1)
        time.sleep(0.05)
    assert predicate(), "timed out"


def test_next_writes_the_bursts_searched_ahead_without_searching_again(step, monkeypatch):
    from chisurf.emtk.busy_overlay import busy_state

    m = step.model
    drv = Driver(step, (1200, 800))
    step.prefetch()
    spec = step.speculation
    assert spec.running or spec.pending or spec.done, "the search ahead did not start"
    assert busy_state(step) is None  # no blur over the window while it searches
    _until(drv, lambda: spec.done)
    key = m.search_key()
    ahead = spec.result_for(key)
    assert ahead is not None and ahead["metadata"]["n_bursts"] == 198
    assert not ahead.get("output_paths"), "the search ahead wrote something"

    def no_search(*_args, **_kwargs):
        raise AssertionError("Next searched again although the search ahead matched")

    monkeypatch.setattr(m.client, "analyze_files", no_search)
    assert step.run_step() is not False
    _until(drv, lambda: not step.running)
    assert not step.job.error, step.job.error
    assert m.n_bursts == 198 and m.has_processed
    by_file = m.result["output_paths_by_file"]
    assert all(".pto/" in by_file[str(p)]["output_folder"] for p in m.files)
    drv.draw(3)
    assert step._stored_key == m.search_key() and not spec.pending  # not searched ahead again


def test_next_while_the_search_ahead_runs_waits_for_it(step):
    m = step.model
    drv = Driver(step, (1200, 800))
    step.prefetch()
    assert step.run() is True
    assert step.running  # the hub's Next waits while the search ahead runs
    _until(drv, lambda: not step.running)
    assert not step.job.error, step.job.error
    assert m.n_bursts == 198


def test_a_setting_changed_after_the_search_ahead_searches_again(step):
    m = step.model
    drv = Driver(step, (1200, 800))
    step.prefetch()
    _until(drv, lambda: step.speculation.done)
    first = m.search_key()
    m.min_photons = 80
    m.settings_changed()
    step._speculate(delay_s=0.0)
    assert m.search_key() != first and step.speculation.has(m.search_key())
    _until(drv, lambda: step.speculation.done)
    assert step.speculation.result_for(m.search_key())["metadata"]["n_bursts"] < 198


def test_the_display_range_is_above_the_plots_in_simple_mode(step):
    drv = Driver(step, (1200, 800))
    drv.draw(3)
    assert not any(n.startswith("window_") for n in step.form.rects)  # not in Filter settings any more
    for tab in ("Count rate", "Inter-photon time", "Micro-time decay"):
        drv.click_text(tab)
        drv.draw(2)
        drawn = {name.split(".")[0] for name in step.display_form.rects}
        assert {"window_start_s", "window_length_s"} <= drawn, (tab, sorted(drawn))
    drv.click_text("Count rate")
    drv.draw(2)
    assert "trace_bin_ms" in step.display_form.rects
