---
type: PRD
prd: "98"
title: "PRD-98: Acquisition is a stream, not an array — acq on tttrlib's streaming decode, consumers, and sink"
description: The acq plugin already decodes BH records with tttrlib's carried-state decoder, then throws the streaming away — every photon is concatenated into one growing array, correlation re-runs the batch correlator on the full history every 5 chunks, the MCS trace recomputes all bins to show the last second, PicoQuant still decodes through a hand-rolled numpy bit-twiddler, and _save_data() is pass. tttrlib now ships a verified streaming family (StreamingCorrelator exact vs batch Wahl, StreamingDecayHistogram exact vs bincount) and PRD-034 is bringing a native .pto sink; acq becomes push-based end to end — one decode path, O(chunk) updates, bounded RAM, and a file that exists before the run ends.
status: proposed
resource: /Users/tpeulen/dev/chisurf/chisurf/plugins/core/acq
tags: [prd, chisurf, acq, tttrlib, streaming, correlator, tcspc, pto]
timestamp: '2026-08-11T00:00:00Z'
---

# PRD-98: Acquisition is a stream, not an array — acq on tttrlib's streaming decode, consumers, and sink

## What exists (measured 2026-08-11)

The single-molecule acquisition plugin (`chisurf/plugins/core/acq`) drives
BH SPC 830/150/160/180, PicoQuant (snAPI), Brickmic and a tttrlib-simulated
device through one seam — `TCSPCDeviceABC.read_fifo(max_words)` returns raw
`uint32` words — and then processes them as if streaming had not been
invented:

1. **Decoding is half-migrated.** `_decode_bh_spc_records`
   (`gui/tool.py:66`) wraps `tttrlib.decode_records` with the carried
   `DecodeState` — the overflow counter crosses chunk boundaries exactly as
   PRD-021 designed — and the manager override (`tool.py:2821`) routes
   `BH_SPC` and `SIMULATION` through it. But the **base**
   `_process_photons` (`tool.py:1104`) is still a hand-rolled numpy
   bit-field decoder ("bits 31,28 markers; 16-27 microtimes; 8-15
   channels"), and **PicoQuant falls through to it**. Two decoders, one
   correct by construction, one correct by hope.
2. **Every photon is kept, twice over.** `_accumulate` does
   `np.concatenate` of all macro times, micro times and channels on every
   chunk — O(N²) copying over a run, unbounded RAM. The plugin's README
   feature list includes "RAM usage monitoring": the symptom has a widget.
3. **Correlation is batch, re-run on the full history.** Every 5 chunks
   (`_correlation_interval`), `_compute_tttrlib_correlation` feeds the
   *entire* accumulated macro-time array to the batch `Correlator` for up
   to 4 channel pairs. Cost per refresh grows linearly with elapsed run
   time; over a run it is O(N²). A 30-minute measurement updates its
   correlation display more slowly than a 1-minute one, forever worsening.
4. **The MCS trace computes everything to show a slice.**
   `_calculate_mcs_trace` (`tool.py:1417`) calls
   `tttrlib.compute_intensity_trace` on *all* macro times each update, then
   displays only the last `rollaround_time_ms` worth of bins.
5. **Decays are incremental, but hand-rolled** — per-chunk
   `np.histogram(..., bins=4096)` added into an accumulator (`tool.py:455`,
   `1269`), fixed bin count, no per-channel weighting.
6. **`_save_data()` is `pass`** (`tool.py:2881`). "Data is acquired into
   RAM and saved at the end" (module docstring) is aspirational: nothing is
   saved unless the BH device object drips raw `.spc` words via
   `spc_output_path`. A crash, or an operator who forgot the checkbox,
   loses the run. There is no self-contained, analyzable output file at
   all — no header, no clock, no channel map travels with the words.
7. **The pipeline exists twice.** `DataProcessingThread` (`tool.py:223`)
   and the manager's own `_process_photons` / `_accumulate_flat_photons` /
   `_update_decay_data` / `_calculate_mcs_trace` (`tool.py:1104–1493`)
   implement the same decode→accumulate→histogram→correlate loop in
   parallel, drifting independently.

## What tttrlib now offers

The streaming family shipped and was **verified against the batch
implementations** on 2026-08-10 (tttrlib PRD-033):

- `StreamingCorrelator` — `push_photon(mt, w, channel)` /
  `push_photons(...)`, `flush()`, `get_x_axis()`,
  `get_correlation_normalized()`. Agreement with the batch Wahl correlator
  is **1.0000 on every cascade**, chunked-vs-whole equality is a test.
- `StreamingDecayHistogram` — `push_photons(microtimes, channels)`,
  per-channel histograms, **exact** vs `np.bincount` and
  `TTTR.get_microtime_histogram`.
- `StreamingPhasor` (1e-12 vs `DecayPhasor`; it lives inside
  `StreamingDecayHistogram.h`, not a header of its own),
  `StreamingBurstDetector` (fixed; matches the batch sliding-window
  search), `StreamingCLSMImage`.
- `decode_records` + carried `DecodeState` (PRD-021) decodes **any
  fixed-width container** in pieces — PicoQuant record types included.

**The MCS class exists and is unreachable, which is worse than missing.**
`StreamingIntensityTrace` was written on 2026-08-11
(`modules/streaming/include/StreamingIntensityTrace.h`), is documented in
the module README, is listed in the module's `CMakeLists.txt`, and has a
test file — but `hasattr(tttrlib, "StreamingIntensityTrace")` is `False`,
because `Streaming.i` exists **twice** and the module's copy is shadowed by
a stale `ext/python/Streaming.i` that SWIG finds first. The shadowing also
withholds the `push_np` numpy typemaps, so every streaming class still
crosses the language boundary one photon at a time at 1.13 µs each — on a
100 kHz acquisition, half a core — and `push_np(macro_times, weights)`
raises `TypeError` outright. Filed in tttrlib's `BUGS.md`
("Two `Streaming.i` files"). This is a blocker for requirement 2, not a
gap to design around.

And the *upcoming* piece this PRD is named for: **tttrlib PRD-034** makes
`.pto` a native TTTR sink — a normative 4-column photons table plus header
tags (clocks, channels, provenance) written through the container's
already-specified over-wide-VINT streaming, `tttr pto add` appending one
measurement per object.

## Requirements

1. **One decode path.** Every device's raw words go through
   `tttrlib.decode_records` with the device's record type and a carried
   state. The hand-rolled bit-field decoder in the base
   `_process_photons` is **deleted**, not kept as a fallback — PicoQuant
   and Brickmic move onto the library decoder like BH did.
2. **Live analyses are push-based streaming consumers.** Per chunk:
   `StreamingDecayHistogram.push_photons` replaces the numpy histogram;
   one `StreamingCorrelator` per configured channel pair (pair channels
   mapped to 0/1) replaces the every-5-chunks full-history batch re-run;
   the MCS trace appends per-chunk bin counts instead of recomputing all
   bins. Nothing downstream of decode ever touches "all photons so far".
   The MCS delegates to `StreamingIntensityTrace`, whose `set_max_bins(m)`
   keeps only the newest `m` bins (O(1) in run length) while
   `first_bin_index()` keeps the retained window's place on the absolute
   time axis — which is exactly the rolling display the plugin fakes today
   by binning every photon of the run to show its tail. The class is
   written but **unreachable from every binding** until the duplicate
   `Streaming.i` is resolved (tttrlib `BUGS.md`); acq cannot start
   requirement 2 before that lands, and must not hand-roll a per-chunk
   binner in the meantime — carrying a partial trailing bin across chunk
   boundaries is precisely the state that ends up implemented twice and
   correct once, which is what this PRD exists to stop.
   `StreamingBurstDetector` (live burst rate as a QC number) and
   `StreamingPhasor` are offered where the decay window already is —
   they cost one push loop that is running anyway.
3. **The sink is a `.pto`, written during acquisition.** When tttrlib
   PRD-034 lands, each run streams its decoded photons into a native
   photons object as they arrive — clocks and channel map as header tags,
   acquisition metadata (device, settings snapshot) as free tags. The
   file exists and grows during the measurement; `_save_data`'s `pass`
   dies. Until PRD-034 lands, the raw `.spc` drip remains the stopgap and
   this requirement is the tracked dependency. Raw vendor words stay
   available as a device-level option, unchanged — the native table is
   the decoded stream, per PRD-034's own fidelity rule.
4. **RAM is bounded.** With consumers streaming and the sink
   write-through, the growing `_absolute_macrotimes` concatenation is
   removed. What remains in memory is display state: rolling windows,
   histogram accumulators, correlator levels — all O(1) in run length.
   The RAM monitor becomes a diagnostic, not a survival instrument.
5. **One pipeline.** `DataProcessingThread` and the manager duplicate
   collapse into a single push-based pipeline: device → decode →
   [sink, consumers] — every device, GUI or standalone, feeds the same
   object.

## Acceptance criteria

1. **Streaming equals batch, on a real run**: after a recorded
   acquisition, `get_correlation_normalized()` from the live correlator
   equals the batch `Correlator` run over the saved photon stream (per
   pair), and the live decay equals `np.bincount` of the saved micro
   times — asserted in a chisurf test, not inherited from tttrlib's.
2. **Update cost is flat**: on a simulated acquisition, the per-chunk
   processing time at minute 30 equals minute 1 (no growth with run
   length), and process RSS is bounded — no term linear in total photons.
3. **The file survives the crash**: `SIGKILL` mid-acquisition; the `.pto`
   opens, photons up to the **last checkpoint** read back with
   `PtoRowCount` agreeing, header tags intact, the uncommitted tail
   invisible. Not "up to the last chunk" — the container's rule is that
   bytes past the `Segment` end are an abandoned write, so the guarantee
   is exactly as strong as the checkpoint interval acq chooses (one
   second is a few hundred bytes of seek-and-write). Gated on tttrlib
   PRD-034's checkpoint operation, which this PRD's requirement 3 is the
   reason for.
4. **Round trip**: the saved `.pto` opens as a `TTTR`; batch analysis of
   it reproduces the live displays.
5. **One decoder**: no numpy bit-shift decoding remains under
   `plugins/core/acq`; a PicoQuant-format record buffer decodes through
   `decode_records` in the tests.

## Non-goals

- **New device support** — the device list and `read_fifo` seam are
  unchanged.
- **GUI redesign** — windows, plots and controls stay; only what feeds
  them changes.
- **Batch analysis tools** — offline correlators, decay fitting, burst
  pipelines are untouched; this PRD is the live path only.

## Dependencies

- tttrlib PRD-021 (record streams) — **done**, partially adopted.
- tttrlib PRD-033 (streaming consumers) — **done, verified 2026-08-10**,
  but **not reachable as built**: the duplicate `Streaming.i` withholds
  `StreamingIntensityTrace` and the `push_np` typemaps from every binding
  (tttrlib `BUGS.md`, 2026-08-11). Requirement 2 is blocked on that one
  deletion.
- tttrlib PRD-034 (`.pto` native TTTR sink) — **proposed**; requirement 3
  and acceptance 3–4 land with it. Its *Writing a file that is still being
  measured* section (the checkpoint operation) was added because of this
  PRD: the write-once sink 034 originally described would have lost an
  entire run to a crash, since a streamed-but-uncommitted `FileData` lies
  outside the `Segment` and is by definition not part of the file.
