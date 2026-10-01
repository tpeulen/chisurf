# trace_browser, card T3a: Qt-free trace binner

Written and finished by the reviewer. The implementing agent (Sonnet) wrote `core/binning.py`, its tests and the
test-marker removal, then was cut off by an API rate limit before its deliberate-breakage check, the report and the
commits (the limit resets hours later); the reviewer verified the uncommitted work, ran the breakage check, fixed one lint
finding and made the commits.

## What changed

* **`core/binning.py` (new, Qt-free):** `bin_trace(tttr, time_window_s, detectors=None, channels=None, selected=None)
  -> (time_axis, counts, labels)`. Imports numpy, tttrlib (guarded) and the standard library only. Reproduces
  `IntensityTrace.process_ptu` / `_process_routing_channels` of the legacy engine with vectorised numpy and with the
  detector mapping or channel list passed **as arguments**: `clocks_per_bin = max(1, floor(window / macro_time_resolution))`,
  photon `t` falls in bin `t // clocks_per_bin`, each trace is as long as its own last photon, traces are zero-padded to the
  longest; a detector counts photons whose routing channel is in `chs` and (when given) whose micro time lies in one of the
  inclusive `micro_time_ranges`; channel traces are labelled `Ch<n>` (the legacy label, `intensity_trace` l.1655).
* **`core/trace.load_trace`:** calls `bin_trace` instead of `IntensityTrace` (cache helpers, signature, return structure and
  `TraceLoadResult` unchanged). `intensity_trace/__init__.py` (the legacy Qt tool) is untouched and keeps its own engine.
* **Tests:** new `test/test_binning_trace_browser.py` (reference numbers for both windows, channel-list call, empty/absent
  mapping fallback, photons outside every window and inclusive bounds, Qt-free subprocess proof that computes an *uncached*
  trace, speed bound); the `@needs_legacy_trace_engine` skip marker is removed from the **five** T0 tests, which now run
  hermetically without a saved setup (the worker-thread test now computes an uncached trace on the worker; it used to hang
  on the Qt widget).

## Equality with the legacy engine

Proof by the numbers recorded from the legacy engine on a temp copy of `BH_SPC132.spc` with the ALEX setup (they are in the
T0 tests): 10 ms: 6233 bins, per-detector sums [22443, 56257, 0], labels `["green","red","yellow"]`, last time 62.32, max
count 467; 1 ms: 62329 bins, last time 62.328. The reviewer re-ran the binner by hand: identical, 0.01 s for each window
(1.2-million-photon-class file). A hermetic side-by-side run of the legacy engine is not possible (it needs Qt and a real saved
setup), so the recorded numbers are the equality proof.

## Difference from the legacy engine (only where it failed)

The legacy no-detector fallback indexed a dict with `[0]` and raised `KeyError: 0` (and returned an empty trace for a
channel-only setup). Here an empty or absent mapping uses `channels`; with neither, every routing channel used in the file,
ascending. A detector without `chs` is skipped with a warning; a detector with no photon after gating gives an all-zero
column. Pinned by tests.

## Tests

```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
100 passed in 23.53s        (81 passed + 5 skipped before; 19 new binner tests, the five tests now run)
```

The real `~/.chisurf/flr/sample_management.db` is untouched by the run (mtime unchanged). Ruff clean on the touched files.

Deliberate breakage (reviewer; both restored, final run green): an off-by-one in the number of bins (`n_bins` without `+ 1`)
failed 9 tests; an exclusive upper micro-time bound (`< hi`) failed
`test_photons_outside_every_window_are_not_counted_and_bounds_are_inclusive`.

## Consequences for the Qt tool

The legacy Qt `TraceBrowser` computes uncached traces through the model, hence now through this binner: same numbers (above),
no Qt widget instantiated for binning, and the fallback no longer crashes. Its look and behaviour are otherwise unchanged.

## Open for T3b / T4

T3b draws the plot from `model.load_trace` (counts per series, time axis, labels; y range and bin window), the annotation box,
first-row selection and precompute on a job. T4 keeps the exports. Nothing here blocks them.
