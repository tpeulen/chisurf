## The image section still draws with raw pyqtgraph, and can crash on teardown

**2026-09-17.** chiplot's default backend is emtk now, but
`chisurf/gui/autoform/sections/builtin.py::ImageMapWidget` (the `image` custom
section: 11 view specs -- colour/channel pickers, movie playback, brush
painting, point picks, rectangle gates) builds `pyqtgraph.ImageView`s directly
and never went through chiplot. With emtk drawing the tool's other plots, the
flc_2d plugin tests crash in about two of three runs (bus error in
`QGraphicsScene::itemsBoundingRect` under `processEvents`); with
`gc.disable()` 5/5 pass and under the pyqtgraph backend 5/5 pass, so it is a
cyclic-GC collection destroying part of the widget tree while its scene still
has events queued. The real fix is porting `ImageMapWidget` onto
`chiplot.ImageView` (PRD-104): emtk has the image, overlay, ROI, picking and
inverted-axis pieces; a z/frame slider and brush painting are what it would
need to gain.

## `_flr_fret_calibration_parameters.phi_donor` is uncommitted

**2026-09-08.** IHM-FLR defines `phi_acceptor` and no donor counterpart,
although γ = (gR·φ_A)/(gG·φ_D) needs both. The term was added to
`mmfdb_flr_ext.dic` (the central spot, per the rule) and **cannot be committed**:
that file carries another agent's in-flight rewrite — 1791 insertions, 981
deletions — so committing it would take their work.

**Consequence:** `accurate_fret/calibration_columns.yaml` references a term that
resolves only in *this* working tree. `test/core/test_analysis_feature_terms.py`
passes here and would fail on a checkout without the addition. Whoever lands
that dictionary rewrite should check `phi_donor` survives it; if their version
defines an equivalent, the declaration should point at theirs instead.

## The ALEX period spectrum runs at 2.6 samples per period

**Measured 2026-09-08.** `detect_alex_period` bins the signed donor−acceptor
stream and takes the peak of its power spectrum. `bin_width` is chosen to make
the FFT fit in `max_bins`, so it grows with the **length** of the measurement
while the period it is looking for is a fixed hardware setting. On the 159 s
analysed span of the cal1 file that is `bin_width = 3027` against a period of
`8000` — **2.64 samples per period**, a hair above Nyquist. A longer recording,
or a shorter alternation period, crosses it: the line aliases and the detector
returns a confident wrong number.

**Tried and reverted:** binning finely over a short leading slice instead
(`coarse_span = max_bins × min_period//16`, ~524 cycles). It fixes the sampling
and makes the FFT 16× cheaper, and it **returns 78400 for a period of 8000** —
the spectral line's power grows with the number of cycles seen, so over half a
thousand cycles it loses to low-frequency drift. The long span is doing real
work; do not shorten it without replacing what it provides.

**The shape of a real fix** is two passes: a short fine-binned window to get the
order of magnitude, then a second spectrum binned at `P0/8` over a long span —
properly sampled *and* many cycles, both FFTs small. Not done here because a
first pass that is off by 10× (as the reverted attempt was) would pick a
`bin_width` that aliases the second, so it needs its own guard rather than a
straight substitution.

Not urgent: the integer scan that follows is what sets the final answer, and it
is now measured over the full record (see the log entry for 2026-09-08), so the
FFT only has to land within 2 %.

## The background estimator's default tail window can fit an empty range

**Measured 2026-09-08** on `001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto`.
The tail fit took every bin above `tail_fraction × max(inter-photon time)` and had
**no upper edge**. With the shipped `tail_fraction = 0.8` that is 17.4–21.8 ms on
this measurement — the sparse far tail, where the red detector has no counts at
all:

| fit window | green | red |
|---|---|---|
| 17.4–21.8 ms (the old default) | 0.74 kHz | **0.00 kHz** |
| 1–6 ms (where the points are dense) | 2.24 kHz | 3.17 kHz |

A background of exactly zero is not obviously wrong on a plot, and every
corrected quantity downstream is a count *minus a background*, so it propagates
silently.

**Fixed by making the window explicit rather than derived**
(`fit_from_ms`/`fit_to_ms`, sliders coupled to a draggable band on the
inter-photon-time plot; `tail_range_ms` in
`chisurf.core.fluorescence.burst.background`). `tail_fraction` now only *seeds*
the window on the first estimate, and headless callers that never set a window
get exactly the old behaviour — **which means the defect is still reachable from
`csc burst-background` and the RPC service.** Fixing that properly means
choosing the window from the data (the last bin with more than `min_counts`
would do), and that changes numbers for every existing caller, so it was not
done here.

## `.pto` can compress its payloads; ChiSurf writes them raw

**Measured 2026-09-08.** The question was whether the container supports
transparent compression. **It does, and no ptolib change is needed:** the format
names a compressed payload by its encoding (`PtoEncoding "dstore+zstd"`,
`"json+brotli"`; codecs `zstd`, `brotli`, `lz4`, `deflate`), a reader that lacks
the codec must list the object and refuse to hand back its bytes as decoded, and
`PtoFile.add(kind, encoding, name, data)` already takes the encoding. The
installed build has a codec registered.

(Not to be confused with `tttrlib`'s `auto_compress_on_read`, which is *macro-time
keyframe* compression in memory — a different thing that is already on.)

What ChiSurf does not do is use it for the **embedded instrument file**, which is
where the bytes are. On a three-measurement ALEX container (11.7 M photons, three
`.sm` files embedded as one `.pto`):

| | size | time |
|---|---|---|
| as written | 82 MB | — |
| deflate level 1 | 53 MB (1.54x) | 1.2 s |
| zstd level 3 | 51 MB (1.60x) | 0.4 s |

Worth having, and not a drive-by, because of one line in the spec: **a compressed
payload is not mappable**. The photon stream is read by memory-mapping, so
compressing it trades 1.6x on disk for a full decode on every open — a call for
whoever owns the reader, not for a plugin. A large *table* is a different case:
it compresses inside its own `dstore` encoding, column by column, so the
directory still reads without decoding anything.

## Detector setups have two stores, and a picker sees only one of them

**Found 2026-09-08.** A detector setup can be written two ways and read two ways,
and the pairs do not line up:

| | writes to | reads from |
|---|---|---|
| `detector_setups.*` RPC (`DetectorSetupClient`) | the settings **JSON** (`chisurf.core.data_io.detector_setups`) | the same JSON |
| every `SetupSelector` picker in the GUI | — | `chisurf.gui.widgets.wizard.tttr_channeldefinition.load_detector_setups` |

The wizard loader reads **MMFDB** when MMFDB is in use, and in that branch it
never falls back to the JSON — the pickers pass `skip_migration=True`, so the
JSON is not imported either. A setup saved through the RPC store is therefore
invisible in every picker, permanently and silently.

Found because the ALEX Suite's alternation step publishes a setup through the
RPC store and then shows it in a `SetupSelector` beside it: the combo listed
nothing while the workflow, the burst search and Accurate FRET all had the setup
and were using it.

Worked around locally, not fixed: that one picker reads a **merge** of both
stores (`_merged_setups` in
`chisurf/plugins/burst/alex_suite/gui/alternation.py`), and the step writes to
both. Every other picker in the application still reads MMFDB only.

The real fix is a ruling on which store is authoritative, and it is not a
drive-by: `save_detector_setups` swallows an MMFDB failure (seen here as
`FOREIGN KEY constraint failed` in a scratch database with no user row) and
reports success, so a store that is silently rejecting writes looks like one
that is empty.

## A burst table's per-stream count *rates* are not proportional to its counts

**Found 2026-09-08.** `E` and `S` are ratios of photon counts. The `.bur` schema
writes each PIE window x detector stream as a **count rate**
(`S prompt green (kHz) | …`), and `_span_features`
(`chisurf/core/fio/fluorescence/burst.py`) computes that rate as

```
count_rate_khz = n_photons_in_the_stream / duration_of_that_stream's_own_span
```

— the span of the *selected* photons, not of the burst. So the four rates of one
burst have four different denominators, and their ratios are not the count
ratios. An `E` built on them carries a per-burst bias that no histogram looks
wrong for. The same holds for the whole-detector `Green Count Rate (KHz)` /
`Red Count Rate (KHz)`, from which `Proximity ratio` is defined.

Two more artefacts of the same definition: an empty stream is written as `-1`
(the `_SPAN_EMPTY` sentinel), and a one-photon stream as `NaN` (zero span).
Both propagate straight into a ratio.

**Half fixed.** `burst_features.yaml` now declares a photon-**count** column
beside every rate (`S {window} {detector} (photons) | {r0}-{r1}`), and
`chisurf.core.fluorescence.burst.table.guess_columns` prefers the counts, so
everything that maps channel roles through it (Accurate FRET, Burst Browser, the
ALEX Suite, the burst-table API) is now correct. Additive: nothing that reads
the kHz columns changed.

**Still wrong: ndX's shipped MFD equations.**
`modules/ndxplorer/ndxplorer/settings/mfd.equations.yaml` defines `Sg`, `Sr`,
`Sg(PIE)`, `Sr(PIE)` and `Sy(PIE)` on the kHz columns, so ndX's
`Proximity ratio`, `FRET efficiency` and `Stoichiometry (PIE)` still carry the
bias. Not changed here because it moves every existing ndX session's numbers,
and because a `.bur` written before today has no `(photons)` column to fall back
to — the equations need a fallback or the analysis needs re-running. Decide
deliberately; do not swap the column names in passing.

## Four burst tools silently reject a `.pto` burst analysis

**Found 2026-09-08.** A burst search over a `.pto` container keeps its results
**inside the measurement** and writes no folder at all: its output is a path like
`m000.pto/sliding_window_All 0.1500#60`, addressed like a folder but not one.
That is the *default* output of the burst pipeline.

Every tool that takes an "analysis folder" guards with `pathlib.Path(p).is_dir()`
and returns without a word when it is `False`, so handing one its own upstream
output leaves the panel reading "Select a data folder first" with the analysis
already made.

Fixed on the burst workflows' path: `burst_browser.load_folder`,
`burst_bva._set_folder` (and its drop handler), and
`chisurf.core.fluorescence.burst.table.read_burst_table`, which now reads a
container run.

Still silent, each one line plus a check that the reader behind it copes:

| tool | site |
|---|---|
| `burst_2cde` | `gui/tool.py:270`, `:299` |
| `burst_h2mm` | `gui/tool.py:852` |
| `burst_fcs_correlator` | `gui/tool.py:301` |
| `burst_fusion` | `gui/view_model.py:255` |

The predicate is `p.is_dir() or burst_tree.is_container_path(p)`.

## flc_2d cannot delegate to tttrlib yet: importing it segfaults the widget tests

**Found 2026-08-11.** A delegation of `plugins/fcs/flc_2d/core.py` to
`fdc_scan_axis` / `fdc_scan_two_axes` is **numerically exact** — all 13 recorded
fixture cases reproduce bit-for-bit — and still cannot land, because merely
bringing `tttrlib` into that plugin's process segfaults its Qt widget tests.

Measured on `pytest chisurf/plugins/fcs/flc_2d/test/`, 8 runs each arm:

| `core.py` | crashes |
|---|---:|
| HEAD (numba, no tttrlib import) | **0 / 8** |
| delegated, `import tttrlib` *inside* the functions | **3 / 8** |
| delegated, `import tttrlib` at module level | **8 / 8** |

The ladder is the finding: the more certainly `tttrlib` is loaded before the Qt
widgets are built, the more certainly the process dies. With
`test_widgets.py` excluded, the delegated version is **5 / 5 clean**, so nothing
is wrong with the numbers or the kernels.

The fault is `SIGSEGV` inside **pytest-qt's `_process_events`**, after the test's
assertions have passed — i.e. at Qt event processing, not in any computation.

**The likely culprit is the environment, not either library.** The process
carries 121 extension modules including PyQt5 *and* IMP, and IMP is loaded from
`/Users/tpeulen/dev/imp/cmake-build-arm64/lib` (via `imp-local-build.pth`) — a
local build made against the **`arm64-imp`** environment while the tests run in
`arm64`. One crash trace showed `pytestqt` itself resolving from
`arm64-imp/lib/python3.12/site-packages`. Two Python/Qt stacks in one process is
a known way to get exactly this. A minimal `import tttrlib` → `QApplication` →
import the plugin does **not** crash (3/3), so it needs the full session.

**What to try next**, in order: rebuild IMP against `arm64` so a single stack is
loaded; then re-run the ladder above — if the delegated arm reaches 0/8, land the
delegation unchanged.

**The delegation is kept** at `scratchpad/core_delegated.py`. It is finished
work, not a sketch.

### On how this entry got written three times

It was first filed blaming the delegation (4 crashes vs 3 clean runs), then
**withdrawn** as pre-existing noise when the same tree at HEAD gave 139/138/0,
then re-established with 8-run arms showing 0/8 against 3/8. The withdrawal was
the wrong call and the first instinct was right.

The lesson is not "trust the first instinct" — it is that **a three-run and a
four-run arm cannot separate a 0% failure rate from a 40% one**, and both of the
first two conclusions were drawn from arms that small. The 139/138/0 that
triggered the withdrawal was a *different command* (it included two other test
files), so it was never evidence about this one. Match the arms before comparing
them.

## WITHDRAWN — 2D-FLC's linear matrix does not "silently drop" its highest bin

**Filed and withdrawn 2026-08-11, same day.** I reported that
`create_2d_fdc_numba_int` loses 654 pairs at `lint_bin_factor` 3 and 974 at 5
(against a brute-force count of 6443), called it an unambiguous defect, and
wrote a fix. **The measurement was right and the conclusion was wrong.**

`TK_Create2DFDC_04.m:170-172` does the same trim:

```matlab
Var = size(Mat_2DFDC_lin) - 1 ;
Mat_2DFDC_lin = Mat_2DFDC_lin(1:Var, 1:Var) ;
```

MATLAB is 1-based over bins `1..lint_Imax`, so that is exactly ChiSurf's
`[:lint_imax - 1]`. The shortfall is the **published method's** behaviour.

**What produced the wrong conclusion**, worth recording because it is cheap to
repeat: I asserted "the MATLAB does no such trim" after reading the reference's
*construction* (lines 38-42) and not its *return* (170-172). Two reads of the
same file, one of them stopping early. The fix I wrote made things measurably
worse — `test_one_d_fdc_matches_microtime_histogram` fell from 0.98 to 0.9695
correlation — which is what sent me back to the source.

The behaviour is now pinned by
`plugins/fcs/flc_2d/test/test_fdc_parity.py::test_the_linear_matrix_trims_its_last_bin_as_the_reference_does`,
with the reason in the docstring, so the next person who measures the shortfall
finds the answer instead of re-deriving the fix.

**Still open and unaffected**: the log-axis question below, which is a genuine
disagreement between ChiSurf's two kernels — and there the reference does settle
it in the builder's favour.

### 🐛 On the ruling that this is a bug — the premise does not hold, verbatim

A ruling was relayed (2026-08-11) that this trim is a defect because *"the MATLAB
returns `Mat_2DFDC_lin` whole"*. **It does not.** `TK_Create2DFDC_04.m`, lines
170-172, unmodified:

```matlab
Var = size(Mat_2DFDC_lin) - 1 ;
Mat_2DFDC_lin = Mat_2DFDC_lin(1:Var, 1:Var) ;
Mat_2DFDC_lint = Mat_2DFDC_lint(1:Var) ;
```

The rule *"MATLAB is authoritative, fix ChiSurf to match"* is not in dispute and
is why this entry was withdrawn: applied to this trim it says **keep it**,
because ChiSurf's `[:lint_imax - 1]` already is it (MATLAB being 1-based over
bins `1..lint_Imax`).

This is recorded rather than silently obeyed because the fix was already written
once on the same wrong premise and made a real measurement worse
(`test_one_d_fdc_matches_microtime_histogram`, 0.98 → 0.9695). Anyone re-opening
it should start by reading past line 168 of the reference.

If the intent is to *change the method* — to keep the highest bin because the
trim loses real pairs, which it does — that is a legitimate decision, but it is a
deliberate divergence from the reference and should be recorded as one, not as
alignment with it.

**The tttrlib session's part in this, recorded because it is the reusable
lesson.** I (`opus-5/ac9f6757`) took "the MATLAB does no such trim" from a
message, wrote it into a `🐛 BUG` block here on the user's *MATLAB is
authoritative* ruling, and repeated it in tttrlib's PRD-036 and on the agent
board — in the same message where I said I was reading the reference
first-hand rather than a paraphrase. I had read its *construction* (lines
38-44) and never its *return* (170-175). A second-hand claim laundered through
a first-hand check reads exactly like a verified one. The trim stays; whether
it *should* is now back with the user as a deliberate-divergence question.

## 2D-FLC: the log-binned matrix moves when `lint_bin_factor` changes, and the two kernels disagree

**Found 2026-08-11**, from an observation by the tttrlib session porting these
kernels, then confirmed against the original MATLAB.

`flc_2d` has two entry points that both produce a log-binned 2D-FDC matrix, and
they build the log axis from **different** `t_imax`:

- `create_2d_fdc_numba_int` (the single-lag builder) uses
  `t_imax = lint_imax * lint_bin_factor` — the micro-time span rounded *up* to a
  whole number of **linear** bins.
- `_fdc_scan_log_kernel` (the multi-lag scan) uses `t_imax = span + 1`.

Measured on the same stream, gate `[1, 40]`, 12 log bins: the two log matrices
are **identical at `lint_bin_factor = 1` and different at 2, 3 and 5**. The total
count is the same (6443 in every case) — the pairs are redistributed across
different log bins, not lost.

**Two consequences, both user-visible:**

1. **A linear-binning knob silently changes the log-binned result.**
   `api.two_d_fdc` derives `lint_bin_factor` from `max_bins`, so a user adjusting
   what looks like a display/resolution setting for the *linear* matrix moves the
   axis of the *log* matrix — which is the one the 2D-FLC lifetime inversion runs
   on. Recovered lifetimes shift and nothing warns.
2. **The scan deviates from the published method.**
   `junk/2D-FLC-code/MatlabCodes/TK_Create2DFDC_04.m` computes
   `t_Imax = lint_Imax * lint_BinFactor` and uses that same `t_Imax` for
   `Mat_2DFDC_logt`. So the *builder* is faithful to the reference and the *scan*
   is not. tttrlib's `fdc_scan_log` (PRD-036) followed the scan, so the C++
   inherits the deviation.

**Settled 2026-08-11 (user: "the matlab is the authoritative code, if
discrepancy matlab wins, override chisurf, fix chisurf, stay close to matlab").**
The scan kernel now takes `lint_bin_factor` (default 1, where the rule collapses
to `span + 1`, so no existing caller's numbers move) and derives `t_imax` the
reference's way, so the two entry points agree at every factor. Pinned by
`test_both_kernels_put_the_log_matrix_on_the_same_axis`.

Kept here rather than deleted because the *original* reasoning was that:
either the scan adopts the reference's coupling, or the builder drops it and the
reference's coupling is declared an artifact of its linear/log matrices sharing
one variable. Whoever decides should say which, in the tracker, before either
kernel is delegated — `fdc_scan_axis` (tttrlib, 2026-08-11) now takes a
caller-supplied tick array, so ChiSurf can pass whichever axis is chosen rather
than inheriting one.

**How to re-derive**: call both entry points on the same stream with
`lint_bin_factor` in `{1, 2, 3, 5}` and compare the log matrices. Equal at 1,
different above it.

### 🐛 BUG — the open question is closed; the scan is wrong, ruled 2026-08-11

Not "whoever decides should say which" any more. The user has ruled that the
**MATLAB is authoritative**, so the coupling is the method and the *scan* is the
deviation: `_fdc_scan_log_kernel`'s unconditional `t_imax = span + 1` matches the
reference only at `lint_bin_factor = 1`. `TK_Create2DFDC_04.m:38-40`:

```matlab
t_Imax    = ceil((tMax-tMin)/tStep) + lint_BinFactor ;
lint_Imax = ceil(t_Imax / lint_BinFactor) ;
t_Imax    = lint_Imax * lint_BinFactor ;
Mat_2DFDC_logt = t_Imax .^ ([0:logt_Imax-1]'/(logt_Imax-1)) * tStep - tStep ;
```

**Fix the scan to derive the span this way.** tttrlib already does
(2026-08-11): `fdc_scan_log`/`fdc_log` take `lint_bin_factor`, defaulting to 1
where the rule collapses to `span + 1`, and `fdc_t_imax(span, factor)` exposes
the formula so a caller can build the identical axis for `fdc_scan_axis`.

**Fixed 2026-08-11** (`d9ef9bc32`): `_fdc_scan_log_kernel` takes
`lint_bin_factor` and derives `t_imax` the reference's way; the two entry points
now agree at every factor, pinned by
`test_both_kernels_put_the_log_matrix_on_the_same_axis`. **The simulation
evidence is still owed** — that requirement is right and is not met by the fix.

Moving the log axis moves the axis the lifetime inversion runs on, so "the
matrices now agree" is not sufficient — show that recovered lifetimes and the recovered relaxation rate
still match a simulation with a known answer, at `lint_bin_factor > 1` where the
axis actually moved. A fixture regenerated against the new axis will agree with
itself by construction and prove nothing about that.

One trap for the fixture work: the MATLAB keeps its log edges in floating point
and compares `(tauI*tStep) <= Mat_2DFDC_logt(T)`, while both ports round edges
to integer ticks. A single-pair disagreement at a bin boundary is that, not a
port error.

Recorded by the tttrlib session (`opus-5/ac9f6757`) on the user's ruling; the
code is owned by the ChiSurf session and has not been touched from here.

## The acquisition plot controllers paint over the window title with no host

**Found 2026-08-11**, in the PRD-98 screenshots. Each acquisition window builds
its plot controller parented to itself (`DecayPlotController(self)`, and the
four siblings). Inside ChiSurf the controller is re-homed into the main window's
controller area; **without a host window** — headless, a test, the standalone
entry point — it has nowhere to go and renders at the window's top-left corner,
on top of the title bar. Every acquisition window does it, including the ones
untouched by that change, so it is not new; it is recorded because it is the
first thing anyone screenshotting this plugin will see and it is not a defect in
what they are looking at.

**What closes this:** the controller should be hidden (or docked into the window
itself) when `chisurf.cs` is None, decided in the window rather than by whoever
happens to construct it.

## `core/math/hmm.py` needs a tttrlib that is not committed anywhere

**Found 2026-08-11**, by landing it. The HMM lattice delegation
([numba retirement](/subsystems/numba-retirement.md) item 3) calls
`tttrlib.hmm_forward_log` and its four siblings. Those exist and are verified —
this machine's installed tttrlib has them and ChiSurf's parity suite is green
against the numba fixture — but on the tttrlib side they live **only in the
shared working tree**. The session that wrote them has made no commits, by
choice: the shared index holds several sessions' staged work, so it left the
commit to a human.

So a **clean tttrlib checkout does not build a working ChiSurf HMM**. The
failure is at least loud rather than silent: `_require_lattice()` raises
`RuntimeError` naming the missing functions and telling the reader to rebuild,
instead of falling back to a second implementation — which is the whole point
of the change.

**What closes this:** committing tttrlib
`modules/math/{include/HmmLattice.h,src/HmmLattice.cpp,CMakeLists.txt,README.md}`,
`ext/python/{HmmLattice.i,tttrlib.i}`, `test/python/misc/test_hmm_lattice.py`,
`test/data/reference/hmm_lattice_numba_parity.npz`, plus its `CHANGELOG.md` and
`okf/prds/PRD-035-*.md`. Not done here because those are another session's
uncommitted files and committing them would be committing work that is not
mine.

**The trap:** a `git stash` or a clean checkout in tttrlib makes the lattice
vanish, and ChiSurf's HMM stops working with an error that points at a rebuild
rather than at the real cause. Check `python -c "import tttrlib;
tttrlib.hmm_forward_log"` before believing any other diagnosis.

## A simulated molecule's photon yield depends on its *index*, not its physics

**Found 2026-08-10** while building the mixture test set for segmentation and
region-wise MLE ([PRD-92](/prds/prd-92.md)).

In tttrlib's `SimEngine`, the photons a fluorophore emits are a fixed function
of the order it was added to the system. Measured with identical species,
identical brightness and identical lifetimes:

| index | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| photons | 659 | 32,336 | 169,099 | 97,421 | 473 | 2,947 |

The numbers do not move when the molecules are placed anywhere else on the
grid, and adding more molecules extends the sequence without changing the
earlier entries — `n=2` gives `[659, 32336]`, `n=6` gives the whole row above.
A molecule measured **alone** yields 20–45 photons wherever it is put, so the
index is doing all the work.

Ruled out by measurement rather than by reasoning: the lifetime (a uniform-τ
field gives the same row as a mixed one), the species layout (one shared
species with four fluorophores equals one species each), `independent_molecules`
(`True`/`False`/default identical), and the excitation PSF (widening it 2.3×
scales every entry and leaves the ratios alone). The photons land *at* the
molecule, so this is not misattribution to the wrong pixel.

**Compensated, visibly, in one place.** `test/data/mixture/make_mixture.py`
scales each blob's brightness by the measured per-index yield, which is linear
and exact (60294 / 59958 / 64110 / 74950 photons for a target of 60000). It is
written in the fixture generator rather than inside the simulator so that
deleting it is a one-line change once the engine is fixed — and so that nobody
reads the even test field as evidence the simulator produces one.

Fix belongs in tttrlib's `SimEngine`, in whatever indexes per-molecule
excitation or RNG streams.

## A simulated photon stream cannot be persisted, and the HDF5 path aborts the process

**Found 2026-08-10** while capturing a pre-split baseline for
[PRD-92](/prds/prd-92.md), which wanted the simulated CLSM stream stored beside
the labels it produced so an equivalence test could re-derive the whole chain
rather than its two ends.

**`TTTR.write` itself is fine**, including the `"PTO"` container: a stream read
from a real file (`m000.spc`, 174,438 photons) writes a 1.2 MB `.pto` and a
1.2 MB `.spc`, both returning `True`. The limitation is specific to a stream
**built in memory** — what `simulate_clsm_molecules` returns. It carries
`get_tttr_record_type() == -1`, `TTTRHeader.ensure_minimal_tags(header, 20, n)`
does not give it one, and PTO header writing is not implemented in the installed
build (`Error in TTTR::write, writing of headers not implemented`). The write
then returns `False` and leaves a **0-byte file**, with nothing raised — so a
caller that does not check the return value gets an empty container and
discovers it later.

**The HDF5 path is worse and is a separate defect.** `tttr.write(path)` with the
HDF5 default `abort()`s the interpreter — the installed tttrlib was compiled
against HDF5 headers 1.14.6 and links a 2.1.1 library, and the library's version
check kills the process rather than raising. A dependency mismatch should not be
able to end a user's session.

Neither is worked around in ChiSurf, and neither should be: **ChiSurf persists
to `.mmfdb.pto`**, and the container writers (`Measurement.create`,
`write_imaging_table`, `write_image`, `write_regions`) all embed files that
already exist on disk, so nothing in the shipped tree hits either path. It is
recorded because the *tests* want it — a simulated measurement that cannot be
stored is a fixture that has to be a pile of derived arrays instead — and
because the next person to try will spend the same half hour on `record type -1`.

Fix belongs in tttrlib: a record type for in-memory streams (or a PTO header
writer), and an HDF5 version check that raises instead of aborting.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## 33 of the MMFDB suite's failures were test-order contamination (fixed 2026-09-16)

**Found 2026-08-10** while adding three enumeration terms to
`mmfdb_flr_ext.dic` for the region/spot container contract
([PRD-92](/prds/prd-92.md)) and checking what that broke. `pytest tests` in
`modules/mmfdb` reports **33 failed / 757 passed**, concentrated in four files:
`test_mmfdb_user_management.py` (14), `test_security_architecture.py` (10),
`test_zip_archive_export.py` (6), plus one each in `test_fdb_general.py`,
`test_fdb_setups.py`, `test_mmcif_database_resolver.py`.

**Every one of them passes when its file is run alone** — the two largest were
checked directly (`test_mmfdb_user_management.py` + `test_security_architecture.py`
→ 40 passed), as was `test_zip_archive_export.py` (6 passed). So the suite is
carrying process-wide state between files, most likely an auth/session or
database singleton, in the same family as the `_DISPLAY_CONFIG` contamination
already recorded for ChiMOL: one test's leftovers break *other files*, which is
why bisecting with `-k` finds nothing.

**Not fixed here**, and not caused by the dictionary change (that adds three
enum values and a comment; the failures are in user management, security and
zip export, none of which read the enumeration). Recorded because the number is
large enough to look like a regression to whoever runs the suite next, and
because it means the suite currently cannot tell a real breakage from this
noise. Whoever fixes it should bisect by explicit node ids across *files*, not
within one.

**Resolved 2026-09-16** (mmfdb `a581bb6`). The singleton was what this entry
guessed at: `register_services` resolved the default database path once and
cached it in a module global, so every handler called afterwards went to
whichever database the *first* registration had found. A later file's handler
then read an empty database -- a valid session token was "Authentication
required", and inserts failed their foreign keys. The path is now pinned only
when a caller names one. `pytest tests` passes in one run (809 passed), and the
same bug was failing 11 tests in ChiSurf's `test/fio`.

## The OpenGL point glyph renders at half the size it is asked for

**Found 2026-08-10** while porting point geometry to the WebGPU backend, by
comparing the same scene through both renderers.

`dots` on 148L carries `meta["size"] = 8.0`. `qtgl` sets both `gl_PointSize` and
`glPointSize` to `size * devicePixelRatioF()`, and the fragment shader keeps the
inscribed circle of the sprite, so the dot should be **8 px across**. Measured on
`test/renders/gl_baseline/dots_view.png`, the modal lit run per row is **4 px**
(2,112 rows at 4, tailing off by 8). Ruled out: the device pixel ratio is
genuinely `1.0` for both the window and the GL widget, and
`GL_ALIASED_POINT_SIZE_RANGE` is `[1, 64]`, so neither scaling nor clamping
explains it. Apple's GL-over-Metal sprite path is the remaining suspect.

**Resolved by deletion (2026-08-10).** `qtgl.py` is gone, so nothing draws the
half-size glyph any more. The entry stays because the *baseline* does: the
frozen `dots_view.png` in `test/renders/gl_baseline/` still shows a 4 px dot,
and `compare_wgsl dots` therefore shows the WGSL renderer drawing a glyph twice
the size of the reference. That row is **correct and expected** — do not "fix"
the renderer toward the baseline.

## `test/gui` crashes the interpreter mid-run, and 20 of its failures are contamination

**2026-08-10.** `pytest test/gui` dies with `Bus error: 10` (exit 138) at around
44 %, just after `test_language_selector`, and reports ~22 failures before it
does. Almost none of that is real:

- **The failures are mostly cross-test contamination.** Two of three sampled
  failures (`test_dialogs_and_progress::test_confirm_declines_by_default`,
  `settings/test_log_filter::test_log_list_widget_uses_multiple_columns`) **pass
  when run on their own**. Judge a `test/gui` failure by re-running that test
  alone before believing it.
- **The one real failure sampled** is `ParseFCSModel object has no attribute
  'get_plot_reference_modes'` (raised from `chisurf/core/base.py`), i.e. an FCS
  model/plot-reference API mismatch — not a GUI defect.
- **A second, separate crash** appears when several plugin suites are combined in
  one process: `chisurf/plugins/{tttr,pch,core/project_browser,burst/...}` plus
  the dock suites run to ~89 % **with zero failures** and then take
  `Segmentation fault: 11` in teardown. Split into two invocations, the same
  tests are 146 + 254 passed. Same shape as the `fret_trajectory` entry below.

So a red `test/gui` is not evidence that a change broke something. Until the
contamination and the two crashes are fixed, verify a GUI change by running the
suites that cover it, individually, and say which ones.

## A simulated photon stream cannot be persisted, and the HDF5 path aborts the process

**Found 2026-08-10** while capturing a pre-split baseline for
[PRD-92](/prds/prd-92.md), which wanted the simulated CLSM stream stored beside
the labels it produced so an equivalence test could re-derive the whole chain
rather than its two ends.

**`TTTR.write` itself is fine**, including the `"PTO"` container: a stream read
from a real file (`m000.spc`, 174,438 photons) writes a 1.2 MB `.pto` and a
1.2 MB `.spc`, both returning `True`. The limitation is specific to a stream
**built in memory** — what `simulate_clsm_molecules` returns. It carries
`get_tttr_record_type() == -1`, `TTTRHeader.ensure_minimal_tags(header, 20, n)`
does not give it one, and PTO header writing is not implemented in the installed
build (`Error in TTTR::write, writing of headers not implemented`). The write
then returns `False` and leaves a **0-byte file**, with nothing raised — so a
caller that does not check the return value gets an empty container and
discovers it later.

**The HDF5 path is worse and is a separate defect.** `tttr.write(path)` with the
HDF5 default `abort()`s the interpreter — the installed tttrlib was compiled
against HDF5 headers 1.14.6 and links a 2.1.1 library, and the library's version
check kills the process rather than raising. A dependency mismatch should not be
able to end a user's session.

Neither is worked around in ChiSurf, and neither should be: **ChiSurf persists
to `.mmfdb.pto`**, and the container writers (`Measurement.create`,
`write_imaging_table`, `write_image`, `write_regions`) all embed files that
already exist on disk, so nothing in the shipped tree hits either path. It is
recorded because the *tests* want it — a simulated measurement that cannot be
stored is a fixture that has to be a pile of derived arrays instead — and
because the next person to try will spend the same half hour on `record type -1`.

Fix belongs in tttrlib: a record type for in-memory streams (or a PTO header
writer), and an HDF5 version check that raises instead of aborting.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## 33 of the MMFDB suite's failures were test-order contamination (fixed 2026-09-16)

**Found 2026-08-10** while adding three enumeration terms to
`mmfdb_flr_ext.dic` for the region/spot container contract
([PRD-92](/prds/prd-92.md)) and checking what that broke. `pytest tests` in
`modules/mmfdb` reports **33 failed / 757 passed**, concentrated in four files:
`test_mmfdb_user_management.py` (14), `test_security_architecture.py` (10),
`test_zip_archive_export.py` (6), plus one each in `test_fdb_general.py`,
`test_fdb_setups.py`, `test_mmcif_database_resolver.py`.

**Every one of them passes when its file is run alone** — the two largest were
checked directly (`test_mmfdb_user_management.py` + `test_security_architecture.py`
→ 40 passed), as was `test_zip_archive_export.py` (6 passed). So the suite is
carrying process-wide state between files, most likely an auth/session or
database singleton, in the same family as the `_DISPLAY_CONFIG` contamination
already recorded for ChiMOL: one test's leftovers break *other files*, which is
why bisecting with `-k` finds nothing.

**Not fixed here**, and not caused by the dictionary change (that adds three
enum values and a comment; the failures are in user management, security and
zip export, none of which read the enumeration). Recorded because the number is
large enough to look like a regression to whoever runs the suite next, and
because it means the suite currently cannot tell a real breakage from this
noise. Whoever fixes it should bisect by explicit node ids across *files*, not
within one.

**Resolved 2026-09-16** (mmfdb `a581bb6`). The singleton was what this entry
guessed at: `register_services` resolved the default database path once and
cached it in a module global, so every handler called afterwards went to
whichever database the *first* registration had found. A later file's handler
then read an empty database -- a valid session token was "Authentication
required", and inserts failed their foreign keys. The path is now pinned only
when a caller names one. `pytest tests` passes in one run (809 passed), and the
same bug was failing 11 tests in ChiSurf's `test/fio`.

## `test/gui` crashes the interpreter mid-run, and 20 of its failures are contamination

**2026-08-10.** `pytest test/gui` dies with `Bus error: 10` (exit 138) at around
44 %, just after `test_language_selector`, and reports ~22 failures before it
does. Almost none of that is real:

- **The failures are mostly cross-test contamination.** Two of three sampled
  failures (`test_dialogs_and_progress::test_confirm_declines_by_default`,
  `settings/test_log_filter::test_log_list_widget_uses_multiple_columns`) **pass
  when run on their own**. Judge a `test/gui` failure by re-running that test
  alone before believing it.
- **The one real failure sampled** is `ParseFCSModel object has no attribute
  'get_plot_reference_modes'` (raised from `chisurf/core/base.py`), i.e. an FCS
  model/plot-reference API mismatch — not a GUI defect.
- **A second, separate crash** appears when several plugin suites are combined in
  one process: `chisurf/plugins/{tttr,pch,core/project_browser,burst/...}` plus
  the dock suites run to ~89 % **with zero failures** and then take
  `Segmentation fault: 11` in teardown. Split into two invocations, the same
  tests are 146 + 254 passed. Same shape as the `fret_trajectory` entry below.

So a red `test/gui` is not evidence that a change broke something. Until the
contamination and the two crashes are fixed, verify a GUI change by running the
suites that cover it, individually, and say which ones.

## 20 file types in `chisurf/` are missing from an installed distribution

**Found 2026-08-10** while adding `*.wgsl` for the chigame shader, which had the
same defect and would have shipped broken.

`[tool.setuptools.package-data]` is an allow-list of globs. Any extension not in
it is **not copied into an installed copy**, and nothing warns: the package keeps
working from a source checkout, so the failure only ever appears for someone who
installed it.

The ones that matter, because shipped code loads them at runtime:

* **`.ico`, `.icns`, `.bmp`, `.qrc`** — GUI icons and the Qt resource manifest;
* **`.ini`, `.yml`** — device configuration (the PicoQuant TCSPC device files)
  and plugin example configuration;
* **`.xlsx`, `.xlsm`, `.gnumeric`** — the potential-energy databases under
  `core/structure/potential/database/`;
* **`.c`, `.cpp`, `.h`** — the bundled AV kernel sources.

The rest (`.dcd`, `.pdb`, `.pml`, `.pdf`, `.pdat`, `.mti`, `.spc`, `.rmf3`,
`.bur`) are fixtures and reference material, so they matter less — but the sweep
does not distinguish, and neither does an install.

**Not fixed here** because the correct pattern differs per family: some want a
package-data glob, some belong in a fixture directory that is not installed at
all, and the `.qrc`/icon set may want compiling rather than copying. Deciding
that is a packaging change, not a side effect of adding a shader.

**Guarded**: `test/test_package_data_covers_shipped_files.py` holds these as a
**shrinking** `KNOWN_UNCOVERED` list and fails on any *newly* uncovered type, so
this cannot grow silently. A companion test fails when an entry becomes stale.
The fix for each is to add a pattern to `pyproject.toml` and strike the line.

## ✅ FIXED — ChiMOL ambient occlusion was wired the wrong way round

**Fixed 2026-08-10.** Kept here because the *first* diagnosis below was wrong in
an instructive way, and because one gap remains.

**What it actually was.** Not a stray `not`. The coarse per-residue estimate at
`view.py` is a deliberate **fallback** for when the fine per-vertex bake does not
run — its own comment says running both would darken the cartoon twice — but it
was gated on `not enabled` while the fine bake contributed *nothing* to a tube
cartoon. So the fallback was the only occlusion a cartoon ever received, and it
appeared exactly when the user asked for none. Flipping the `not`, which is what
the first diagnosis proposed, would have deleted the only working AO.

**The fix.** `_occlusion_enabled()` is now the single reader of
`occlusion.enabled`; `_estimate_ambient_occlusion` is wrapped in `view.py` so all
**six** call sites honour it (only one consulted it before, and five shaded
regardless); and the coarse path asks `_per_vertex_occlusion_available()` rather
than a second, disagreeing condition — which preserves the no-double-darkening
intent in both directions. `sticks.ambient_occlusion` is deleted: a second switch
for the same concept, read by nothing, and sticks bake no occlusion for it to
turn on. Guarded by `test/test_occlusion_switch.py`, which asserts **both**
directions — a test that only checks "the image changed" passes an inverted
switch, which is how this survived.

Measured after, on lit pixels only: cartoon 91.05 on / 142.66 off, spheres 109.74
/ 158.96, surface 106.78 / 109.49 — on darkens in every case.

**Still open: `sticks` has no ambient-occlusion path at all** (toggling the switch
changes exactly 0 pixels). That is a missing feature, not a broken switch, and it
is why `sticks` is excluded from the guardrail's parametrisation.

**Two measurement traps worth keeping.** The first grab after a rebuild can be a
partially initialised framebuffer that comes back as *noise* — it poisoned a
brightness comparison until the image was looked at, and the fix is to discard one
grab. And the background is most of the frame, so a mean over the whole image
dilutes an inverted switch into what looks like rounding; compare lit pixels only.

## Superseded first diagnosis, and the other two settings

**2026-08-10.** Found while capturing the OpenGL render baselines before the
WebGPU port ([chimol-web](/plugins/chimol-web.md)). All three were measured with
matched A/B pairs that differ by one setting, not read off the source.

**1. `occlusion.enabled` is inverted.** The only gate is
`chimol/renderer/view.py:5441`:

```python
if not bool((_DISPLAY_CONFIG.get("occlusion") or {}).get("enabled", True)):
    occ_ca = _estimate_ambient_occlusion(...)
```

so ambient occlusion is computed when occlusion is switched **off**. Measured on
148L cartoon against a plain control: `enabled=on` is **0.00 %** different from
no-AO-at-all, `enabled=off` is **9.35 %** different with a max channel delta of
188. Turning the feature on turns it off.

The same line is the only gate in the file: the other three
`_estimate_ambient_occlusion` call sites (`view.py:5785, 6265, 7817`) are
**ungated entirely**, so sticks/surface/bead AO ignores the setting in both
directions. Fixing the `not` alone would therefore change cartoon only and leave
the setting still lying about the other three.

**Not fixed in the same change deliberately**: the fix changes what the renderer
draws, and it would invalidate the GL baselines being captured in that very
change — the baselines have to record what ships today, or the WebGPU port has
nothing to be compared against. It wants its own before/after pair.

**2. `sticks.ambient_occlusion` gates nothing.** It is registered, reachable via
`set sticks.ambient_occlusion, on`, and stores a value that no code reads — the
real key is `occlusion.enabled`. Measured: **0 pixels** change. Another instance
of "the setting is registered" and "the setting works" being different claims.

**3. `balls.impostor_min_atoms` does not apply to atomic spheres.** Not a defect —
`view.py:6026` reads it from `balls_cfg` and the docstring says *beads* — but it
means `show spheres` on a PDB never takes the point-sprite impostor path, so a
baseline for that path needs a bead/integrative model. Recorded because two
sphere scenes captured with `balls.impostor_min_atoms` at 100000 and at 10 came
out **bit-identical**, which looks like a broken setting until you find the
docstring.

## `test_numba_seam` is red at HEAD: six allow-list strikes landed without their code

**2026-08-11.** `test/test_numba_seam.py::test_no_new_numba_imports` fails on
six files that import numba and are no longer listed in
`test/numba_import_allowlist.txt`:

```
chisurf/core/fluorescence/burst/bocpd.py
chisurf/core/fluorescence/tcspc/corrections.py
chisurf/core/fluorescence/tcspc/tcspc.py
chisurf/plugins/fluorescence_decay/lltf/core/convolve.py
chisurf/plugins/fluorescence_decay/lltf/core/fitter.py
chisurf/plugins/fluorescence_decay/lltf/core/scaling.py
```

All six are **already ported in the shared working tree** — none imports numba
there — so the failure is invisible to anyone running the suite from that tree
and appears only against a clean checkout. The allow-list strike was committed;
the ported source was not. Fixing it means committing another session's
uncommitted work, which is off limits, so it belongs to whoever owns those
files.

**The shape is what to carry forward, because the retirement will keep hitting
it:** striking a line and porting the kernel are *one* change. Split across two
commits, the tree is red for everyone who did not inherit the working tree —
and the guard, which exists precisely to keep the list from drifting from the
code, reads as broken rather than as correct. Verified pre-existing: identical
at `HEAD~1` and at HEAD, in an isolated `git worktree`, with the same six files.

## `test_prd_mentions` is red on two files that belong to another session

**2026-08-10.** `test/test_prd_mentions.py` fails on files that name a PRD in
shipped source (the `mfd_prepare` files this entry originally listed were
cleaned **2026-08-15**, commit `e7f9a3835`):

```
chisurf/gui/chiplot/backends/__init__.py
chisurf/gui/chiplot/backends/opengl/__init__.py
```

All are **untracked** — they are new files from other sessions' in-flight
work in the shared tree, so editing them would collide with whoever is writing
them. The fix is one line each (point at the OKF concept that owns the area, or
drop the reference) and belongs to the session that lands those files.

Not to be confused with a regression from the tool-window migration: that pass
*removed* a file from the allowlist (`chisurf_dock_tool.py`, 154 → 153 entries)
and added none.

## Registering a dropped measurement in MMFDB fails on a foreign key

**2026-08-07.** Dropping eleven `.spc` files into the burst workflow, with the
`tttr_to_pto` guard converting them, stores the object and then fails to
register it:

```
INFO  mmfdb.store.object_store - Stored new object: a3dbd6be... (13227189 bytes)
ERROR mmfdb.store.transactions - Database transaction failed and was rolled back: FOREIGN KEY constraint failed
ERROR root - MMFDB RPC failed: raw_data.register: FOREIGN KEY constraint failed
```

The object store keeps the blob; the metadata row is rolled back — so the
container is on disk and MMFDB does not know about it, which is the state that
makes "open it in ndX from MMFDB" fail later with nothing to point at. The
analysis itself continues, so nothing surfaces in the window.

Not diagnosed here: the failing constraint is not named in the message, and
`raw_data.register` lives in the **mmfdb repository** (`modules/mmfdb` is a
symlink to its own checkout), where the fix and its test belong. Whoever picks
it up should first turn the bare `FOREIGN KEY constraint failed` into a message
that says *which* key — SQLite will report it with
`PRAGMA foreign_key_check` after the failure — because the same message will
otherwise be re-diagnosed from scratch every time.

## `NUMBA_NUM_THREADS` collides when the fio suite runs as a whole

**2026-08-07.** `test/fio/test_vv_vh.py::test_vv_vh_spectrum_equals_concatenated_components`
and `test/fio/test_ndxplorer_rpc_bridge.py::test_lines_service_phasor_and_fret_over_inprocess_client`
fail with `RuntimeError: Cannot set NUMBA_NUM_THREADS to a different value once
the threads have been launched (currently have 7, trying to set 8)` when
`pytest test/fio` runs the directory, and **both pass in isolation**. Something
earlier in the directory launches numba's thread pool at 7 and something later
asks for 8; neither of the failing tests is the one setting it. Pre-existing and
unrelated to the burst/`.pto` work that surfaced it. The fix is to find the
setter and have it either run before any numba entry point or not set the count
at all — the same "one process-wide global, so one test breaks *other files*"
shape as chimol's `_DISPLAY_CONFIG`, and it wants the same treatment: bisect by
explicit node ids, not `-k`.

## Burst Selection's progress bar cannot advance within a single large file

**2026-08-07.** `analyze_request` (`chisurf/plugins/burst/burst_selection/api/selection.py`)
now reports progress **per file** to the GUI's `TaskHandle` (one file
finishing is the chunk it can report on), which fixed the busy-spinner feel
of a multi-file batch. It does **not** help a single very large file — a
merged multi-measurement `.pto` (easy to produce since the `tttr_to_pto`
drop guard landed the same day, see [PRD-85](/prds/prd-85.md)) or simply a
long acquisition still reports only once, at completion, because
`apply_photon_filters`/`find_bursts` inside `analyze_file` are each one
vectorized call over the whole photon stream with no internal chunking.

Not fixed here because it is a correctness risk, not a wiring gap: splitting
a burst search into windows requires carrying detector/burst-in-progress
state across window boundaries correctly, or a burst near a window edge
either gets cut in two or double-counted. `tttrlib`'s burst-search
implementations (`chisurf/core/fluorescence/burst/tttrlib_search.py`,
registry-driven) are compiled and offer no progress callback to hook into
either. Whoever picks this up should first check whether a newer `tttrlib`
exposes incremental/streaming burst search before attempting to chunk the
input in Python.

Separately, the fix deliberately did **not** thread
`TaskHandle.progress_window()`'s cancellation-aware `set_value` through this
path (only report-only `progress_callback`): `chisurf/server/dispatcher.py`'s
`ServiceDispatcher.dispatch` catches `except Exception` broadly and converts
*any* exception — including the `concurrent.futures.CancelledError` a
cancelled `progress_window.set_value()` raises — into an ordinary
`{"ok": False, "error_code": "INTERNAL_ERROR"}` result. `BurstSelectionClient.analyze_files`
then raises a plain `RuntimeError` from that, so cancelling a burst search
would show as a scary error message instead of the silent stop the rest of
the app gives you via `run_in_background`'s `CancelledError` handling. Giving
burst_selection real mid-search cancellation needs the dispatcher to let
`CancelledError` (or some other user-cancel signal) propagate instead of
being folded into a generic error — a dispatcher-level change, not a
burst_selection one, and worth checking whether any other RPC service
already depends on the current blanket-catch behaviour before changing it.

## Two `ParameterGroupTable*` GUI tests fail headless, unrelated to anything they test

**2026-08-07.** `test/gui/test_paired_table_layout.py::test_the_list_style_stacks_a_wide_component`
and `test/gui/test_parameter_table_wheel.py::test_a_long_table_can_still_be_scrolled`
fail deterministically under `QT_QPA_PLATFORM=offscreen`, both against a
`QtWarningMsg: This plugin does not support propagateSizeHints()` warning —
the first as a row-count mismatch after a delete (`4` instead of `2`), the
second as a scrollbar that never gains a range (`0 > 0`). Both look like the
offscreen platform plugin not computing real widget/viewport geometry, not a
behavioural regression: `chisurf/gui/autoform/sections/parameter_table.py`
(the module both tests exercise) imports only
`chisurf.gui.widgets.chitable.delegates`, which has no import of
`chitable.source` or `chitable.filters` at all — verified by grep, not by
reverting anything, since the working tree is shared with other sessions.
Found incidentally while checking chitable's own test suite for regressions
after removing chitable's module-level pandas import; not investigated
further because neither file was touched.

## img_flow: the demo PTU is one frame short of what it simulates

`test_the_demo_is_a_readable_ptu_whose_flow_comes_back` asks `create_demo` for
30 frames and `load_image_stack` reports 29. Pre-existing and deterministic —
it reproduces with no local changes to the plugin.

The cause is the marker convention rather than a lost frame. `demo.py` calls
`engine.run_scan(scanner)` once per frame and the simulator emits a frame
marker at the **start** of each, so 30 markers arrive. A CLSM reader builds a
frame from one marker to the next, which makes 30 markers 29 closed frames; the
last frame's photons are in the file with nothing to terminate them.

Not fixed here because the fix is not local. Emitting a 31st marker by running
one more scan would add that scan's photons too, so closing the last frame
means either a simulator API for a trailing marker (tttrlib's `SimScanner`) or
a reader that treats end-of-file as a frame boundary. Which of those is right is
a question about the simulator, not about this plugin, and changing the demo
changes both the guided tour's data and `expected_profile`.

Worth checking first: whether a real PTU from a scanner has a trailing frame
marker. If it does, the simulator is wrong; if it does not, the reader is, and
every measured file has been one frame short all along — which would be the
more interesting answer.

## RESOLVED — burst FCS: the `td4` companion was written on the bursts that produced a result, not on the bursts

**Discovered 2026-08-07, fixed the same day.** `_save_td4_results` in
`chisurf/plugins/burst/burst_fcs_correlator/wizard.py` built its row grid from
the correlations it computed, then zero-interleaved that. The
[burst-companion contract](../subsystems/burst-companions.md) requires **one
row per burst of the measurement, including the ones the analysis skipped** —
because the file is merged onto the burst table *by position*.

The function's own docstring already stated the consequence, which is why this
was recorded rather than merely discovered: "a burst the correlator skipped is
a missing row there rather than a blank one, so every burst after it is merged
against the wrong burst's diffusion time — silently, because the shape and the
column names stay right and only the attribution is wrong."

Two further deviations in the same function:

* it wrote the layout **by hand** (`out[1::2]`, `'\t'.join(cols) + '\t\n'`,
  `%.6f`) rather than through `burst_companion.write_companion`. That was the
  same divergence the `.bv4` writer had until 2026-08-07;
* the container written beside it (`_write_container`) was already **correct**
  — it carries `Burst Index` as a declared key, and is unaffected by this fix.

**The fix needed the burst count**, which the correlator did not hold at the
point the row grid was built. It turned out to already be available higher up:
`local_idx` (the row's `Burst Index`) comes from `enumerate(ranges)` where
`ranges` is the *full* per-measurement burst list `parse_bur_file`/
`parse_bst_file` returns — so `len(ranges)` is exactly the true grid size, no
second `.bur` read needed. `_run_burstwise_fcs` now threads that through as
`burst_counts: {(Burst Folder, First Stem): n_bursts}`, and
`_save_td4_results` allocates a full `(n_bursts, n_cols)` grid, fills in the
computed rows at their true `Burst Index` position, and writes it through
`burst_companion.write_companion` (which also fixed the by-hand layout). The
sparse, results-only table still goes to `_write_container` unchanged, since
its declared-key join was already correct.

Pinned by `chisurf/plugins/burst/burst_fcs_correlator/test/test_td4_writer.py`
(the layout test the original note asked for): a skipped burst reads back as a
sentinel row, not a missing one, and a computed burst keeps its true row
position rather than being compacted upward. Landed alongside the last three
[PRD-82](../prds/prd-82.md) pandas ports.

## acquisition: the SPC-130 record decoder exists twice, because the library exposes its own only behind a file reader

**2026-08-06.** `_process_bh_spc_records_numba` in
`chisurf/plugins/core/acq/gui/tool.py` is a hand-maintained numba copy of the
simulation library's `RecordProcessor<BH_RECORD_TYPE_SPC130>`, and its own
docstring says so. Asked "why is this here at all, it should be the library":
because the acquisition path decodes records arriving **from the card, in
memory**, and the library's Python surface offers no "decode this buffer" entry
point — only `TTTR(filename)`, plus `append_events`, which takes events that are
already decoded. The duplication is forced by that gap, not chosen.

**It has not drifted.** Measured against `m000.spc` (SPC-130, 174 438 events):
same event count, and macro times, micro times and routing channels identical
over the whole file. Pinned now by
`chisurf/plugins/core/acq/test/test_spc_record_decoder.py`, which reads a real
`.spc` both ways — a copy of a decoder with nothing holding it to the original
is how the two come to disagree about an overflow run or a gap flag on
somebody's data months later, with no error anywhere.

**The fix is an in-memory record decoder in the library's Python surface**, and
it is now specified there as the library's PRD-021 — "decode this buffer" with
the decoder state carried across chunks, ranged and streaming reads for all
fourteen container types, and the whole `.set` sidecar in every binding. **Two
deletions here are that PRD's definition of done**, and neither can happen
before it lands or acquisition stops working:

* `_process_bh_spc_records_numba` and its pinning test;
* `bh_spc/reader.py`, once the sidecar parser is in the library.

**The sidecar is the second half, and it is the same story.** `bh_spc/reader.py`
parses the `#PR`/`#SP` hardware-parameter blocks of a `.set` file for the
card-setup dialog. The library reads `.set` sidecars too (`read_bh_set_file`),
but only the five imaging tags a photon reader needs — `SP_IMG_X`, `SP_IMG_Y`,
`SP_PIX_CLK`, `SP_TAC_R`, `SP_ADC_RE` — and that function is **not exposed in
any binding**. Measured on two real sidecars, that is **5 of 115** parameters
and **5 of 121**: the same file is parsed twice by two implementations, each
ignoring what the other wants. Neither is wrong; the split is.

**The copy is not a performance workaround, which is the thing most likely to be
assumed.** Reading and decoding 299 999 records from a file through the library
costs 1.50 ms (200 M records/s); the numba copy decodes the same records,
already in memory, in 0.66 ms (457 M records/s). Different work — one includes
the file read — and both far faster than anything downstream needs. The copy
exists because there is no entry point.

## RESOLVED — photon container: adding an instrument file read it whole into memory

**2026-08-06, fixed 2026-08-07.** `Measurement.create` embeds the instrument
file verbatim, and the only input path tttrlib exposed took bytes, so an 8 GiB
PTU became an 8 GiB Python `bytes` before it was written.

Fixed in the library rather than worked around here: tttrlib PRD-020 added
`PtoFile::add_file`, which writes the same header and streams the payload in
blocks. `_add_payload_from_path` already preferred it when present, so the seam
picked it up with no chisurf-side change. The same PRD closed the read half —
column subsets and row windows of an embedded store, ranged byte reads, and
cues for positioning in a photon stream.

## imaging: a 30-frame acquisition reconstructs as 29, and the flags that would fix it do not reach the reconstruction

**2026-08-06.** Found by rebuilding the simulation library from source (the
environment carried a build predating its 2026-08-05 CLSM fix, so this is
invisible until someone rebuilds). `chisurf/plugins/microscopy/img_flow/test/
test_img_flow.py::test_the_demo_is_a_readable_ptu_whose_flow_comes_back` fails
on `assert stack.data.shape[0] == 30` with **29** — one full frame of a
30-frame scan is gone.

**The file is not at fault, and the edge arithmetic is right.** The demo writes
30 frame markers and the last one is followed by a complete frame: 64 line-start
and 64 line-stop markers. Called directly, the edge finder answers correctly —

```
get_frame_edges(tttr, 0, -1, [4], 1, 0, skip_before, skip_after, 1, -1)
  skip_before=True  skip_after=False -> 31 edges = 30 frames   <- correct
  skip_before=True  skip_after=True  -> 30 edges = 29 frames
  skip_before=False skip_after=False -> 32 edges = 31 frames   (leading stub)
```

and `create_frames` makes `len(edges) - 1` frames, which is the right rule.

**What is wrong is one layer up.** Constructing `CLSMImage` with those flags
gives **29 frames for both values of `skip_before_first_frame_marker`** and 28
for both values of `skip_after_last_frame_marker` — i.e. the count moves with one
flag and not the other, and is one lower than the edge list implies in every
combination. The flags are not reaching the reconstruction the edge finder sees.
Reproduce with:

```python
from chisurf.plugins.microscopy.img_flow.demo import create_demo
create_demo(path, n_frames=30)
tttrlib.CLSMImage(tttrlib.TTTR(str(path)), marker_frame_start=[4],
                  marker_line_start=1, marker_line_stop=2, marker_event_type=1,
                  skip_before_first_frame_marker=..., channels=[0], fill=True)
```

**Trap in re-deriving it**: the demo's frame marker is routing channel **4**, not
3 — PTU writes markers as bit positions, so the value in the file and the value
in the docs differ. Passing `[3]` finds no frame markers at all and
`get_frame_edges` returns an empty list, which looks like a different bug.

Not fixed here because it belongs in the imaging module of the companion library
and has nothing to do with the table work that surfaced it. The test is left
**red rather than xfailed**: this is silent data loss — the frame simply is not
there, and the array shape is the only thing that says so.

## PDA: the dynamic two-state fit lands just past its convergence threshold

**2026-08-06.** `test/gui/test_pda2c_model_editor.py::test_dynamic_pda_recovers_
exchange_and_rejects_the_static_model` fails on `assert fit_dyn.chi2r < 1.5` with
**chi2r = 1.5339**, deterministically — the same value on every run and on the
commit before the PRD-38 cleanup, so it is not a flake and not caused by that
work (verified in a detached worktree at `b5f6eec0c^`).

Everything the test is *about* passes: it recovers `k_ex`, `R1`, `R2` and `x1`
within tolerance and does reject the static model. Only the absolute goodness-of-
fit is 2 % over the line, so the question is whether 1.5 is the right threshold
for this fixture or whether the dynamic model leaves a small systematic residual.
Do not "fix" it by moving the number without answering that.

## chimol: the mouse-mode block's text is clipped at the panel's column width

**2026-08-06.** Seen while composing the object panel over a `ray` result on a
902x562 viewport: the bottom-right block reads `Mouse Mode 3-Button Viewin`,
`Whee`, `MovS`, `+Box-BoxClipMovS` — every line runs out of column. The column
is a fixed `column_width = 220`, and the block is laid out to that regardless of
what its longest line needs, so it is clipped at every window size rather than
at small ones.

Not caused by the ray-image change (it is the same before and after, and the
panel is a fixed-width column either way), and not chased there because the fix
is a layout question for the panel: either the block measures its own text and
the column takes the wider of the two demands, or the mode names abbreviate.
PyMOL sizes the internal-GUI column from the text. Reproduce with the composer
in `chisurf/plugins/chimol/test/test_ray_keeps_the_panel.py` — paint
`paint_screen_space` onto a `QImage` and read the bottom-right corner.

## models: `ReactionWidget` (stopped flow) could not be instantiated — RESOLVED 2026-08-06

**Resolved** by [PRD-38](../prds/prd-38.md) increment 18: `ReactionModel`
(`core/models/stopped_flow/reaction.py` + `reaction.view.json`) implements
`update_model`, `reaction.ui` is deleted, and `ReactionWidget` is a deprecation
alias. Kept here for what the port found underneath it.

`ReactionWidget.__abstractmethods__` was `frozenset({'update_model'})`, so choosing
"Reaction" in the stopped-flow model menu raised `TypeError`. **All three**
stopped-flow / ET entries were in that state.

**Because it could never be opened, `ReactionSystem` had never really run**, and
carried four defects the new model is the first caller to hit:

* `reactions` returned a `zip`. `odeint` calls `rate_equation` once per step with
  that same object, so it was exhausted after the first call, every later
  derivative was zero, and **every reaction system integrated to a flat line**.
* `n_species` raised `NameError` — `reduce` was never imported and the `except`
  only caught `TypeError`.
* `species_brightness` could not round-trip a list of numbers: the setter stored
  what it was given, the getter read `.value` off each entry.
* `plot()` called a matplotlib alias the module never imported. Deleted rather
  than fixed.

Rate constants were plain `Parameter`s, i.e. **not fittable**; the hand-written
editor hid that by appending its own widget-backed parameters instead of calling
`add_reaction`. The guard (`test/models/test_reaction_model.py`) asserts an
`A ⇌ B` system relaxes to the analytic `k_f/k_r` equilibrium, not merely that it
computes something.

*General lesson: an unopenable editor hides the state of everything below it. Look
for the missing caller, not only the missing control.*

## models: `EtModelFreeWidget` is registered and cannot be instantiated

**2026-08-06. Resolved by deprecation** — the fit is deregistered and the module
deleted; `EtModelFreeWidget` resolves to `None` so an old config drops the entry
instead of crashing. Kept here because the *reason* matters: it had never worked.
Choosing it failed with

```
TypeError: Can't instantiate abstract class EtModelFreeWidget
           without an implementation for abstract method 'update_model'
```

`EtModelFreeWidget.__abstractmethods__` is `frozenset({'update_model'})`. Its
compute class `EtModelFree` lives *inside*
`chisurf/gui/widgets/models/tcspc/et.py` (line ~250), which is why it is tier B in
[PRD-38](../prds/prd-38.md): the model has to be extracted into `core/models/**`
before its editor can be described in JSON, and the extraction is also what would
give it a real `update_model`.

**Why it went unnoticed:** nothing constructs it. Construction smoke tests skip GUI
model widgets, and the editor-integration guard walks only the JSON-described
models. It is registered in `experiment_configs.yaml`, so it appears in the menu
regardless.

To reproduce, resolve it the way `add_fit` does and build a `Fit`:

```python
from chisurf.gui.widgets.models.tcspc import EtModelFreeWidget
print(EtModelFreeWidget.__abstractmethods__)   # -> {'update_model'}
```

Once ported, drop it from `_a_still_legacy_widget_model`'s skip in
`test/gui/test_auto_model_widget.py` -- that helper currently steps over abstract
widgets so the MRO tests do not report this pre-existing breakage as their own.

## models: the parse editors' validity badge and LaTeX preview — RESOLVED 2026-08-06

**Resolved** by [PRD-38](../prds/prd-38.md): a `value` section of
`kind: "expression"` renders the equation field through the shared
`chisurf/gui/widgets/expression_input.py::ExpressionInput`, so **any** view spec
now gets a formula field with the safe-AST ✓/✗ badge, the reason in a tooltip, the
typeset LaTeX preview, the names-and-functions reference and parameter discovery
— which is strictly more than the hand-written `ParseFormulaWidget` had.

`parse/widget.py` and `parseWidget.ui` are deleted; `parse/latex.py` stays, since
`equation_editor` and `expression_input` both use it.

*The point worth keeping: the gap was closed by reusing the widget that already
did it rather than re-implementing the check inside `ValueWidget`. A second
implementation of "is this formula safe" is a second answer to that question.*

## chimol: the nucleic-acid cartoon has artifacts — RESOLVED 2026-08-06

Kept for the mechanism, which generalises past this one representation.

Reported as "the backbone of the nucleic acid is offset, thus it looks like
there are sticks sticking out of the backbone". The sticks were the base
connectors, drawn correctly to the real sugar atoms while the tube ran
somewhere else -- so the three symptoms it presented as (offset backbone,
detached rings, stray spokes) were **one** fault.

The fault is a category error, not arithmetic. The nucleic trace was passed
through PyMOL-style `RepCartoonSmoothLoops` control-point averaging, which
PyMOL applies to **loops** -- because a moving average over points on a HELIX
is not a smoothing but a **contraction toward the helix axis**. A duplex C4'
trace is a helix of radius ~9 A; the shipped two 3-point passes moved it a
measured 1.68 A (max 2.43 A) off the atoms, against a tube radius of 0.4. It is
also sharply window-sensitive: `window=3` on the same structure reaches 8.3 A,
so a half-width that reads like a quality knob is a displacement knob.

Two changes, because the default was only half of it: nucleic smoothing is off
by default (`nucleic_smooth_cycles`, and the spline already smooths *and*
passes through its control points), and each base connector is now anchored to
the same array the tube is swept along instead of to the raw atom -- so no
smoothing setting can separate them again.

**Why the render test did not catch it:** it pinned `backbone_smooth_cycles` to
0 in its own config while the shipped default was 2. It rendered, and asserted
on, a configuration nobody ran. That is the second instance this week of a test
asserting a non-shipped environment into existence (the first was mouse picking),
and it is worth treating as a pattern: a test that supplies its own config is
testing the code, not the product.

## ndX: the mask event filter reads a deleted check box during start-up (2026-08-06)

`MaskDrawingIntegration.eventFilter` (`utils/mask_drawing_integration.py:427`)
asks `plot_control.mask_widget.is_drawing_enabled()` on every event it sees,
including one `Enter` on the plot canvas raised while the window is still being
built. At that moment `MaskDrawingWidget.enable_drawing_checkbox` holds a wrapped
object that has been deleted, and the `except (RuntimeError, AttributeError)`
around it logs

```
WARNING - Error checking drawing enabled state:
          wrapped C/C++ object of type QCheckBox has been deleted
```

and returns `False`. By the time construction finishes the reference is valid
again and points at the live check box, so the visible effect is limited to that
one event being treated as "drawing off" — which it is anyway, since drawing
starts disabled. What is *not* known is which object is deleted: only one
`SurfacePlotWidget` is ever constructed, and the check box the control holds at
the end is alive and is the same object the mask widget references.

**Measured, not assumed: this is not from the AutoForm panel work.** It
reproduces on a pristine `HEAD` checkout of the module — copy the tree, restore
every modified file with `git show HEAD:<path>`, put the copy first on
`PYTHONPATH` and build an `NDXplorer`; the warning appears exactly once there
too. It also appears with both AutoForm panel builders monkey-patched to no-ops,
which is what rules out the panels rather than the check box that replaced the
checkable group box.

The fix is to look the check box up by `objectName` at call time rather than
hold a reference across construction, or to install the event filter after the
window is built. Both are changes to the mask subsystem, which is why neither
was made while wrapping the panels.

## okf: the update log is ~40 % duplicated entries (2026-08-06)

`okf/log.md` holds **1977 entries of which 1180 are distinct** — 765 appear more
than once, some four times, and the repeats go back months (`chimol: sessions`,
`Parameter error estimates were wrong by √2`, `German catalogue brought to ~90 %`).
It is not one bad commit: several instances work this file at once, each inserting
at the same `## <date>` anchor and each committing a *view* of the file that
overlaps the others'.

Re-derive it before touching anything:

```python
# split on lines starting with "## " (date headings) or "* **" (entries),
# then count distinct entry bodies
```

**Not fixed here, deliberately.** De-duplicating touches ~11 500 lines of a file
that other instances are committing to *right now*, and a mechanical pass that
drops one entry by accident is worse than the duplication. It needs a dedicated
change made when nothing else is mid-edit, with the check being that the set of
**distinct** entries is identical before and after.

**One trap already paid for.** A first attempt at that pass, run casually while
doing something else, cut the file from 29 265 to 17 759 lines in one write —
because "drop exactly-duplicated blocks" is only safe if the block splitter is
right, and there is no undo for a working-tree write. It was restored from
`HEAD` (the file happened to be clean), but that was luck, not design: **build
the new content, diff it against the old, and only then write.**

## testing: `fret_trajectory`'s suite crashes the interpreter *after* every test passes

**2026-08-06.** `pytest chisurf/plugins/traj/fret_trajectory/` reports
`11 passed  [100%]` and then dies with `Fatal Python error: Bus error` (sometimes
`Segmentation fault`) during interpreter shutdown. Every test passes; the process
exit code does not, so CI reads it as a failure.

**Pre-existing, and measured as such.** It is tempting to blame the DCD port,
because the port is what made the four previously-`ValueError`-ing tests run at
all. It is not the cause: a detached worktree at the pre-port commit crashes the
same way. To re-derive it —

```bash
git worktree add --detach /tmp/wt <pre-port-sha>
cd /tmp/wt && export PYTHONPATH="$PWD:$REPO/modules/mmfdb/src:$REPO/modules/chinet:$REPO/modules/imp-tricks/src"
QT_QPA_PLATFORM=offscreen python -m pytest -q chisurf/plugins/traj/fret_trajectory/
```

**The traps in measuring it.** Both nearly sent me after the wrong thing:

- **`grep`ing for `failed` finds nothing.** The crash prints no pytest summary
  at all — the process is gone before one is written. Match on `Bus error` /
  `Segmentation fault`, or a green-looking run will read as a clean one.
- **It does not reproduce from a plain script.** A QApplication, four
  `Structure2Transfer` widgets and three model loads exit 0. It needs the
  pytest-qt fixtures, so it is a *harness* shutdown-order problem, not something
  the product does to a user.
- **No single test causes it.** `test_gui.py` minus `test_gui_interaction_process`
  is clean 5/5; that test alone is clean 5/5; the four together crash ~1/3; the
  whole directory crashes 8/8. It accumulates with how much Qt was built, which
  is why bisecting to one test id finds nothing.
- **Order matters.** `test_view_model.py` then `test_gui.py` passes; the
  alphabetical order pytest actually uses is the crashing one.

**Tried and reverted.** The Qt-free view model and the Qt atom-pair section hold
each other (`section._model` / `model.atom_pair_section`), a strong QWidget↔object
cycle collected by the GC — possibly after `QApplication` is gone. Making the
back-reference weak is defensible on its own, but it does **not** fix this: 5/5
still crash. Reverted rather than kept under a rationale that had been
disproven. Whatever holds the Qt objects past shutdown is something else; the
shared session-scoped `qapp` in `chisurf/plugins/conftest.py`, which overrides
pytest-qt's own and never tears the application down, is the next thing to look at.

## packaging: five pandas HDF5 writers outlived the `pytables` removal — RESOLVED 2026-08-06

**2026-08-06.** `pytables` was dropped on the grounds that its "only remaining
use" was the MEM sampler's posterior (commit `ffeab9f0c`). It was not: pandas
reaches for it too, and **five live call sites still do**, none of them guarded
by a `try` —

- `chisurf/plugins/burst/burst_h2mm/core/export.py:279` — `write_hdf5`, the
  **ndX-openable** export (`key="results"`, `format="table"`)
- `chisurf/plugins/burst/bid_to_analysis/__init__.py:317,322,331` — `pd.HDFStore`
- `chisurf/core/fluorescence/imaging/pixel_maps.py:699,703,713,753` — the pixel-map
  store and `add_maps_to_hdf5`
- `chisurf/core/fio/fluorescence/burst_states.py:88` — `pd.read_hdf`
- `chisurf/core/fitting/fit.py:2363` — `save_chain_to_hdf5`

**Why nobody has hit it yet, and the trap in re-deriving it.** The developer
`arm64` env still carries `pytables 3.7.0` from before the removal, so every one
of these paths works locally and every test covering them passes; the failure
appears only in an environment solved from the current manifest. Reproduce
without rebuilding anything by hiding the module from the import machinery:

```python
import builtins; real = builtins.__import__
builtins.__import__ = lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n)) if n.split('.')[0] == 'tables' else real(n, *a, **k)
import pandas as pd
pd.DataFrame({"a": [1]}).to_hdf("p.h5", key="results", format="table", mode="w")
# ImportError: Missing optional dependency 'pytables'.
```

**What it blocks, and why the fix is a scope call rather than an oversight.**
The h2mm export is not an internal cache — the pandas `format="table"` layout
*is* the interchange contract with ndX, so the two repairs are not equivalent:
re-declaring `pytables` restores the contract and costs the dependency back
(measured 0 packages while `mdtraj` was present — that is now stale and needs
re-solving, since `mdtraj` went too), whereas moving the writers to `.npz`/plain
HDF5 keeps the dependency out and **changes a file format another tool reads**,
which needs ndX checked against it first. Whichever is chosen, the guardrail is
the same shape as the one `pyarrow` needed: a test that fails when a
module-level *or* in-function `pd.to_hdf`/`pd.read_hdf`/`pd.HDFStore` exists
without `pytables` declared.

## `test/server` — three real defects fixed, 43 tests still red

**The RPC server could not build a fit at all.** ``fit_create`` resolves a model
by walking ``Model.__subclasses__()``, which only sees *imported* classes, and
the server imports none of them: measured in a fresh server process, exactly
**one** model class was reachable ("Global fit", pulled in by the fitting
machinery). Every ``fit.create`` naming a real model answered ``model 'X' not
found``. It now runs the same headless bootstrap the agent layer uses
(``ensure_experiments_registered``), which brings the count to 43, and the error
lists what *is* available.

Two more, each hidden behind the first:

* ``FitGroup`` **iterates** its data to build one member fit per dataset, and a
  bare ``DataCurve`` iterates into ``(x, y)`` tuples — so the single-dataset
  path built member fits whose ``data`` was a tuple and the first read of
  ``data.x`` failed. It takes a ``DataGroup``, one dataset or several.
* A server-created fit had the range ``(0, 0)`` and could be created but never
  run (``Improper input: N=4 must not exceed M=(0,)``). ``fit_create`` now
  initialises it from the reader's ``autofitrange``, falling back to the whole
  curve for a dataset that arrived as raw ``curve_data`` and has no reader.

Also fixed: ``fit_set_dataset`` did not accept ``fit_uid`` while the dispatcher
passes it, and ``fit_set_result_idx`` made ``fit_index`` a required positional —
so addressing either by uid, the documented way, raised ``TypeError`` inside the
dispatcher. And ``Fit.set_result_idx`` documented "clipped to the valid range"
while ``np.clip(idx, 0, len(results) - 1)`` returns **-1** for an empty deque and
then indexes it: "this fit has not been run yet" reached the caller as
``IndexError: deque index out of range``.

### What is left, and the trap in measuring it

43 failures across 12 classes in ``test_integration_lifecycle.py``. **They do not
reproduce class by class**: ``TestErrorBoundary`` passes **12/12 alone** and
fails 3 in the full file, and ``TestProxyRpcErrorHandling`` passes 6/6 alone and
fails 6 in it. The file shares one module-scoped server and client
(``_client()``) and resets only datasets and fits between tests
(``reset_state`` → ``fit__clear`` / ``dataset__clear``), so anything else a test
leaves behind is inherited by the next one. **Fix the isolation before chasing
any individual assertion** — a per-test failure here may be a previous test's
residue, and a fix verified on one class is not verified.

Three classes have been ported and pass in isolation (``TestErrorBoundary``,
``TestProxyRpcErrorHandling``, ``TestChisurfRunPattern``); the pattern for the
rest is the same. A failing call **raises** ``RemoteError`` — service errors are
carried in the JSON-RPC ``error`` member (SV-04) — and these tests still assert
``not result.get("ok")``, which never described the contract: it also passes on
success, because a result payload has no ``"ok"`` key either. Port to
``pytest.raises(RemoteError)``, and where the test only means "the server must
survive this", assert that with a following ``meta__ping``.

The whole file takes **13.5 minutes**; run one class at a time while working.

## The arm64 env's tttrlib symlinks can dangle into a deleted pixi cache

**Found 2026-08-04**, mid-session: every GUI tool stopped constructing with
`ModuleNotFoundError: No module named 'tttrlib'`, having worked minutes earlier.

The cause is not a missing install. In the `arm64` conda env,

```
site-packages/tttrlib.py          -> ~/Library/Caches/rattler/cache/envs/chisurf-<hash>/…/tttrlib.py
site-packages/_tttrlib.cpython-312-darwin.so -> …/_tttrlib.cpython-312-darwin.so
```

are **symlinks into a pixi/rattler cache environment**, and that cache directory
had been emptied — `ls <target dir> | grep -c tttr` returns 0 — while the links
remain. A dangling symlink imports as "no module", so nothing in the error says
the file is there-but-pointing-nowhere.

Diagnose with `ls -la $CONDA_PREFIX/lib/python3.12/site-packages/tttrlib.py` and
then look at the target. Stale `.bak_*` and randomly-suffixed copies
(`_tttrlib.cpython-312-darwin.so6uhgcN`) beside them are the fingerprint of an
install that was interrupted or replaced.

**Not repaired here**: another agent instance was running pixi at the time, and
re-linking or reinstalling underneath an in-flight environment solve is how one
instance breaks another's. The repair is to re-run the tttrlib editable install
for this env once nothing else is building.

**What it blocked**: the `irf_estimator` guided tour could not be walked with
`build_tools/dev_utils/check_plugin_guide.py`, so its `help.md` / `guide.json`
are written and **deliberately left uncommitted** — a GUI change is unfinished
until its render has been looked at, and this one has not been.

**Resolved by the third repair**: [PRD-82](/prds/prd-82.md) stage 2 moved every
one of these onto the columnar writer — one dataset per column, no optional HDF5
package, and with a text column *smaller* on disk than the frame file it
replaces (60.0 MB against 72.6 MB) rather than larger. It did **not** wait for a
reader for the legacy layout: that reader was written in the simulation library
and reverted as out of scope there, so files from earlier releases still need
the optional package, now behind a named `LegacyTableError`. See the storage
entry below and [PRD-82](/prds/prd-82.md).

## Test suite: what is still red after the 2026-08-04 sweep

**Where to pick this up.** The suite was run **one directory (and, for
`test/gui`, one file) per pytest process**, because a directory-wide run dies
with SIGBUS/SIGSEGV partway through and takes the failure summary — and every
later file — with it. Re-derive with the scripts kept in the session scratchpad
pattern: `python -m pytest <target> -q --tb=no -rf` per target, recording the
return code, and treat `rc=139`/`rc=134` as "this file crashed, its failures are
unknown", not as "one failure".

**Trap in taking the measurement**: run inside the **activated** `arm64` conda
env (`conda activate arm64`), not merely with its interpreter path. With the
base env activated, PIL binds to base's `libz-ng` and any test that shells out
(`test/scripts/test_scripts.py`) fails with `Symbol not found: _zng_deflateInit2`
— a harness artifact that looks exactly like a code defect. Those two script
tests pass when the env is activated properly.

**Blocked as of 2026-08-04**: `import tttrlib` fails in the `arm64` env. The
package was rebuilt as a **directory** (`site-packages/tttrlib/`, holding its own
`_tttrlib*.so` and the split `libtttrlib_*.dylib`), while the env still carries
the two symlinks of the old single-module layout — `tttrlib.py` and a top-level
`_tttrlib*.so` — both now dangling. Repair by replacing them with one link to the
package directory:

```bash
SP=$CONDA_PREFIX/lib/python3.12/site-packages          # with arm64 activated
P=~/Library/Caches/rattler/cache/envs/chisurf-*/envs/default/lib/python3.12/site-packages
rm "$SP/tttrlib.py" "$SP/_tttrlib.cpython-312-darwin.so"   # both dangle; nothing is lost
ln -s "$P/tttrlib" "$SP/tttrlib"
```

Until then every test importing `tttrlib` errors **at collection**, which
`pytest -q --tb=no` reports only as ``1 error during collection`` with no cause
— re-run the target without `--tb=no` before believing any `rc=2`.

### `test/gui` — 30 failures across 22 files, plus 5 crashes

Five files crash rather than fail, so their contents are unmeasured:
`test_gui_plots.py` (139), `test_lineplot.py` (139), `test_widgets.py` (139),
`test_gui_tool_fret_line.py` (134), `test_region_editor.py` (134). One cause of
the 139s is fixed — `get_app()` built a **second `QApplication`** per process —
and `test_gui_plots.py` gets past it, so re-measure these five first; what
remains after that is a different fault.

The rest, grouped by what they look like rather than by file:

* **Stale test doubles** — the same class already fixed in five other files: a
  widget attribute that has moved (`new_detector_le`, `load_detector_setups`),
  a value that is now read from a model rather than the Designer widget, a
  fixture whose data shape predates the loader. `test_gui_tool_pdb2label.py`
  (3, `AttributeError`), `test_init_chisurf_onboarding_wizard_import.py` /
  `test_wizard.py` (the same test, in two files), `test_updater_*.py` (2).
* **Numeric disagreement** — `test_gui_tool_kappa2dist.py` (2) and
  `test_gui_tools.py::test_kappa2_calculation_*` are the *same two* assertions
  in two files, both `assert 0.1 == 0.0`; likewise
  `test_gui_tool_tttr_histogram.py::test_load_data` and
  `test_gui_tools.py::test_histogram_load_data` (`assert 0 == 1`). Fixing the
  pair fixes four entries. **Note the duplication**: `test_gui_tools.py` looks
  like a rewritten copy of the three `test_gui_tool_*.py` files, and
  `test_info_json_uppercase.py` was a byte-level subset of `test_info_json.py`
  (deleted). Check for a duplicate before debugging anything here.
* **`test_rate_matrix.py` (4) — diagnosed, deliberately not fixed.** Each cell
  of the grid is now a container `QWidget` holding a *fix checkbox plus* the
  spin box, with the spin boxes kept in `RateMatrixSection._spins[(i, j)]`; the
  tests still call `table.cellWidget(i, j).setValue(...)`, from when the cell
  *was* the spin box, and get `'QWidget' object has no attribute 'setValue'`.
  Left alone because `chisurf/gui/autoform/sections/rate_matrix_section.py` had
  **uncommitted changes from another instance** while this was measured — the
  tests belong to whoever is changing that widget. Port them through `_spins`,
  not through `cellWidget`.
* **Widget behaviour** — `test_proteinmc_mdl.py` (3),
  `test_parameter_prior_widget.py`,
  ~~`test_parameter_table_actions.py`~~ (fixed 2026-08-05: the test asserted, as
  its *precondition*, the very warning that
  `FittingParameterGroup.finalize` had deliberately stopped emitting — a
  parameter without a controller is the ordinary case. Rewritten to assert
  silence in both halves),
  `test_image_section_axes.py`, `test_plot_construction.py`. These are the ones
  most likely to be *real* defects rather than stale tests, and the rate-matrix
  four are the biggest single cluster.

`rc=5` (`test_save_button.py`, `test_style.py`, `test_gui_chisurf_tcspc.py`,
`test/repro/`) means **no tests collected** — empty or fully skipped, not a
failure.

### A parameter that starts exactly on its bound cannot move

Not a test failure but the reason one "fix" was reverted, and worth knowing
before bounding anything. `leastsqbound` maps a bounded parameter through
`sin` (two-sided) or `sqrt(x**2 + 1)` (one-sided); both are **quadratically
flat** where they meet the bound, so a parameter sitting *on* its bound has a
derivative of zero with respect to the coordinate MINPACK varies. Its Jacobian
column comes back empty however strongly the residuals depend on it: at
MINPACK's default `1e-3` internal step, a background bounded at `bg >= 0` and
started at `0` moves by **5e-7**.

Nudging the start inward was tried and reverted. The offset has to be ~0.1 in
internal coordinates to give a usable derivative, and for a two-sided bound that
is 0.25% of the *whole box* — for a rate bounded at `(0, 1e9)` it starts the fit
at 2.5 million, which broke three PDA rate tests
(`test_pda2c_time_binned.py` x2, `test_pda3c_rates.py`). A scale-aware offset
small enough to be safe is too small to help. Any real fix has to change the
*transform* (or use an optimiser with genuine box constraints), not the start.

## 2D-FLCS prints a pyqtgraph teardown traceback when its window closes

**Found 2026-08-04**, while walking the new 2D-FLCS guided tour headlessly.

Closing `FlcTwoDTool` prints, two to four times,

```
RuntimeError: wrapped C/C++ object of type QComboBox has been deleted
  ... ViewBox.forgetView -> updateAllViewLists -> updateViewLists
  ... ViewBoxMenu.setViewList:  current = c.currentText()
```

The chain is entirely inside pyqtgraph: a destroyed `ViewBox` runs a
`destroyed`-signal lambda that rebuilds **every** view list, and reaches a
`ViewBoxMenu` whose combo box Qt has already deleted. Nothing of ours is on the
stack.

**Not caused by the guided tour**, though the tour makes it louder. Measured by
disabling `GuidedTour._unfold` entirely and walking the tour again: the traceback
still appears (2×). With the tour's extra `processEvents` it appears 4×, because
more deferred deletions get to run before the interpreter exits. Other
pyqtgraph-backed tools (H2MM) do not reproduce it — 0 occurrences.

Harmless in the sense that matters: it is an exception inside a Qt slot at
teardown, printed and swallowed, with no state left broken. Left alone because
the fix belongs in pyqtgraph's `ViewBoxMenu`, and the plugin is scheduled to move
off pyqtgraph anyway ([PRD-64](../prds/prd-64.md), [chiplot](../subsystems/chiplot.md)).

## chimol: every scene rebuild refits the camera — RESOLVED 2026-08-04

**Found 2026-08-04**, while photographing `cartoon_side_chain_helper` — the
framing kept resetting between the "off" and "on" shots.

`MolView._update_view(fit_camera=True)` is the default, and a rebuild is what
colouring, a representation change, a label, a bond edit and **every `set`** all
trigger. Measured on 148L: `zoom resi 20-26` puts the camera distance at
**1.26**, and the next `set` of *anything at all* puts it back to **5.0**. So
framing a binding site and then adjusting a stick radius loses the framing — in
a viewer, which is a serious thing to get wrong. PyMOL moves the camera only for
a camera command (`zoom`/`orient`/`center`/`reset`) or a load (`auto_zoom`).

**Attempted and reverted**: flipping the default to `False` and passing `True`
from the three load paths (`set_structure`, `set_coordinates`, `add_volume`) is
*not* sufficient, and the suite says so — `test_ray_command.py::
test_every_representation_reaches_the_image` then traces an **empty image** for
all four representations. `ray` and the headless load path both depend on this
refit to frame at all: at the point the load paths call it the scene has no
geometry to measure, so the first rebuild that *does* is what actually frames.
An `auto_zoom`-once flag (frame on the first build with geometry) does not fix
it either, because in that test the window is never shown and `_update_view`
returns early with no renderer.

The real fix moves framing to where a structure is loaded and the scene is
built, rather than flipping a default — six call sites had already been patched
to `fit_camera=False` one at a time, which is the signature of a default that is
wrong but load-bearing. Left as it was, because a half-verified change across
~64 call sites in a viewer is worse than a known defect.

Six call sites already pass `fit_camera=False`; the ones that matter for a user
are colouring, representations and `set`.

**Resolved 2026-08-04, and the revert was for the wrong reason.** The default is
now `False`, with the three load paths passing `True` — the change described
above as insufficient. It was not insufficient; the `ray` failure it was blamed
for was the **aspect** defect two entries down, not the framing. A window that
is never shown has no viewport, `_aspect()` read 1/30 off the one-pixel column
that left, and the camera went thirty times too far away; refitting on every
rebuild hid that, because the last rebuild landed after the widget had a size.
With `_aspect()` fixed, `test_ray_command.py` passes with the default flipped
and no other change.

Two things the flip needed on top: `_rebuild_after_coordinate_change` reuses
`set_structure` — the *load* path — to re-derive after an edit, so `h_add` on a
zoomed-in residue still jumped out until `set_structure`/`set_coordinates` grew
a `fit_camera` argument; and nothing re-derived the distance on a **resize**,
which the old behaviour had been covering by accident, so `resizeGL` now
re-frames when the viewport's shape changes (distance only — the clips carry a
user's `clip` adjustments — and by *scaling* the distance rather than
recomputing it, since the scroll wheel moves the camera without changing what
was framed).

Measured: 12 of 12 ordinary commands threw the framing away before, 0 of 12
after. `test_camera_persistence.py` pins both halves — what must not move the
camera, and what must.

**The lesson is about the revert, not the bug.** "Attempted and reverted, with
why" was the right thing to record and is what made this cheap to re-open — but
the recorded *why* was a symptom seen through another defect. When an attempt
fails, the note is worth more if it says what was measured than what was
concluded.

---

## Stale tests left behind by finished refactors

**Found 2026-08-03**, while running the guard suites for the PSF calculator's
guide/help and export work. Six failures in `test/gui` and `test/server` that
have nothing to do with that change, and are not flaky — they fail on an idle
machine, on paths with no uncommitted edits, so they are committed breakage
rather than another instance's work in flight.

* `test/gui/project/test_info_json.py::test_info_json_uppercase` and its
  duplicate `test_info_json_uppercase.py` monkeypatch
  `filter_widget.load_detector_setups`. That method moved off the widget and
  became the module-level `chisurf.core.data_io.detector_setups.load_detector_setups`
  in the SV-01 Qt-free split; the tests still patch the bound method, so they
  raise `AttributeError` before asserting anything.
* `test/gui/settings/test_acquisition_simulation_autoform.py` references an
  undefined `TestWidget` (`NameError`) in three tests.
* `test/gui/test_mmfdb_picker.py::test_shared_client_adopts_chisurf_login_session`
  expects the shared client's token to be `None` and finds one.

Not fixed in the change that found them: each is a test that a *completed*
refactor left pointing at the old shape, and repairing one means deciding what
the refactor intended it to assert — which belongs with whoever owns that
refactor, not with a change to a calculator plugin. Recorded rather than
silently skipped, because a red suite that everyone steps over is how the next
real regression gets missed.

Fixed in passing, since they were unambiguous and one line each: the
`node_editor` package promising names in `__all__` it never bound, the
`ReentrancyGuard` that never guarded, `to_elementary` keeping the keys it was
asked to skip, a missing `Path` import, and three stale
`serialize_reader_state` mocks.

## test/server: the shared-server integration file errors and then hangs

**Found 2026-07-28**, while test-gating an unrelated proxy fix (RF-722).
`pytest test/server` never finishes: `test_integration_lifecycle.py` runs its
module-scoped `ChiSurfServer` in-process, and most of its tests error in
*setup* with

```
chisurf.startup.services.AppStartupError: service 'mmfdb' did not become ready
within 5.0s
```

after which the run stalls indefinitely at
`TestParameterLifecycle::test_linked_info` (>180 s, no output). The 5 s
`ready_timeout` in `chisurf/startup/services.py` is the visible trigger and it
is load-dependent — the same tests pass when the machine is idle, so a machine
running several suites (or several agent instances) turns it red. Which of the
two symptoms causes the other is not yet established: a server whose startup
raised may leave the ZMQ socket half-alive, which would explain a later call
that never returns.

Not fixed in the change that found it: the failure is in the shared server
fixture, not in anything that change touched (nothing in the file calls the
insertion routes it altered), and diagnosing a startup-timeout-plus-hang is its
own change. The proxy behaviour itself is covered by `test_proxy.py` and
`test_proxy_integration.py`, which are green.

**Update 2026-07-28 — the startup half is fixed; two other faults were behind
it.** The `mmfdb` stage now declares `"ready_timeout": 30` in
`chisurf/startup/services.d/10_mmfdb.json`. Measured, the stage costs **3.8 s**
on an *idle* machine for its first import, so the 5 s default was never a budget
— it was a hang-detector consuming 76 % of itself on a good day. Raising it
costs nothing in failure latency: `_run_service` records the exception and sets
`ready_event` on the way out, so a service that *fails* still surfaces at once
and only a service that truly *hangs* waits out the budget
(`test_app_startup_manager_reports_background_failure_without_waiting` pins
that, and `test_config_background_services_budget_a_cold_import` stops a new
background stage from silently inheriting the bare default). The server now
constructs, and `TestProxyLifecycle`/`TestLargePayload` run to completion in 8 s.

What that uncovered, both still open:

1. **The fit tests ask for a model that does not exist.** Every
   `client.fit__create(..., model_name="TCSPC")` returns `model 'TCSPC' not
   found`. `fit_create` (`chisurf/server/services/fits.py:410`) resolves a model
   by walking `Model.__subclasses__()` for one whose `name` matches; after
   importing `chisurf.core.models` the only reachable names are `Global fit` and
   `Model name not available`, so no spelling of that call can succeed. Two
   faults stacked: the name is stale, *and* the subclass walk only sees models
   some other import happened to pull in.
2. **The intended skip guard is dead.** `TestParameterLifecycle._setup` writes
   `if not ft.get("ok"): pytest.skip(...)`, but since [SV-04](../specs/assessment.md#sv-04)
   moved service errors into the JSON-RPC `error` member, `fit__create` *raises*
   `RemoteError` instead of returning `{"ok": False}`. So the guard never runs
   and 7 tests fail where the author meant them to skip. Do **not** patch the
   guard to swallow `RemoteError` — that would hide finding 1 rather than fix it.

**The hang is still unexplained**, and it is not specific to `test_linked_info`:
with the timeout raised the run now stalls in the same class at
`TestParameterLifecycle::test_set_bounds` (>5 min, no output), while
`test_set_value` and `test_set_fixed` — which reach the identical `_setup` —
fail fast a moment earlier.

**To close it:** give `fit.create` a model lookup that does not depend on what
happens to have been imported (an explicit registry, as the model/UI split
already needs), fix the test's model name, then give the client a receive
timeout so the remaining stall is a failure with a traceback instead of silence.

**Update 2026-08-03 — the model name is not the only blocker.** Driving the
server directly, with `chisurf.core.models.tcspc.lifetime` imported first so
the subclass walk can see it, both real names (`"Lifetime "` — note the
trailing space — and `"Lifetime (new)"`) get past the lookup and then fail in
`fit.create` itself with

```
'tuple' object has no attribute 'x'
```

so a dataset loaded over `dataset.load` with a `curve_data` payload does not
arrive as something `FitGroup` can build a fit on. Fixing the test's model name
alone would therefore turn a wrong error into a different wrong error. The
whole-suite symptom is unchanged: `pytest test/ --ignore=test/gui` still stalls
at `TestParameterLifecycle::test_set_bounds` (main thread blocked in
`zmq_ctx_destroy` → `ctx_t::terminate` → `mailbox_t::recv`, i.e. a context
being torn down while a socket still holds queued data), and run on its own the
class fails fast instead. So the hang needs state from the tests that precede
it.

## fitting over a genuinely remote server still has a 5-second deadline (2026-08-03)

`FittingClient.run_fit` no longer crosses the socket when the server is embedded
in this process -- which is the GUI's normal case, and where the bug actually
bit: the fit ran on the server thread, the GUI thread blocked in `recv`, and the
`fitting_timeout_ms` deadline (5000 ms, `settings.mmfdb`) expired mid-fit and
disabled RPC for the rest of the session:

    FittingClient: disabling RPC after transport failure in 'fit.run':
    timeout: no response within 5000ms

A real two-state MFD fit takes about 130 s, so it lost that race every time.

**Still open for a genuinely remote server.** Any fit longer than the deadline
will do the same thing over the wire, and the blocking call freezes the GUI for
its duration regardless. The right shape is almost certainly a job submitted to
the server's `JobManager` with progress arriving over the event bus -- the
machinery already exists for sampling (`_watch_sampling_job` polls exactly that
way). Not attempted here because this tree has no remote server to test against,
and a fix that cannot be run is a guess.

## quest: the plugin's RPC layer targets a backend the package does not have

**Found 2026-07-28.** Starting the GUI logs

```
Failed to register services for plugin 'quenching_estimator'
ModuleNotFoundError: No module named 'quest.backend'
```

`chisurf/plugins/quenching_estimator/` is deliberately a thin shell: its
`rpc/services.py`, `api/contract.py` and `api/client.py` all forward to
`quest.backend.services` / `quest.backend.contract` so the CLI, the web backend
and ChiSurf share one implementation of the sixteen `quest.*` methods the
manifest declares. That backend package does not exist -- not in the checked-out
`modules/quest`, and not on any of its branches (`git ls-tree` over `master`,
`main`, `dev`, `devel`, `development`, `chisurf-pin` shows only `quest/lib` and
`quest/settings`). So every `quest.*` RPC is unreachable, and the plugin's own
tests for the contract cannot run either. The GUI entry point still works: it
imports `quest.gui` directly and never touches the backend.

**To close it:** write `quest/backend/{contract,services}.py` in the quest
repository, over `quest.core` / `quest.api`, matching the schemas already in
`chisurf/plugins/quenching_estimator/manifest.json` (that file is the contract's
written form). It belongs there, not here: a second implementation ChiSurf-side
is exactly the `LAY-01` duplication the shell was built to avoid. Until then the
failure is a logged registration error, not a crash.

## packaging: the LaTeX converter has no Python 3.12 conda build

**Found 2026-07-28.** `chisurf/gui/widgets/models/parse/latex.py` renders a
parse-model formula through the third-party `latexify` converter. The
conda-forge package for it stops at Python 3.11, so it cannot go into the
recipe's `run:` list, and the module-level `from latexify import ...` therefore
made the module -- and with it the whole parse-model widget -- unimportable in
the released conda package. Only a pip install ever had it.

The import is now inside the conversion function, next to the `except` that
already fell back to `_convert_python_expression_to_latex_fallback`, the in-tree
AST converter. A conda install renders through the fallback instead of failing:
it covers the operators the parse models use, and is less complete than
`latexify` for anything exotic.

**To close it:** either a Python 3.12 build lands on conda-forge (then declare it
in the recipe and drop the fallback path from the hot path), or the in-tree
converter grows to full parity and the dependency goes for good -- it is one
`ast.NodeVisitor`, so the second is the more likely end state.

## RESOLVED — chimol: large integrative models, and the "fix" that killed them

**Opened and closed 2026-07-27.** The nuclear pore complex was the case that
showed it.

| Entry | Beads | Load before | Load after |
| --- | --- | --- | --- |
| `PDBDEV_00000010` (one spoke) | 29,273 | 8.7 s → 4.3 s | **0.36 s** |
| `PDBDEV_00000012` (eight spokes) | 234,184 | **430 s**, ~11 GB | **1.6 s**, 0.7 GB |

The cost was never the reader — `ihm` reads the 31.5 MB file in well under a
second. It was **a cartoon splined through beads that have no backbone**: 234k
beads become thousands of short chains, each fully splined, framed and extruded.
A bead stands for a *range* of residues, so the ribbon was meaningless as well as
expensive.

**The trap, explained.** Switching beads to the sphere representation — the
correct depiction, and what `set_rmf_data` already did — appeared to make the
entry *die silently*. It did not die. `ball_mask` was left all-**false** by the
mmCIF path (only the RMF path set it), and the sphere branch's fallback for "no
selection" is a **sparse sampling of 50 points along the chain**. The viewer drew
fifty dots and called it a nuclear pore. Nothing raised, because nothing was
wrong as far as any single line of it was concerned.

**What landed.** A bead model is now recognised in the viewer, so every reader
agrees on it: all beads selected, spheres on, cartoon and trace off, no bond
inference, per-bead radii carried through `set_coordinates` and scaled with the
coordinates. Past 20,000 beads the depiction is **sphere impostors** — one vertex
each, shaded as a sphere in the fragment shader — instead of ~160 vertices of
merged mesh per bead, with the impostor's world radius projected to a sprite size
so it follows the camera. Pinned by `test/test_bead_model.py`.

**IMP RMF support landed on 2026-07-28** — and the shape of what was wrong is
worth keeping. RMF was not missing the bead rule because nobody had written it
for RMF; it was missing it because RMF had *its own route into the viewer* and
therefore could not receive anything the common route learned. Measured: one
global radius for every bead, decimation instead of impostors, and hierarchy
check boxes that moved nothing. All of it silent. The fix was to remove the
route, not to duplicate the rule — see the log for that date.

**Still open from that thread:** interior culling (`_get_surface_atom_mask`
exists and is unused), dynamic LOD on camera motion (the draft/settle mechanism
from the trajectory work generalises), and depth-cue fog.

---

## chimol: three atom dtypes — RESOLVED 2026-07-28

Chimol carried **three** transcriptions of "the atom dtype every reader
produces", no two of them the same: a six-field one in `io/beads.py` for the
PDB/mmCIF/RMF readers, a twelve-field `_MDTRAJ_ATOM_DTYPE` for trajectory
topologies, and a twelve-field `PSEUDOATOM_DTYPE` in `cmd/editing.py`. Two of
the three carried a comment asserting they matched the core's `keys_formats`.

All three are gone. `chimol/io/atoms.py` (renamed from `beads.py`, since it now
owns the atom row and not only the bead) imports
`chisurf.core.fio.structure.coordinates.atom_dtype`. Rows are built by field
name (`atom_row(**fields)`) rather than as twelve-long positional tuples.

**The interesting part was not the duplication but what it hid.** The canonical
dtype had `chain` as `|U1`. An mmCIF asym id runs `A..Z` then `AA`, `AB`, …, so
on the eight-spoke nuclear pore 518 of 544 chains needed two characters and
every one was stored as its first letter: **544 chains became 26**, silently.
`chain AB` selected the whole of A and colouring by chain painted twenty
molecules alike. The field is `|U4` now. Widening it made the PDB *writer* a
hazard in turn — `%1s` is a minimum width in Python, not a truncation, so a
two-character id would have shifted every following column — so the writer uses
`%1.1s` and warns, naming the chains whose identity a PDB file cannot carry.

**`modules/quest` still carries two more copies of that PDB format string**
(`quest/lib/io/PDB.py`, `quest/lib/structure/Structure.py`), with the same `%1s`
that does not truncate. They are deliberately untouched: quest builds its own
atom arrays, so the core's widened `chain` cannot reach them, and quest is
slated for deprecation rather than repair. If any of it is kept, the writer goes
with the rest of the duplication — it should not be ported forward as it is.

---

## chimol: a ray-traced mesh is shaded twice, and comes out muddy

**2026-08-03.** Mesh vertex colours arrive at the tracer with ambient occlusion
*and* a cast shadow already multiplied in — `Geometry.occlusion` says so in its
own docstring ("Already multiplied into `colors`") — and the tracer then applies
its own lighting and its own shadows on top. Measured on the 148L cartoon: the
bake costs 44 % of the vertex colour (mean 0.567 → 0.318), and the traced image
is mean 33.3 against 54.5 for the same scene built with baking off. The picture
reads as muddy rather than as shaded, and the baked shadow comes from a *fixed*
light direction that need not be one of the ray lights.

**Not fixed here, and why the obvious fix is wrong.** Dividing the bake back out
of the colours is inexact: the shadow is folded into the `occlusion` channel with
a different constant from the AO (`shadow_darkness` 0.45 vs `darkness` 0.7), so
recovery is off by a mean 0.03–0.05 and up to 0.44 on individual vertices — a
colour error that looks like a colour, not like a bug. The right fix is to carry
the **base** colour plus the occlusion channel and let each backend apply it,
which changes the `Geometry` contract and therefore the GL backend too, and needs
verifying in a real window (offscreen creates no GL context). Worth doing; it is
its own change.

The depth-cue half of the same darkness *was* fixed — see
[the parity tracker](/plugins/pymol-parity.md).

---

## chimol: five camera-framing tests are red

**2026-08-03.** `test_camera_framing.py` fails five ways, in isolation and in the
full run, and identically at `HEAD` with no working-tree changes:
`test_distance_follows_the_field_of_view[True/False]`,
`test_zoom_fits_every_atom_not_just_the_trace`, and
`test_camera_distance_matches_pymol[True/False]`. The measured distance is ~30×
the expected one (41429 against 1381), which points at a scale factor — chimol
scales coordinates by `_scale_factor` (default 10) — rather than at the framing
rule. Recorded here because it was found while working on something else and is
not that change's to fix; the assertions encode PyMOL's
`d = R / tan(fov/2)` and are worth keeping.

---

## chimol: a sphere impostor occludes as a flat disc (RF-522)

**2026-07-27.** The impostor is exact in silhouette and in shading, but every
fragment is written at the depth of the bead *centre*, because the fragment
shader assigns no `gl_FragDepth`. Where beads overlap each other or other
geometry, the nearer centre takes the whole disc instead of the two surfaces
intersecting — by up to one bead radius, which on the nuclear pore is tens of
ångström. Below `balls.impostor_min_atoms` the same beads are meshes and
intersect correctly, so the two depictions do not match across the threshold.

**Why it is not simply fixed.** Writing `gl_FragDepth` in *any* branch of a
GLSL 1.20 shader disables early-Z for every draw that shader serves — and this
one serves the cartoon and every mesh in the scene, which is the path a lot of
work has gone into keeping fast. The correct fix is a **separate shader program
for impostors** (its own vertex/fragment pair, the depth write confined to it),
not a branch in the shared one. Documented as a limitation in the viewer guide
in the meantime.

---

## chimol: `show` and `hide` say nothing on an empty viewer

**2026-07-27.** `spectrum`, `zoom` and `color` now answer "nothing is loaded" on
an empty viewer instead of describing a molecule that is not there, because they
all resolve a selection first and the resolver raises. `show spheres` and `hide
everything` do not go through the resolver — they go through
`RenderingMixin._toggle_representation` — so on an empty viewer they still
silently do nothing, which is the same class of wart one step quieter.

Not fixed with the others only because `rendering.py` had concurrent edits from
another working copy at the time; it is a two-line guard in
`_toggle_representation`.

---

## chimol: a point glyph's configured size never reaches the renderer

**2026-07-27.** `QtGLRenderer._geometry_to_draw_data` computes `size` from
`geom.meta["size"]` and then does not pass it to `_DrawData`, so every point
glyph draws at the 4-pixel default: `dots.size_px`, the overlay sizes, and the
`px_mode` flag that distinguishes a pixel size from a world one are all dead
configuration. Sphere impostors are unaffected — they carry a per-vertex radius,
which does reach the shader.

Not fixed in the change that found it because the fix changes the size of every
point glyph in the application at once, and the render fixtures would all need
re-inspecting; that is its own change, with its own before/after images.

---

## mmfdb: the shipped curated seed is two schema versions behind

**2026-07-28.** `tests/test_mmcif_database_resolver.py::test_packaged_seed_is_curated_and_on_the_current_schema`
is red at mmfdb `HEAD`: the packaged `data/sample_management.db` is stamped
schema **45** while `schema.SCHEMA_VERSION` is **47**. Since PRD-19 removed the
migration waterfall a stale seed is not fully migrated forward — missing
*columns* are added, stale *table structure* is not — so an unconfigured first
run copies a seed the current code cannot fully write to. The regenerator is
`build_tools/regenerate_curated_db.py` in chisurf (`--replace`).

Not fixed here because that script had concurrent edits from another working
copy at the time; regenerating and re-committing the binary seed belongs to
whoever bumped the schema.

---

## examples: a shipped example imports a package that moved, and no test reaches it

**2026-07-29.** `examples/fdb_burst_selection_roundtrip.py` opens with
`from chisurf.core.mmfdb import FluorescenceDatabase, BurstPipeline`. That
package no longer exists — MMFDB lives in `modules/mmfdb/src/mmfdb/` — so the
example fails on its second import line. It has failed silently ever since the
move because [PRD-46](/prds/prd-46.md)'s script runner
(`test/scripts/test_scripts.py`) discovers `examples/scripts/*.py` only:
anything in the `examples/` root is outside the glob and is never run.

Two separate repairs, which is why neither landed with the flrCIF alignment fix
that found it: the example needs porting to the current `mmfdb` API and a
verifying run against the `bh_spc132_sm_dna` SPC file it references, and the
runner's discovery needs widening (or the example needs moving into
`examples/scripts/`) so the next one cannot rot unnoticed. The other five root
examples at least resolve every top-level import; whether they still *run* is
exactly what nothing checks.

---
type: Reference
title: Known issues & recurring gotchas
description: Curated open functional bugs and cross-cutting engineering pitfalls distilled from working bug logs.
resource: chisurf/
tags: [bugs, gotchas, pitfalls, gui, qt]
timestamp: '2026-07-06T00:00:00Z'
---

# Purpose

This concept distills durable content out of ad-hoc working bug logs (formerly in
a top-level `notes/` folder) so the knowledge survives without keeping a raw log
in the tree. Two things are worth preserving from those logs: **functional bugs
that were still open** when the log was last touched, and **recurring root-cause
patterns** that keep re-biting across subsystems.

This is not a live issue tracker. Architecture-divergence items (spec violations,
review-found correctness bugs, schema/manifest drift) live in the
[cleanup backlog](/specs/assessment.md); this page is for runtime/functional
behaviour. The open list below was captured around **June 2026** — re-verify each
against the current tree before acting, as some may already be fixed.

# Recurring gotchas (durable — verify before you re-break them)

These are the patterns; each caused more than one bug.

- **pyqtgraph draws a 2-D array transposed.** `ImageItem`'s default axis order
  is column-major: axis 0 becomes *x*. Everything else in ChiSurf — numpy, the
  ROI subsystem, the AutoForm `image` section's own markers, click picks and
  rectangle gate, and its 3-D path — treats `(x, y)` as `(column, row)`. The
  mismatch is invisible on square or symmetric data and puts every marker and
  every drawn region on the transposed pixel otherwise. Set
  `axisOrder="row-major"` on any new `ImageItem`/`ImageView`; the array handed
  around is unchanged either way, so masks keep their `(row, col)` meaning.
- **Several pyqtgraph views destroyed together abort the process.** `ViewBox`
  registers itself in a process-global `NamedViews` dict and, when destroyed,
  walks every other registered view to rebuild its menu — reaching one whose
  `QComboBox` is already gone. At interpreter exit this aborts *after* the last
  test passed: a green run with a non-zero exit code, and no pytest summary to
  explain it. Keep at most one long-lived view per test module (module-scoped
  fixture) and build the rest under `qtbot`, which deletes them while Qt is
  still alive.

- **Collecting a TCSPC model widget between tests is a bus error.** Same
  signature as the entry above — every test prints a dot and then
  `Fatal Python error: Bus error` — but a different subject and a different
  trigger: `Fit(model_class=GaussianModelWidget, …)`. Building *five in one
  test* is stable; building one per test across five tests aborts on roughly
  four runs in five, so it is the per-test garbage collection of the fit and its
  Qt children (with the session `QApplication` still up), not the count. Not
  root-caused. Until it is, hold every such fit in a module-level list and never
  release it — see `test/gui/models/test_distance_widget_append.py`.

- **Qt Python-wrapper vs C++ lifetime.** `RuntimeError: wrapped C/C++ object …
  has been deleted` on window close. The Python wrapper outlives the destroyed
  C++ widget; a shared `_new_closeEvent` in `chisurf/gui/misc_helpers.py` calls
  through to a dead object. Any close-event / save-window-state handler must
  guard against an already-deleted widget (`sip.isdeleted`). Recurs across
  plugins (microtime histogram, MLE lifetime wizard).
- **`@property`-backed reader settings silently drop on serialize.**
  `serialize_reader_state()` / `_reader_settings_dict()` iterate
  `reader.__dict__` and skip `_`-prefixed keys. A `@property` (e.g. `is_vv_vh`)
  is not in `__dict__`; only its private backing field is, and that is filtered
  out — so the setting fails to persist across restart with no error. Any new
  `@property` on an `ExperimentReader` needs the serializer to look for the
  public property. PRD-40 aims to make AutoForm/`.view.json` own persistence and
  remove this class of bug.
- **`DataCurve[key]` returns 5 items, not 4** (since masks were added). Every
  consumer (`calculate_weighted_residuals`, `DataCurve.save`) must unpack 5. A
  `Curve.__getitem__` regression that returned `y` where `x` was expected
  produced huge residuals / wrong χ² rather than a crash — easy to miss.
- **Refresh derived outputs explicitly.** Updating input parameters and plots
  does *not* refresh derived/output parameters. After any fit switch or parameter
  edit, call `model.finalize()` and refresh the output-parameter controllers.
- **Propagate anisotropy calibration as a unit.** `g_factor`, `l1`, `l2` must
  travel together reader → dataset/group metadata → model kwargs → parameters;
  propagating `g_factor` alone was a repeated bug. Values may be scalar floats or
  parameter objects — handle both (no `.value` on a float). Coerce NaN/inf to
  finite before constructing parameters (non-finite calibration caused Windows
  access-violation crashes on project load). Steady-state anisotropy uses
  `r = (VV - VH)/(g*VV + 2*VH)` and should prefer dual-channel VV/VH.
- **pyqtgraph text overlays + threading.** Before `setHtml`/`updateTextPos` on a
  `TextItem`, verify both it and its backing `QGraphicsTextItem` are alive
  (`sip.isdeleted`); dangling items crash on Windows. Prefer plain `setText`.
  Qt-owning objects (MCP server, GUI executor) must be created/owned/destroyed on
  the main thread.
- **macOS ARM64 text rendering.** Emojis/special symbols in UI strings can hit
  CoreText paths that SIGBUS (`EXC_ARM_DA_ALIGN`); keep UI strings ASCII-safe on
  that platform. (Note this tension with the general emoji-toolbutton preference.)
- **Keep hot-path logging at DEBUG.** Logging a full DataFrame repr / per-redraw
  traces at INFO on every recompute was itself a major interactive slowdown.
  `resizeEvent` should rescale cached data (debounced), never re-bin/recompute.
- **A GUI log handler must batch, be bounded, and never touch the widget per
  record.** `QTextEditLogger` sits on the root logger, so *any* subsystem's
  logging pays its cost. Writing to the widget from the logging thread is
  undefined behaviour (`QBasicTimer` warnings, crashes); inserting one row per
  record pays a relayout plus `scrollToBottom` each; and running the O(rows)
  console filter per record makes a burst O(rows^2) — a data load logging a few
  hundred records took seconds. Records are queued and applied in batches on the
  GUI thread (one wake-up per batch, ~50 ms rate limit, newest-only for the
  status bar), the console is capped at `LogListWidget.max_rows`, and the filter
  pass is debounced and skipped entirely while no filter is active.
- **File-save dialogs seed from the data location.** Default the save dir to the
  loaded data file's folder / `cs.working_path` (not Qt's last-used dir) and
  update `cs.working_path` after save. `chisurf/gui/main.py` "Save Fit" is the
  reference.
- **Plugin menu-callback contract.** The menu system `exec`s a plugin file with
  `__name__ == "plugin"`; without an explicit `if __name__ == "plugin": load()`
  guard the plugin silently does nothing.
- **Plugin `.ui` paths must be plugin-relative and existence-checked** (cached
  resolver) before `uic.loadUi`; stale relative paths break silently after folder
  moves. Contract tests cover this — keep them.
- **Batch/action dispatch must not swallow per-item exceptions.** A batch
  `fit.add` that swallowed callback errors reported success while creating no
  fits. Route default actions to `cs.current_fit`, not fit index 0.
- **macOS QComboBox popups render translucent.** Node/embedded combos need an
  explicit opaque palette + `setAutoFillBackground(True)` and cleared
  `WA_TranslucentBackground` on the view; QSS `QComboBox QAbstractItemView`
  alone does not fix the popup window. (Seen in the light-path node editor — see
  [Light Path Simulator](/plugins/profiles/lightpath-simulator.md).)

# Open functional issues (re-verify against current tree)

Grouped by area; captured June 2026.

**The generated manual still names the retired emcee dependency at its source
(2026-07-28).** `docs/manual/*.rst` are generated from
`docs/_old_manual/manual.docx` by `pixi run -e docs docs-manual`. The three
places that said ChiSurf "uses emcee" (and showed `method: emcee` in the settings
listing) were corrected **in the generated RST**, because the sampler is now
in-tree; the `.docx` still says it, so a regeneration reintroduces the wrong
statement. Fixing it properly means editing the binary source or retiring that
manual page in favour of `docs/concepts/parameter_uncertainty.md`, which now
covers the same ground.

**Anisotropy now follows Schaffer/Eggeling throughout (settled 2026-07-27).**
`r = (Fp - G Fs) / ((1 - 3 l2) Fp + (2 - 3 l1) G Fs)` with **G = S_par/S_perp**,
the ratio a paper quotes and the one tttrlib's estimators already took. Four
sites moved together — `compute_g_factor_perrin` (was returning the reciprocal),
`anisotropy_from_integrals`, `LifetimeModel._tcspc_rt_curves`, and the
`vm_rt_to_vv_vh` generator (now divides the perpendicular channel by G). The
chain closes: the generator round-trips exactly at every G, the calibration's
output feeds its own consumer, tttrlib's formula and the VM combination
`vv + 2 G vh` and all three return the truth. That also retires the two splits
recorded here earlier — the cross-repo one and the VM one — without touching
tttrlib or the five VM call sites.

**The l1/l2 parameterisation is settled too (2026-07-27).** It was the
generator that was out of step, not the correction. `vm_rt_to_vv_vh` built an
ideal pair and mixed it with a 2x2 matrix (Koshioka 1995), which is a different
meaning for l1/l2 and does not invert the Schaffer correction. tttrlib states
the right one in its own forward model (`DecayFit23.cpp`:
`x_vv[2] = r0 (2 - 3 l1)`, `x_vh[0] = 1/g`, `x_vh[2] = r0 (-1 + 3 l2)/g`):

    VV = vm (1 + (2 - 3 l1) r),    VH = vm (1 - (1 - 3 l2) r) / G

Substituting that into `(sp - G ss) / ((1 - 3 l2) sp + (2 - 3 l1) G ss)` makes
numerator and denominator collapse to `3 vm (1 - l1 - l2) r` and
`3 vm (1 - l1 - l2)`, so the round trip is exact for any l1, l2 and G. The
generator now uses it, and the round-trip test covers a non-unit G and non-zero
mixing together — the combination that exposed the old one (0.274 and 0.318
against 0.300).



**Found 2026-07-27, not fixed: the PCH settings panel is clipped at its right
edge.** `chisurf/plugins/pch/gui/tool.py` puts the settings form in a
`QScrollArea` with `setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)`, and the
form is wider than the splitter gives it, so the File / Channels / Bin Time /
Micro Time editors run past the window edge and their right-hand ends are
unreachable — visible in any screenshot of the tool at its default 1000×650. The
fix is a layout one (let the form shrink, or give the splitter a sensible initial
size, or stop suppressing the scroll bar), not a one-liner, so it was left out of
the message-groups change that surfaced it.

**Reported 2026-07-27. Plugin names and menu categories are never translated,
in any locale.** Everything a plugin's `manifest.json` shows *except* its name
is translated: `chisurf/core/plugin/manifest.py` runs `description`, `summary`,
`experimental_message` and `deprecation_message` (plugin-level and per RPC
method) through `tr()` at load time, and the extractor collects them. The two
fields the user actually reads in the menu — `display_name` and `categories` —
are excluded on purpose at *both* ends: `extract_strings.py` leaves them out of
`TEXT_KEYS` and `manifest.py` keeps them canonical, each with a comment saying
they double as menu-path / identity keys and are "localized at the nav seam".

**That nav seam does not exist.** The plugin-menu builder in
`chisurf/gui/__init__.py` (`parse_hierarchical_plugin_name`) splits
`display_name` on `:` into hierarchy parts plus a leaf and uses both verbatim —
there is no `tr()` call anywhere in that path — and the ribbon does the same via
`ribbon_categories.py::_parse_hierarchical_plugin_name`. So a manifest naming
`Spectroscopy:Single-Molecule:PCH` renders as those exact English words under
`de` and `fr`. Verified: "Burst Analysis", "Microtime Shifter" and
"Spectroscopy" have zero entries in `chisurf_en.ts` *and* `chisurf_de.ts` — the
strings are not merely untranslated, they were never offered to a translator.

This compounds with the ribbon entry below: the ribbon's plugin categories are
built from these same paths, so wrapping the ribbon's own literals in `i18n.tr`
would still leave every plugin-derived entry English until this seam is built.

The reason it cannot be fixed by wrapping the field is worth stating, because it
is the whole design problem: `display_name` **is** the identity key. It is the
menu path, it keys `plugin_order` in the ribbon, and it feeds
`get_plugin_settings_path(plugin_name)`. Translating it in place would move a
plugin's settings directory and lose its ordering when the user switches
language. A fix has to separate identity from display — keep the canonical path
as the key, translate each path segment and the leaf only at render time, and
teach the extractor to emit those segments (they are a small closed vocabulary:
Spectroscopy, Single-Molecule, FRET, Tools, Structure, Simulation, …). The same
anchoring rule as everywhere else then applies: any code re-deriving a key from
display text must repeat the identical `i18n.tr(...)` call.

**Reported 2026-07-27. The ribbon is not translated, and the mechanism that
looks like it covers it does not.** Switch the language and the whole top
navigation stays English. `chisurf/gui/widgets/ribbon/` contains **no**
`i18n.tr` call and no `.ui` file, so none of its text is translatable, and none
of it is even *extracted*: `build_tools/i18n/extract_strings.py` collects from
`.view.json`, `manifest.json`, `.ui` files and AST `i18n.tr(...)` calls, and the
ribbon matches none of those. Verified — "Other Tools", "Utilities" and
"Clipboard" have zero entries in `chisurf_en.ts`. ("Fitting" and "Analysis" do
appear, but from `fittingWidget.ui`; the ribbon's own literals are never looked
up, so those entries are a coincidence, not coverage.)

Two groups of strings are affected:

- **Category and panel titles**, hard-coded in `ribbon_categories.py`: Main,
  Edit, Analysis, Tools, Setup, View, Help, Documentation, Basic, Clipboard,
  Fitting, Utilities, Other Tools.
- **The ribbon's own chrome**, hard-coded across `titlewidget.py`,
  `ribbonbar.py`, `panel.py`, `toolbutton.py`, `ribbon_auto_fold.py`: "Collapse
  Ribbon" / "Expand Ribbon", "Panel options", "Remove from Quick Access
  Toolbar", "Show All Hidden Items", "Pin ribbon" / "Unpin ribbon", "Open Help
  Plugin", and the "ChiSurf" title and its tooltip.

Why it went unnoticed: `main.py::_retranslate_interface` tears the ribbon down
and rebuilds it on every language change, and its docstring says that rebuild
"re-reads every string through the freshly installed translator". That holds for
ribbon buttons derived from **QActions** — those come from `gui.ui` and are
retranslated in the step before — but a hard-coded literal re-read is the same
English literal. The rebuild is therefore not the fix, and the docstring
overstates what it achieves.

Fixing it is the ordinary in-place path already used for rich non-form tools
(wrap each static string in `i18n.tr`, see `tttr_time_windows` /
`tttr_microtime_shifter`), after which the extractor picks them up. Note the
ribbon is a **vendored** widget family: `ribbonbar.py`, `panel.py`,
`toolbutton.py`, `titlewidget.py` etc. carry upstream chrome strings, so decide
per file whether to localize in place or to keep the vendored copy pristine and
translate only ChiSurf's own layer (`ribbon_categories.py`,
`ribbon_auto_fold.py`, `ribbon_file.py`). Also mind the anchoring gotcha in
[/subsystems/i18n.md](/subsystems/i18n.md): the ribbon styles buttons by object
names derived from action text, so any `i18n.tr` added there must be mirrored
wherever a key is re-derived from display text.

**Found 2026-07-26 while unifying the progress bars. `PDBFolderLoad` cannot be
constructed at all.** `chisurf/gui/widgets/pdb/pdb.py` has rotted against a
refactored `TrajectoryFile`, in two places: `__init__` calls `TrajectoryFile()`
and `onLoadStructure` calls `TrajectoryFile(use_objects=…, calc_internal=…,
verbose=…)`, but the current constructor requires a positional `p_object` and
takes none of those keywords. The widget is reachable — the modelling
experiment page builds one (`gui/widgets/experiments/modelling/modelling.py`) —
so that page is broken too.

Half of it is fixed: `LoadThread`'s `procDone`/`partDone` signals had been
commented out during the PyQt-to-qtpy move (their `pyqtSignal` spelling did not
survive), so construction raised `AttributeError` one line earlier still; they
are restored as `QtCore.Signal`. The remaining `TrajectoryFile` calls need a
real port, and what `use_objects` / `calc_internal` were meant to select is no
longer expressed anywhere in that class — so the intent has to be recovered
before the call sites can be rewritten, which is why this is logged rather than
guessed at.

**Found and fixed 2026-07-26 — and the first diagnosis was wrong.**
`test_consistency_check_rejects_the_wrong_kinetic_scheme` was accepting a
deliberately wrong scheme at p = 0.297. It was filed here as "not the rename,
bisect the concurrent fitting-layer edits". That attribution was wrong: the
cause was the earlier change that made `k_ex` an **absolute rate in Hz**
(time-binned PDA) while this test still set it as the dimensionless
`K = (k1 + k2) T`. At 2 Hz over a 2 ms window that is K = 0.004 — the
"dynamic" data the test generated was *static*, so the static scheme it exists
to reject fitted it perfectly. The sibling test in
`test_pda2c_model_editor.py` had already been converted; this one was missed.

Fixed by converting through the dataset's observation time, as the sibling
does. With real dynamics the model recovers K = 2.04 against a truth of 2.0 and
the static scheme is crushed (chi2r 176 against 1.38), so the rejection is now
emphatic.

Worth keeping from the episode: **a unit change in a shared parameter needs a
sweep of every test that sets it**, because a test that silently generates the
wrong physics still passes — it just stops testing anything. And the acceptance
branch of that pair is now pinned to a typical realisation: at K = 2 the default
seed gives chi2r = 1.55 at the *true* parameters where seeds 2-8 give 0.80-1.18,
and the bootstrap correctly rejects that draw. Asserting on it would test the
noise, not the model.

**Found 2026-07-26 while making the PDA3c rate matrix fittable.** A rate fitted
by the three-colour dynamic model comes out **systematically fast, by some tens
of percent**, and more computation does not help. Measured on bursts simulated
from a known two-state scheme by an independent forward route (a fresh distance
triple per state per burst, mixed by sampled occupation times, then split
multinomially): the profile likelihood along `k_tot` peaks at 650–700 Hz for a
truth of 500 Hz, and the argmax moves by at most one grid step from 600 to 8000
sampled trajectories and from an occupancy resolution of 24 to 192. So it is
**not** Monte-Carlo noise in the occupation-time sampling — that part is exact
in distribution.

The cause is the approximation made *outside* the sampling, in
`Pda3cModel._mean_channel_probabilities`: each state is collapsed to its
distance-averaged per-photon probability vector *before* the occupation-time
mixing, so the intra-state distance spread contributes to the predicted
burst-to-burst width differently than it does to real bursts. Fixing it properly
means carrying the distance quadrature through the dynamic average (nodes x
occupancy nodes x bursts), which is a real cost increase and a design decision
about where to truncate — hence recorded rather than fixed in the change that
found it. Until then, `pda3c.py`, the concept page and the guide all say to read
a fitted rate as an exchange **timescale**, not a rate measurement; comparisons
between conditions are sound.

Note this was invisible before, because the rate matrix was a plain array
attribute nobody could fit — the bias only became reachable when the rates
became parameters.

**Narrowed down 2026-07-26, with the exact statement of the defect.** The same
approximation has a consequence with a *checkable* answer: **the multistate
route does not nest the static model.** At 1e-3 Hz over a 2 ms window nothing
switches, so every molecule sits in one state for the whole burst and the
likelihood must equal the static mixture's term for term. It is off by **2357
log-likelihood units** — because a pure trajectory is evaluated at its
distance-*averaged* probability vector where the static model integrates the
likelihood over the distance distribution, and those differ by Jensen. A
static-versus-dynamic comparison (an F-test, a model choice) is therefore
meaningless in exactly the regime where the two models are nested.
`test/models/test_pda3c_rates.py::test_the_multistate_route_nests_the_static_model`
records this as a **strict xfail**, so it will fail loudly when fixed.

**Two approaches tried and rejected, so nobody repeats them:**

1. *Exact atoms alone.* Giving pure trajectories the full static treatment, with
   the analytic weight `pi_i exp(-lambda_i T)` rather than their sampled
   frequency, makes the static limit exact to five decimals and removes a
   1901-unit spike at slow exchange (caused by occupancy quantisation merging a
   switching trajectory into a near-pure cell). But it leaves the *interior*
   annealed, and the halves are then inconsistent: the fit compensates by
   slowing exchange, the recovered rate moves from 199 to **65** against a truth
   of 200, and the profile bias flips from +30% to −30% (stably, 300–350 Hz at
   every sampling setting). Fixing one half alone is not an improvement.
2. *Sampling the joint average.* Drawing one quenched distance triple per state
   per occupancy node is the right average in principle, but the node labels
   *are* the occupancies, which shift continuously with the rates — so
   neighbouring evaluations see unrelated conformations however the draws are
   keyed (a per-node hash of the quantised occupancy included). The optimiser
   reads the noise as structure and walks off: 200 → 52.

**The fix is to carry the distance quadrature through the occupancy average** —
both halves together, deterministically — and the open question is where to
truncate it, since the product over states is combinatorial in the quadrature
nodes.

**Found 2026-07-26 while adding typeset labels.** `pytest test/fitting` used to
**abort the interpreter** part-way through (~47 %), so everything after it never
ran. `chisurf/macros/core_data.py::add_dataset` popped a `MyMessageBox` on its
two "nothing was read" paths; a modal dialog needs a GUI to close it, and with no
`QApplication` at all Qt aborts the process outright. The exception path a few
lines below already guarded on `gui is None` with exactly that reasoning — the
two earlier sites had been missed. Fixed by applying the same guard (head-lessly
the log is the report), which is what makes the suite run to completion.

That uncovered **14 pre-existing failures and 1 collection error** that the abort
had been hiding. All confirmed identical on an unmodified tree with only the
guard applied, so none belongs to the change that found them; recorded rather
than fixed because they span five unrelated subsystems:

- `test_fit_state.py` (5) — model `get_state`/`set_state` round-trips, including
  the FRET-Gaussian and PDA length-preservation contracts.
- ~~`test_grouping.py` (3) + `test_grouped_default_linking_contract.py` (1)~~ —
  fixed 2026-07-26; they read *source text* from paths that no longer exist and
  are now behavioural.
- ~~`test_experiment.py::test_FCS_Reader`~~ — fixed 2026-07-26. Remaining:
  `test_models_regression.py::test_parse_model_evaluation`,
  `test_parameter.py::test_equality`,
  `test_fit.py::test_fit_save_full_length_curves_have_nan_padding`,
  `test_reference_models.py::test_lifetime_model_convergence`.
- `test_derived_quantities.py::test_a_well_determined_ratio_is_where_the_delta_method_is_right`
  (noted 2026-07-28) — the skew diagnostic fires on a ratio it is meant to pass
  (`0.771 +0.0207 -0.0236`), so the asymmetry threshold is tripped by ordinary
  Monte-Carlo noise rather than by real skew. It samples with `method='de'`,
  which the ensemble-sampler change did not touch; recorded rather than fixed
  because the fix is a re-derivation of the threshold in `derived.py`.
- `test_sampling_diagnostics_report.py::test_posterior_summary_prefers_a_converged_chain`
  (noted 2026-07-28) — **flaky, roughly one failure in four** on an unchanged
  tree. It asserts that every posterior entry reports `method == 'mcmc'` after
  sampling; on a failing run they report `'laplace'`, i.e. the MCMC result was
  not adopted and the Laplace approximation stood. Measured by running the test
  alone five times: 2 failed, 3 passed, no edits in between.

  Worth knowing *how* this was established, because a single controlled run said
  the opposite. It first appeared while checking whether the atom-dtype change
  had caused it: reverted, the test passed; restored, it failed — a clean-looking
  A/B that was pure coincidence. Only repetition showed it flips on its own.
  A one-shot before/after cannot tell causation from flakiness, and a flaky test
  will happily frame whatever change is in flight.
- ~~`test_group_polarization_any_size.py` errors at collection.~~ — fixed
  2026-07-26.

**`test/gui` cannot currently run to completion (noted 2026-07-28).** It
**segfaults** (exit 139) about 19% in, at `test_channel_definition_lut_box.py`
— a file whose 8 tests all pass when it is run *alone*, so the crash is
cross-test state and not that file's doing. 17 failures precede it. Everything
after the crash is simply unrun, which is the worse part: the suite reports
nothing about roughly four fifths of itself.

Established as independent of the atom-dtype change by running the whole area
with the old `|U1` field and the new `|U4` one: **byte-identical** progress,
the same 17 failures, the same crash at the same point. The TTTR
channel-definition wizard and LUT tools had several files under concurrent edit
at the time, which is the first place to look.

**Update 2026-07-29 — there is also a hang, before the segfault.**
`test/gui/test_gui_plots.py::test_plot_updates_when_parameter_changes` did not
finish in **10 minutes** when run entirely on its own; it errors in the
`chisurf_app` fixture (`chisurf.gui.get_app()`, which boots the whole main
window) and then stalls. Seen while checking that a chiplot fix had not broken
plot consumers. A second instance's `pytest test/gui -q` was 87 minutes in at
the same moment, so a shared-resource conflict (server ports, the settings
directory) cannot be excluded and *neither run is a clean measurement of the
other* — but the solo run had the whole boot to itself and still did not
progress, which the concurrency explanation does not cover. Whoever picks this
up should time the fixture alone on an idle machine first.

**Found 2026-07-26 while closing [RF-182](/reviews/findings.md#rf-182).**
`test/core/test_curve.py::Tests::test_reading` passes when `test/core` runs on
its own and fails when `test/fitting` has run first in the same process: the
yaml round-trip comes back with a different `unique_identifier`. It is an
ordering artifact over process-wide registry state, not a defect in the curve
I/O, and it is identical with and without the `DataCurve` change that surfaced
it. Not fixed here because the poisoning module is somewhere in `test/fitting`
as a whole (no single file reproduces it) and chasing it is a separate job.
Two order-dependent failures in the *same* run **were** fixed:
`test_fit.py::test_fit_parse` and `::test_fit_data_setter` used
`chisurf.core.models.parse` / `chisurf.core.fitting.fit` while importing only
the package roots, so they passed only when another test module had imported
those submodules first; the test module now imports them itself.

**Found 2026-07-26 while closing [RF-168](/reviews/findings.md#rf-168) in the
BVA layer.** `test/plugins/burst/test_background_gui.py` has two failures that
are stale against the AutoForm conversion of the Burst Background tool
(`61a2803ae`, then `993577745`), unrelated to the BVA change that surfaced them.

- **`test_diagnostics_plots_build_and_render`** asserts
  `hasattr(w, "iht_plot")` on `BurstBackgroundEstimator`; the AutoForm rebuild
  no longer exposes named plot attributes on the tool, so the assertion fails at
  the first line and the render path is never exercised.
- **`test_semantic_detector_colors`** does
  `from chisurf.plugins.burst.burst_background import _det_color`, which no
  longer exists — the detector-colour mapping moved with the conversion.

  Both need re-pointing at the AutoForm section handles rather than a code fix;
  left open here because doing that properly means driving the tool headlessly
  and inspecting the render (the screenshot rule), which does not belong in an
  unrelated docstring/dedup change. The colour test in particular should assert
  through a public seam, not a private helper name.

**Found 2026-07-26 while routing the fit jobs through the job manager
([INC-08](/specs/assessment.md#inc-08)).** Two failures in the server suite,
both confirmed identical on the unmodified tree, both about the RPC *transport*
rather than the services under change — left open because fixing them means
re-deciding the client's error contract, which is [SV-04](/specs/assessment.md#sv-04)
territory and does not belong in an unrelated change.

- **Eight `test/server/test_rpc_edge_cases.py` tests are stale against the
  SV-04 error contract.** `ChisurfClient.call()` now raises `RemoteError` for
  application-level errors (that *was* the SV-04 fix), but these tests still
  expect an error **dict** back — e.g. `test_very_long_method_name` calls an
  unknown method and asserts on the returned payload, and gets
  `RemoteError: method '…' not found`. The tests need updating to
  `pytest.raises(RemoteError)`, not the code.
- **`pytest test/server` never terminates; the wedge is in
  `test_integration_lifecycle.py`.** Localised on 2026-07-26 by an A/B against a
  clean `HEAD` worktree: `pytest test/server --ignore=test/server/test_integration_lifecycle.py`
  finishes in **86 s** with **21 failed, 501 passed**, while the same run *with*
  that file idles indefinitely (0 % CPU) inside `TestParameterLifecycle` —
  stack in `zmq_ctx_destroy` → `zmq::mailbox_t::recv` → `poll`, i.e. a context
  termination waiting on a socket an earlier test left open. Run in isolation
  (`-k TestParameterLifecycle`) the class completes, so it is leaked state from
  earlier tests in the file, not the class itself. Until a socket is closed (or
  `LINGER` set) somewhere upstream, exclude that one file to run the suite.
  The 21 remaining failures are pre-existing at `HEAD` — the eight stale
  `test_rpc_edge_cases.py` expectations above plus fit-endpoint tests
  (`test_fit_save_endpoint`, `test_fit_list_includes_chi2r`,
  `test_model_finalize_endpoint`, …).

**Found 2026-07-25 while migrating the imaging tools onto the ROI subsystem.**
Three red tests, each pointing at real behaviour rather than a stale test alone.
Left open because each needs a decision from the owner of code being actively
worked in this tree; the fourth found alongside them (a `np.float` in
`test_fluorescence`, removed in NumPy 1.24) and three stale imports of the
retired `_dev/fluorophore_db` plugin were fixed on the spot. Two of the three —
the `calculcate_spectrum` term count and the binary `.pqres` read — were
resolved on 2026-07-25 and 2026-07-26 and are recorded below.

- **`test_structure.py::test_labeled_structure` fails on the labelled-structure
  path.** Molecular modelling has moved out of chisurf into the external
  framework, so this may be a test that outlived its subject rather than a
  live defect; confirm before either fixing or removing it.

**Found 2026-07-25 while closing [BUG-09](/specs/assessment.md#bug-09).** Both sit
in the anisotropy area; neither is reachable from a production call path today.

- ~~**`vm_rt_to_vv_vh` puts the g-factor in the one place that is not
  invertible.**~~ Fixed 2026-07-26 in its own change, as
  [RF-231](/reviews/findings.md#rf-231). It computed `vh = vm · (1 − g·r)`, while
  its sibling `calculcate_spectrum` — the one the fitting models actually call —
  computes `g · vm · (1 − r)`; only the latter satisfies
  `r = (I_VV − I_VH/g) / (I_VV + 2 I_VH/g)`, because a detection sensitivity scales
  the whole perpendicular channel, not just its depolarization term. The helper now
  uses that placement, the two doc pages that repeated the wrong formula were
  corrected with it, and `test_vm_rt_to_vv_vh_recovers_anisotropy` pins the round
  trip *and* term-for-term agreement with the spectrum path at `g ∈ {0.8, 1, 1.5}`.

**Fixed 2026-07-25/26 — kept here because the *patterns* keep recurring**

- **Five test files about one behaviour, and none of them could fail.**
  `test_group_polarization_any_size.py`, `test_polarization_fix.py`,
  `test_unified_polarization.py`, `test_group_reference.py` and
  `test_polarization_group_update.py` were written during a single bug hunt and
  between them contained *zero* assertions about polarization: each
  `logger.error(...)`d on a wrong value instead of asserting; one took a
  `num_datasets` argument with no fixture and no `parametrize`, so pytest errored
  at collection and the sizes were only passed from a `__main__` block; one ended
  `return True`. Consolidated into one parametrized file that asserts the
  contract stated in `Anisotropy.set_polarization_by_group_position`. The open
  question this was filed under — does a 3-fit group really alternate
  vv/vh/vv? — was not an owner call after all: the code answers it in so many
  words, and it does. The rewrite also found the expectation that had been
  logged-and-ignored for years: two fits *added separately* are two groups of
  one, so both are `vm`, not the `vv`/`vh` the old test wanted. **Pattern: a
  test that logs instead of asserting is worse than no test — it occupies the
  slot where a real one would go.**
- **Four "contract" tests grepped source text out of files they could not
  open.** `test_grouping.py` and `test_grouped_default_linking_contract.py`
  asserted that `"def _is_global_fit_dataset(" in Path("cs/macros/core_data.py")
  .read_text()`. The package was renamed `cs/` → `chisurf/` and one path was
  relative to the working directory, so all four raised `FileNotFoundError` —
  a test that asserts a substring appears in a file it cannot open tells you
  nothing twice over. Replaced with tests of what the functions do: which
  parameters count as nuisance, that grouping links the physics and leaves the
  instrument parameters local, that the global-fit dataset survives
  `remove_datasets`. **Pattern: asserting on source text pins the spelling, not
  the behaviour, and rots at the first rename.**
- **Every unnamed data group called itself `ExperimentDataCurveGroup`.**
  `DataGroup.name` documented a fallback to the current dataset's name, in a
  `except KeyError` branch that could never run: `Base.__init__` stamps
  `self.__class__.__name__` into `__dict__['name']` whenever no name is passed,
  so the key was always present. After loading an FCS file the dataset list
  showed the class name instead of the file. A stamped class name is now treated
  as absent. **Pattern: a fallback guarded by a condition its own constructor
  makes impossible is dead code that reads as a feature.**

- **A binary `.pqres` file was read with `np.loadtxt`, and three layers had to
  break for that to happen.** `FCS.read()` accepted a `reader_name` argument,
  documented it, and then dropped it on the floor — every call used the reader's
  configured default (`kristine`), so asking for `'pqres'` sent a binary file to
  a text parser and it died on byte 0xff. Behind that, `read_pqres_fcs` returned
  a `DataCurveGroup` where the dispatcher expects `list[dict]`, so the format had
  never worked through `read_fcs` at all. Behind *that*, every `<base>X`/`<base>Y`
  tag pair was promoted to a curve — the standard deviations, the weights and a
  25 025-point TCSPC decay included — yielding 10 curves where the file holds 3.
  **Pattern: a keyword argument that is accepted and ignored is worse than one
  that raises; and a test that `print`s and `return`s reports green over all of
  it.** (`test/fluorescence/test_pqres.py` now asserts the three named
  correlations, their 54 lag times and finite non-zero weights.)
- **The anisotropy spectrum test pinned a VH model that cannot be inverted.**
  The test asserted `−2·r` in the perpendicular channel where the code produces
  `−1·r`, and the "16 terms vs 8" term-count mismatch it was filed under was the
  union/concatenate mixing form, not a defect. The definition of `r` settles it:
  only `g · f_VM · (1 − r)` round-trips back to the `r(t)` that generated the
  pair. The test now compares the *decays* the spectra stand for against the
  analytic definitions, so it is immune to the term count. **Pattern: a test
  whose expectation was recorded from the implementation pins the bug as
  hard as it pins the behaviour — derive references from the definitions.**
- **A test loaded its subject from a hand-built file path and rotted silently.**
  `test/fitting/test_anisotropy_integrals.py` built
  `parents[1] / "chisurf" / "fluorescence" / ...` and `exec_module`d it; when the
  module moved under `chisurf.core` the path pointed at `test/chisurf/...` and the
  file errored at collection instead of failing loudly at a rename. Replaced with
  a normal import (the module pulls in nothing but numpy). **Pattern: importing by
  path defeats every tool that would have caught the move.**
- **A GUI modal reported an error from the macro layer, so head-less loading
  hung forever.** `core_data.add_dataset` caught every read failure and built
  `MyMessageBox`, whose `__init__` calls `exec_()`. With a `QApplication` but
  no user — CLI, script, test, the assistant — that blocks indefinitely; with
  no `QApplication` at all Qt *aborts the process*. A file that could not be
  read therefore looked like "loading is very slow". Errors are now re-raised
  when there is no GUI. **Pattern: never report from core/macro code with a
  modal; the caller cannot always click.**
- **`np.float` and `np.float_` were still used in 7 modules**, and NumPy
  removed them (1.24 and 2.0). Three FCS readers — ConfoCor3, ALV `.ASC` and
  PyCorrFit — raised `AttributeError` on the first data line they parsed, so
  those formats simply did not load. Fixed to `float`/`np.float64`, with a
  guardrail test that scans for the removed aliases. **Pattern: a removed
  alias only fails when its code path runs, so it hides in readers for
  formats nobody exercised recently.**
- **`GeneralFCSModel` exposed all three diffusion presets to the optimiser**
  while computing with one, so a fit reported its untouched defaults
  (`N = 1.0`, `D = 300.0`) as results and `n_free` was 15 instead of 5.
  **Pattern: when a model holds alternative parameter groups, the parameter
  list has to follow the active one.**

**Test collection**
- **RESOLVED — `test/core/test_rename.py`** no longer breaks collection of the
  whole `test/core` package. It used to be an ad-hoc tttrlib file-locking script
  that ran at import time against a hardcoded `e:\dev\chisurf\…\Leica_SP8.ptu`;
  it is now a real test over the repository's own `test/data/clsm/`, guarding
  that reading a photon file leaves no handle that blocks renaming or deleting it.
- **RESOLVED — the `chisurf.gui.widgets.yaml_utils` test modules are gone**
  (2026-07-26). Four modules imported `dump_yaml`/`prepare_for_yaml` from a
  module that **has never existed** — `git log -S` finds no commit adding or
  removing it — so they failed at collection with `ModuleNotFoundError` and took
  `test/settings`, `test/plugins` and `test/gui` down with them. They were
  print-driven prototyping scripts that never ran against real code (the same
  never-existed-API class as `test/models/test_user_models.py` below), so they
  were deleted and replaced by `test/settings/test_settings_yaml_lists.py`,
  which asks the same question — do list-valued settings survive as lists? — of
  the serializer that does exist (`chisurf/core/settings/settings_utils.py`).
- **RESOLVED — `test/plugins` collects again** (2026-07-26). Three further
  modules tested `chisurf.plugins._dev.chato`, a scratch tree that is
  **gitignored** (`.gitignore:78`) and absent from the repo, and one tested
  `chisurf.plugins.chat`, deleted in `c28d07b65`; all four were untestable by
  construction and were removed. `test_plugin_manager_mistral_icon.py` imported
  a real class (`AIIconRateLimitError`) that the package simply did not
  re-export — it now does. Two `test_manifest.py` files in `__init__.py`-less
  directories also collided on the module name (`import file mismatch`); the
  three `test/plugins/*/` subpackages got their `__init__.py`.
  **Pattern: a test module whose import fails takes its whole package's
  collection with it, so one dead import hides hundreds of live tests.**
- **OPEN — `test_plugin_manager_mistral_icon.py`: 6 tests red since the HTTP
  client swap** (found 2026-07-28 while test-gating an unrelated plugin-manifest
  fix). `085bd79b4` ("an HTTP client of our own") moved
  `PluginManagerWidget._post_mistral_json_with_retries` and its siblings off an
  injected session object onto the module-level `chisurf.core.http.post`, and
  dropped the `session` parameter — but the tests still pass a
  `SimpleNamespace(post=...)` as the second positional argument, so it binds to
  `path`, the real path binds to `headers`, and every call raises
  `TypeError: … got multiple values for argument 'headers'`. The signature is
  identical in HEAD and in the working tree, so this is not an in-flight edit:
  it is red on a clean checkout. The fix is test-side — monkeypatch
  `chisurf.core.http.post` instead of injecting a session — and it is small, but
  `chisurf/plugins/core/plugin_manager/gui/tool.py` has concurrent uncommitted
  edits in exactly this HTTP path from another instance, so rewriting the tests
  against a signature that may still be moving was left to whoever lands that
  migration. Nothing outside these 6 tests is affected; the rest of
  `test/plugins` (321 tests) is green.

**Qt teardown in test suites**
- `chisurf/plugins/fcs/fcs_filter_calculator/test/test_widgets.py` aborts with
  `libc++abi: Pure virtual function called!` when the file is run as one
  process. Every test passes individually, and the abort is independent of the
  test that happens to be running when it fires, so it is cross-test teardown
  (a C++ object outliving its Python wrapper, the usual pyqtgraph/`DockArea`
  shape) rather than a defect in any one test. Confirmed pre-existing in July
  2026 by reproducing it with the then-current working changes stashed.
  Workaround: run the file with `--forked`, or per-test, until fixed.

**Project save / restore**
- Project round-trip: decay/lifetime models do not save & reload (critical).
- Save→close→open resolves the active window via `chisurf.cs` after teardown
  removed it → `AttributeError: module 'chisurf' has no attribute 'cs'`.
- Dataset removal no longer confirms and closes dependent fits.
- TCSPC "stacked" (`is_vv_vh`) not persisted across restart (see the
  `@property` gotcha above).
- Undo/redo does not destroy stashed dataset/fit UI windows
  (`history_replay.apply_entity_lifecycle`) — stale windows linger.

**Fit creation / fitting**
- Access violation (`0xC0000005`) on fit creation after dataset load, in
  TCSPC/anisotropy chinet init — keep parameter init scalar/type-safe into the
  native layer (no catchable Python exception at the crash boundary).
- FCS MaxEnt fit does not autorange on creation → zero points in range →
  non-computable out of the box.
- Parameter-widget edits do not fully propagate to model/chinet.

**Plugins / tools**
- NDXplorer stays blocked after data load; clear-then-reload shows no data — a
  proper `reinit()` (reset caches, plot objects, combos) is needed rather than a
  partial `clear_plots`.
- TraceBrowser does not populate its file list on folder open (severe).
- Correlator/FCS channel-preset saving does not work.
- TTTR Image Browser exports to the wrong folder; anisotropy "Save CSV" ignores
  the loaded-data location (see file-save gotcha).
- BH / SPC-130 micro-time resolution is wrong and not corrected on load (data
  correctness).
- mmfdb-admin: cancelling the password prompt still opens the UI.

**Tests**

Found while verifying an unrelated change (2026-07-25) and **all resolved on
2026-07-25**; `pytest test/core` and `pytest test/models` both run clean (498
passed / 3 skipped, and 246 passed). Kept as a record of what each turned out to
be, because three of them were defects in the code rather than in the tests.

- `test/core/test_mmfdb_schema_migration.py` **did not finish** — this is what
  made a full `pytest test/core` run look like a hang. `sqlite3`'s `conn.backup()`
  retries a busy source forever, and the migration held an open write transaction
  while snapshotting. Fixed in the MMFDB repository (commit `38973c5`) by
  committing before the backup, with a regression test.
- `test/core/test_rename.py` failed at **collection** on a hard-coded Windows path
  (`e:\dev\chisurf\test\data\clsm\Leica_SP8.ptu`), taking the whole directory down
  with it. Rewritten against the repo's own test data.
- Of the four API-drift files, three were **code** defects, not stale tests:
  `Curve.__init__` did not coerce `None` axes and `to_dict` had lost
  `skip_qt_widgets`; `DataGroup.name` had lost its setter; and
  `Project.load` called the classmethod `Session.load` as if it mutated the live
  session, so opening a project restored no chinet nodes at all (`Session.clear()`
  was missing too). Only `test_base.py` was a stale test — one incidental
  assertion contradicted the dedicated UUID spec, and the spec wins.
- `test/models/test_fret_line.py` asserted frozen coefficient strings and lifetime
  arrays computed on `np.logspace(np.log(1), np.log(500))` — base-10 exponents, so
  that "1–500 Å" axis really ran to ~1.6 million Å. Worse, the axis is a module
  global that nothing restored, so those tests silently changed the distance grid
  for every test that ran afterwards. Rewritten to assert the relations that
  define a FRET line, with setUp/tearDown restoring the global. The `KeyError`s
  were real: fixed model constants (`R0`, `t0`, `s(G,n)`) live in
  `parameters_all_dict`, not `parameter_dict`, which holds only free parameters.
- `test/models/test_user_models.py` tested a registry —
  `register_user_model`, `load_user_models`, `iter_user_models_for_experiment`,
  `_user_model_registry` — that **has never existed**: `git log -S` across the
  whole history finds no commit adding or removing any of them, and the
  documentation page describing the same registry was rewritten against the real
  mechanism in `43e60f7f3`. So this was not API drift and needed no owner
  decision. Rewritten against what the code does offer: the
  `<dotted.module>__override__<timestamp>.py` exec-into-the-module injection.

**Environment**
- Built-in Jupyter/notebook integration is disabled/broken; the notebook menu is
  missing from the ribbon.
- `modules/ndxplorer/ndxplorer/utils/performance_optimizations.py` still calls
  `np.bool8`, removed in NumPy 2. In-process it is covered by
  `chisurf/core/compat.py` (chisurf is imported first, which restores the alias),
  but ndX run standalone would raise. The root fix belongs in the ndxplorer
  repository — left alone here only because that working tree currently holds
  another instance's uncommitted work.

# Deferred enhancements

- **A chimol dock's widgets were reported deleted, and the cause is not pinned
  down.** The report: closing/moving a dock left
  `_update_sequence_view` raising `RuntimeError: wrapped C/C++ object of type
  QListWidget has been deleted`, out of the *selection-changed* handler, so
  clicking an object killed the window.

  Two things landed. A guard in `_update_sequence_view` checks the widgets are
  alive and logs instead of raising, which stops the crash whatever deleted them.
  And a genuine latent defect in `dock_area.cleanup_empty_tab_widget` was fixed:
  it assumed a splitter holds exactly **two** children, moved the first sibling
  out and deleted the splitter — taking any third child with it, because Qt
  deletes an orphaned widget's children. chimol's default layout has a
  three-child vertical splitter (viewport / sequence / timeline), so the shape was
  present.

  **But that defect was not shown to be the reported cause.** Driving
  `removeTab` on the three-child splitter leaves every widget alive with the old
  code as well as the new, because `removeTab` detaches the page widget before
  cleanup runs. The remaining suspects are the drag paths (`_finish_drag`,
  floating windows) and `restore_tab`/`restore_all_tabs`, none of which has been
  driven. Next step: reproduce by *dragging* a dock out and closing the float,
  with a liveness probe on every page widget, rather than by calling `removeTab`.


- **The chimol accessibility doc figure is not reproducible byte-for-byte, and
  the reason is unknown.** Re-running `docs/guides/make_screenshots.py::
  _grab_chimol_viewer` rewrote `docs/guides/figures/chimol_accessibility.png`
  with ~41% of pixels changed (max channel delta 144) — the same molecule,
  orientation and blue-white-red colouring, but uniformly lighter in the
  crevices. The ray tracer has no RNG (`grep random render/raytracer.py` is
  empty) and its occlusion is its own code, not the GL shader's, so the GL
  ambient-occlusion floor cannot explain it. The figure was restored to its
  committed bytes rather than churned on an unexplained diff. Worth pinning down
  before the next deliberate figure regeneration: render it twice in one process
  and compare, then bisect against the chimol commits of 2026-07-26. A doc
  figure that changes on every build is churn a shared tree does not need.


- **Per-item tooltips in the metadata-key combobox** (`chisurf/gui/plots/
  fitinfo.py`, keys from `chisurf/core/fio/mmcif/db/pdbx_metadata.py`). Multiple
  Qt approaches (`Qt.ToolTipRole`, `QStandardItem.setToolTip`, delegates, event
  filters) either broke selection or showed no tooltip on a ~6.7k-item model.
  Deferred; descriptions are shown as the combo/value-cell tooltip after a key is
  chosen. If revisited, try a custom popup `QListView`/delegate applied *after*
  `showPopup()`, or a side-panel hint instead of dropdown tooltips.

- **RESOLVED — the RICS "35 % recovery bias" was the fit region, not the physics.**
  Recorded here on 2026-07-26 as an unexplained systematic and closed the same
  day. The closed loop (`test/microscopy/test_rics_closed_loop.py`) fitted the
  full square block of lags, `|ξ| ≤ 10` and `|ψ| ≤ 10`. Most of those 440 points
  carry no information about `D`: the `ψ = 0` row spans one 20 µs pixel dwell,
  and the far lags have no correlation left — so they outvote the slow-axis
  column that does carry it. Fitting `ξ = 0`, `1 ≤ |ψ| ≤ 10` instead gives
  **mean 0.99×, sd 0.13** over twelve simulations spanning `D` = 1–5 µm²/s,
  against **1.10×, sd 0.37** for the square region. The apparent "systematic"
  was the `D` = 2 slice of a strongly `D`-dependent artefact (0.62× at `D` = 1,
  1.41× at `D` = 2), which is why measuring at one `D` made it look constant.

  Ruled out along the way, and worth not re-testing: the discretisation of the
  simulated focus (a sixfold finer grid moves it 1.390 → 1.392, an exact
  analytic focus is no better), the axial term (an axially long focus leaves the
  bias unchanged, and the 2-D and 3-D models return identical `D`), the box
  extent, and non-stationarity. The static limit was already exact — with `D`
  fixed at 0 the model recovers the simulated waist to 1.4 % — which is what
  localised the problem to the *dynamic* term and then to the lags being fitted.

  One consequence is now documented rather than fixed: with the better region
  the slow end fails **silently**. Below about `D` = 1 µm²/s for a 20 µs / 50 nm
  scan the fit returns a confident wrong number (2.6× at `D` = 0.05, ~15× at
  `D` = 0.02) instead of collapsing to its bound as the square region did. The
  scan-precision planner is the intended defence.

- **`burst_h2mm/tests/test_examples.py` aborted the process in
  `tttrlib.write_hdf_file` — fixed 2026-07-27.** The abort was real but not the
  H2MM engine's and not the test's: tttrlib linked a *second* HDF5. Its build
  ran `find_package(HDF5)`, which also searches for an installed HDF5 **CMake
  config package**; that config outranks `HDF5_ROOT`, and on macOS it is
  Homebrew's — so the extension in the `arm64` env used `libhdf5.320` while the
  environment (and h5py/PyTables) load `libhdf5.310`. Whichever initialises
  first wins, which is why the same test passed after a GUI suite (it imports
  PyTables) and aborted when the burst suite ran alone. Fixed at the root in
  tttrlib (`c2334218`: module mode is forced when a caller names `HDF5_ROOT`),
  the `arm64` extension was rebuilt against the environment's HDF5, and
  `build_tools/build_tttrlib.py` now passes the same flags. The `--ignore`
  workaround is no longer needed: `chisurf/plugins/burst` runs standalone (344
  passed) and tttrlib's own suite is green on the rebuilt module. Guarded by
  `test/test_tttrlib_hdf5_runtime.py`.

- **TCSPC (79/79) + fluorescence AI triage (12/12) suites fully green.** Fixed on 2026-07-29.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.
  `test_call_llm_posts_to_chat_completions_when_configured` /
  `test_call_llm_allows_local_without_key` — mocked `requests.post` but the code
  uses `chisurf.core.http.post`; mock target corrected.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.

- **`examples/notebooks/fdb_burst_selection_roundtrip.ipynb` cannot run.** Found
  on 2026-07-27 while closing [INC-14](../specs/assessment.md#inc-14). Its first
  code cell does `from chisurf.core.mmfdb import FluorescenceDatabase,
  BurstPipeline`; `chisurf/core/mmfdb/` was deleted in the MMFDB extraction and
  neither name survives anywhere in the tree (`FluorescenceDatabase` was a
  deprecation shim over `mmfdb.repository.MFDatabase`, and `BurstPipeline` has no
  definition at all). Its prose also still describes the curated database as the
  storage default, which [INC-15](../specs/assessment.md#inc-15) shows it is not.
  Porting it means rewriting the notebook onto `mmfdb.repository.MFDatabase` plus
  the `burst_analysis` `BurstWorkflow` facade and re-running every cell — more
  than a path fix, so it is recorded here rather than half-corrected.

- **`test_trajectory_manifests_drive_plugin_discovery` is red against committed
  state.** Met on 2026-07-27 while migrating the FRET Calculator onto
  `ChisurfDockTool`. `test/plugins/test_plugin_contracts.py:139` asserts
  `info["menu_hidden"] == (manifest_id != "traj_tools")` — i.e. the Traj Tools hub
  must be *visible* in the menu and its child trajectory plugins hidden — but
  `chisurf/plugins/traj/traj_tools/manifest.json` carries `"menu_hidden": true` at
  `HEAD`, so the hub hides itself and the assertion trips. Neither file is touched
  by the migration and both are unmodified in the working tree, so this is
  committed breakage, not an in-flight edit. Which side is wrong is the open
  question, and it is exactly the undocumented hub/child `menu_hidden` pattern
  that [INC-07](../specs/assessment.md#inc-07) still lists as open — deciding it
  belongs with that finding rather than inside an unrelated dock-base migration.
  (The sibling failure in the same file,
  `test_plugin_direct_loadui_string_targets_exist` on a missing
  `vv_vh_g_factor/gui/wizard.ui`, is *not* committed breakage: that tool is
  mid-edit in the working tree by a concurrent `.ui`-to-AutoForm port, and the
  `.ui` never existed at `HEAD`.)

- **`compute_ics` returned non-finite values and wrong correlations for non-square
  ROIs.** **FIXED on 2026-07-31** in the companion repository (`67d9dda5`), guarded by
  `test/python/clsm/test_clsm_ics.py` (`4b9ae857`). Two independent defects:

  * `get_roi` indexed the input image as `images[f*(nl*np) + l*nl + p]`, using the
    number of *lines* as the row stride where it needed the number of *pixels per
    line*. **On a square frame the two are the same number, so square ROIs were always
    correct** — which is why this survived. A wide frame was read scrambled; a tall one
    ran past the frame, and past the whole allocation on the last frame, which is where
    the NaNs came from. It also explains the one detail that never fit: only a
    self-pair `(f, f)` failed, because the overread of any earlier frame lands
    harmlessly in the next one.
  * `compute_ics` fed an `r2c` half spectrum (`np/2+1` compact columns) to a full `c2c`
    inverse using full-width strides, so the spectrum was misread. The half spectrum
    now has its own strides and the inverse is `c2r`.

  Both were needed: the stride fix alone still left the autocorrelation of a delta at
  0.53125 instead of 1. Now it agrees with a NumPy reference to 6.7e-16 across square,
  tall, wide and odd shapes, for auto- and cross-correlation, and matches the
  convention PAM (`Do_2D_XCor.m`) and the Kolin/Wiseman STICS reference use.

  Nothing caught it because a flat field is correct either way (its spectrum is pure
  DC) and the ICS fits have a free amplitude with `normalise_ics` rescaling — the RICS
  closed-loop test recovered the simulated `D` straight through both bugs. The new
  tests are therefore all non-square, and the acceptance test needs no normalisation
  convention at all: the autocorrelation of a delta must be zero at every non-zero lag.
  `test_a_region_does_not_change_the_particle_number` now passes 5 runs of 5.
- **`import chisurf.core.fluorescence.burst` fails: `tqdm` is undeclared.** Met
  on 2026-07-28 while closing [RF-604](../reviews/findings.md#rf-604).
  `chisurf/core/fluorescence/burst/bva.py:3` imports `tqdm` at module level for
  a single progress bar (`:117`), but `tqdm` appears in neither `pixi.toml` nor
  `pyproject.toml` and is absent from both the `default` and the `test`
  environment — so the package `__init__` raises `ModuleNotFoundError` and
  everything downstream of it goes with it, e.g.
  `test/gui/test_pda2c_model_editor.py::test_pda_model_editor_renders_and_computes[...Pda2cSimpleModel]`
  via `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py:22`.
  The sibling use in `maxent_decay/core/solver.py:8-9` already treats `tqdm` as
  optional behind a `try`, which is the shape the fix should take (or declare
  the dependency); it is recorded rather than fixed here because it belongs to
  the burst subsystem and not to the PDA finding this run closed.


## Burst GUI follow-ups (opened 2026-07-28)


## tttr_image_browser: the widget suite aborts at teardown, about one run in three

**Found 2026-07-28** while migrating the tool onto the shared dockable-tool base
(PRD-36). `chisurf/plugins/tttr/tttr_image_browser/test/test_widgets.py` aborts
with `libc++abi: Pure virtual function called!` inside `pytest-qt`'s
`_process_events`, after the body of `test_tttr_image_browser_tool_creation` has
already passed — so it is a **teardown** crash, not a test failure, and it takes
the whole pytest process with it.

It needs the *sequence*: the two Qt-free view-model tests, then a bare
`TTTRImageBrowser`, then a second one inside `TTTRImageBrowserTool`. Constructing
either widget four times on its own never crashes. Measured alone-vs-alone over
five runs each with the pre-migration `gui/tool.py` loaded side by side with the
new one: **2/5 crashes on the old class, 3/5 on the new** — the rate is the same,
so the migration neither caused nor cured it. `-p no:randomly` does not help; the
order is already fixed, the crash is simply intermittent.

The shape (a pure-virtual call while deferred deletions are processed) points at
a `pyqtgraph` item outliving the C++ half of its owner across two widget
generations in one process. The fix belongs in the offscreen-Qt test fixture or
in the image-browser section's teardown, not in this plugin's tests, so it is
recorded rather than patched around; the plugin's own suite is green under
`-p no:randomly` and green about two runs in three otherwise.


## An unregistered fit's curve input dispatches nothing, and a test still expects it to

**Found 2026-07-29** while checking that a shared-table change had not broken
anything: `test/gui/test_auto_model_widget.py::test_curve_input_widget_renders_and_dispatches`
is red on HEAD, with no uncommitted work in the code it exercises.

`CurveInputWidget._on_change` dispatches `section.select_action` only
`if section.select_action and fit_index >= 0`, and `_own_fit_index()` answers
`-1` when the bound model's fit is not in `chisurf.fits`. Its docstring says
this is deliberate — the method used to answer `0`, which is not "unknown" but
*another fit*, so an edit could land on whichever fit happened to be first. The
test builds a model that is not registered and asserts `model.change_irf` is
dispatched, i.e. the older contract.

Both readings are defensible and they conflict: either the widget should still
apply the selection to its own model when no fit index can be resolved (a
headless or scripted fit otherwise gets a picker that silently does nothing), or
the test should assert that an unresolvable fit dispatches nothing. That is the
call of whoever made the `-1` change; it is recorded here rather than decided
from the outside, since guessing wrong re-introduces the "edit lands on the
wrong fit" bug the docstring describes.

---

## Three plugin GUIs die when constructed bare (no main window, no credentials)

**Found 2026-07-29** while sweeping every chiplot-using plugin GUI to check that
the [chiplot](/subsystems/chiplot.md) `add_arrow` fix had not left another panel
broken. 22 of them construct cleanly; three do not, and none of the three is a
chiplot fault:

* `core/mmfdb_admin` — **fatal abort**. `MMFDBAdminTool.__init__` ->
  `_ensure_authenticated` fails to log in (embedded server, no credentials),
  and the interpreter dies with `QThread: Destroyed while thread is still
  running` -> `Fatal Python error: Aborted`. A cancelled or failed login should
  leave the tool unusable, not take the process down.
* `core/acq` — `AttributeError: 'NoneType' object has no attribute
  '_acquisition_manager'` at `gui/tool.py:1089`: the tool writes itself onto
  `self.main_window`, which is `None` when `chisurf.cs` is not up.
* `core/lightpath_simulator` — constructs fine, then **segfaults at
  interpreter teardown** (exit 139 after the widget is built), around its
  plugin RPC client.

Repro: instantiate the manifest's `entrypoints.gui` class with no arguments
under `QT_QPA_PLATFORM=offscreen`. Not fixed in the change that found them: all
three are pre-existing on HEAD, live in plugins that change did not touch, and
each is its own diagnosis (a thread-lifetime bug, a missing-host guard, and a
teardown crash). What is *not* established is whether the first two also bite in
the real application, where `chisurf.cs` exists and a login dialog is answered —
the sweep only proves the bare-construction path is broken, which is the path a
headless test or a standalone launcher would take.

## `test/fitting` — the ten inherited failures, resolved (2026-08-03)

Recorded here when the consolidation commits turned a body of in-progress work
into history; all ten now pass, and the entry is kept because *why* they failed
is more useful than that they did. Six were tests written against APIs that
never existed; two were real bugs; two were about reproducibility.

**Real bugs, fixed in the code.**

* **Parameter links were lost on every project reload.** `fit_state` stored a
  link target by uid, and loading a project constructs fresh models with fresh
  uids, so no link could ever resolve. The parameter *lookup* already fell back
  to the name; the link target did not. It now records `link_target_name` and
  falls back the same way. This silently un-linked every global fit that was
  saved and reopened.
* **MCMC chains were irreproducible.** `walk_mcmc` and `walk_mcmc_blocked` drew
  from NumPy's global stream with no way to pin them, so the same fit sampled
  twice gave different credible intervals. Both now take `seed=`, which
  `sample_fit` forwards. The default still draws from the global stream, so
  `np.random.seed` keeps working for existing callers.

**Tests asserting an API that was never implemented.** `Pda2cGaussianDistanceModel`
has never existed in this tree; `Gaussians.append` takes `x`, not `amplitude`;
`ParseModel` and `LifetimeModel` are constructed *by* a `Fit` and read data
through `fit.data`, so neither can be built bare with a mock hung off it
afterwards; and two tests stubbed a model through `__new__` and then assigned to
`parameters_all_dict`, which is a read-only property. Each was rewritten against
the real API, keeping the behaviour it meant to cover.

**Assertions about the wrong quantity.** A lifetime spectrum's amplitudes are
normalised fractions -- one component is 1.0 by construction, and the absolute
scale lives in the scaling parameter -- so comparing an amplitude against the
generating count rate tests a number the model does not claim. `Parameter`
derives from `Base` and compares by identity, because two parameters holding 2.0
are still two different parameters; comparing values is what `.value` is for.
And `FitGroup.save` derives one filename per member, so the base picks up a
member suffix.

*Lesson worth keeping:* a test that has never passed is not evidence of a
regression, and reading it as one sends you looking for a bug that is not there.
Six of these ten described a system nobody had built.

## 2D-MFD exchange rates came back 20-35% low  *(fixed)*

**Fixed.** A fitted exchange rate was biased low, from -20% at 1 kHz to -33% at
5 kHz on ground-truth simulated data, and the cause was not any of the five
places it was looked for. Kept because the eliminations are the expensive part
and a later regression should not repeat them.

Ruled out, each by measurement, with the instrument response *declared* rather
than estimated so it could not contribute:

* the instrument — a perfect response left the bias unchanged;
* the burst-duration binning — 6 -> 40 span bins moved the answer 0.7%;
* the occupation-node coarsening — 16 -> 200 nodes was identical;
* the analytic approximations as a class — the transcribed Sim2D Monte Carlo,
  which makes none of them, had the *same* bias;
* the pinned optics — correcting the benchmark's distances (they gave E = 0.190
  and 0.843 where the simulator generates 0.2 and 0.8) and removing a static
  6 A width improved the deviance from 823 to 675 and left the bias.

**The cause.** Both forward models handed a burst's photons out over the states
in proportion to the *time* spent in each. A molecule is brightest at the centre
of its transit, so its photons over-sample whichever state it held then: the
effective averaging window is shorter than the burst's first-to-last-photon span,
the observed histogram is *less* averaged than the model predicts at the true
rate, and the fit compensates by lowering it.

**The fix.** `occupation.photon_weighted_occupation_variance` evaluates

    Var(f) = pi0 pi1 (1/N^2) sum_i sum_j exp(-k |t_i - t_j|)

which is exact for a telegraph process whatever the arrival pattern, and
`effective_window_scale` inverts it to the window a burst's photons behave like.
`MfdKineticModel.photon_weighted_window` applies it, on by default and silently
skipped when the folder carries no photons.

| exchange | span assumption | photon-weighted |
|---|---|---|
| 1 kHz | -26.8% | **-7.3%** |
| 5 kHz | -33.1% | **-3.0%** |

It is also *faster* — 18.9 s/fit against 28.8 at 5 kHz — because a shorter window
needs fewer transfer-matrix slices.

**What is left.** One scale factor is used for the whole measurement rather than
one per nuisance cell, because the ratio is a property of a burst's brightness
*shape* and varies far less than its duration or photon count; per cell needs the
cell index the binning does not return. The residual -7.3% at 1 kHz is larger
than at 5 kHz and has not been chased.

Gates: `test_photons_do_not_sample_a_burst_uniformly_in_time` (mechanism) and
`test_the_photon_weighted_window_recovers_the_generating_rate` (end to end), both
slow, in `test/fluorescence/test_mfd_ground_truth.py`.

## Three-colour PDA is slow, and not where it looks

**Open, now profiled.** `chisurf/core/models/pda2c/` drives `tttrlib.Pda` — the
C++ two-colour engine. `pda3c/likelihood.py` computes the three-colour equivalent
in Python, and it is slow: ~17 s for 4 000 bursts × 120 model points.

**Where the time goes**, measured with `cProfile`:

| | share |
|---|---|
| `_background_factors` | **64%** (28.9 s of 45.5 s over three calls) |
| `burst_log_likelihood` itself | 34% |
| `log_multinomial_pmf` | **0.07%** |

So the multinomial is free and the background correction is everything.

**What does not work, and was tried.** Inside `_background_factors` the obvious
tttrlib reuse is `Pda.poisson_0toN` for the per-channel background series — it
agrees with `scipy` to 6e-17 and is about 4× faster on the series alone. Caching
it, together with the `meshgrid` exponent bookkeeping, against the background
rates and box shape produced **no measurable gain** (16 929 ms against 16 942 ms,
bit-identical output). Two reasons, both worth knowing before trying again:

* `boxes` comes from `_channel_boxes(counts, ...)`, so it depends on the burst
  chunk and a cache keyed on it misses;
* the cost is the `gammaln` broadcast over `(n_bursts × K × width)` — the falling
  factorials — not the Poisson series, which is one small array per channel.

**What would.** Either a C++ kernel for the falling-factorial box (the thing
`Pda` does for two channels, generalised), or a smaller box: `_tail_cutoff` and
`_MAX_CUTOFF` decide `width`, and the array is linear in it. Measure the cutoff's
effect on the answer before making it a knob.

Unrelated and unexplained: `burst_log_likelihood` and
`burst_log_likelihood_reference` disagree by up to 28 log units on a
naive comparison. That is **pre-existing** — identical at HEAD before any of the
above — and may be a misuse of the reference's contract rather than a defect, but
nobody has checked.

## The Mistral icon tests would call the real API if their mock were fixed

**Open.** `test/plugins/test_plugin_manager_mistral_icon.py` fails with

    TypeError: _manager.<locals>.<lambda>() missing 1 required positional argument: 'path'

because `_post_mistral_json_with_retries` dropped its `requests_module`
parameter — it reaches the transport through `chisurf.core.http` itself now —
and the test's stand-in still threads one through.

**Do not just fix the signature.** Doing that makes the six tests *pass the
mock* and then issue **live HTTP requests**: `api.mistral.ai` returns 401, and
the OpenAI-compatible cases fail DNS on `api.example.test`. The mock was the only
thing holding the transport, so correcting its shape removes the seam without
replacing it.

The fix is to intercept at the new seam — patch `chisurf.core.http` (or inject a
transport) rather than hand a module in — which is a change to how these tests
are built, not a one-line signature edit. Until then the `TypeError` is the safer
failure: it is loud, fast, and offline.

## `img_flow`'s demo PTU reconstructs 29 of its 30 frames

**Found 2026-08-05** while running the microscopy plugin suites during the
`tifffile`/`imageio` removal. Unrelated to that change — nothing on this path
touches image files — but worth writing down, because the default suite cannot
see it: `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` is marked
`slow`, and the `test` task runs `-m 'not slow'`.

**The measurement.** Deterministic, not flaky (three runs, same number):

```
python -m pytest -q chisurf/plugins/microscopy/img_flow/test/test_img_flow.py \
    ::test_the_demo_is_a_readable_ptu_whose_flow_comes_back
# assert 29 == 30
```

The written stream is not short of markers — that is the first thing to check
and it rules out the obvious explanation. `create_demo(..., n_frames=30)`
produces 423 058 events carrying **30 frame markers** (routing channel 4) and
1920 line-start / 1920 line-stop markers, i.e. exactly 64 lines for each of the
30 frames. `tttrlib.CLSMImage(t, fill=False)` then reports `29 x 64 x 64`.

**Where the frame goes.** `CLSMImage::get_frame_edges` turns N frame markers
into N−1 intervals; the last frame is closed only by the `n_events` edge that
`skip_after_last_frame_marker == false` appends. Thirty markers giving
twenty-nine frames means both skip flags are effectively true for this file, so
the final frame — which has no *following* frame marker, only the end of the
stream — is discarded with its photons. Establish which code path sets those
flags for a PQ PTU before changing anything: the defaults in `CLSMImage.h` are
`false` for both, so they are being set somewhere along the PQ header route.

**Not the recent CLSM commit.** The suspicion falls naturally on tttrlib
`37dedfc4` ("reconstruct images from a line clock that has no stop marker"),
which reworked frame edges the same day. It is not the cause: its only
default-routine change is `walk_back_over_simultaneous_markers`, which moves an
edge earlier within one macro-time tick and cannot change how many edges there
are. Do not spend the rebuild on that A/B.

## Companion explorer: eight cache/change-token defects fixed, not yet committable

**Where to pick this up.** The fixes and their tests are **in the ndXplorer
working tree and green** (861 passed, 6 skipped, from a 572-test baseline), but
they could not land as their own commit and are waiting on the peer refactor
underneath them.

**Why they cannot land alone.** Every fix edits code that exists only in the
working tree. `git show HEAD:ndxplorer/core/data_source.py | grep -c "def gate_key"`
returns **0**, and the same for `_frame_column` in `axis_helpers.py` — so a
commit of "just my hunks" against HEAD would target functions HEAD does not
have. The peer refactor in flight (arrow backend removed, gates evaluated in the
store, masks as TIFF) spans 46 paths and has 9 staged deletions in the shared
index. These fixes go in **with** it; extracting them first is not a smaller
change, it is an incoherent one.

**What was fixed** — all eight are the same failure mode, a change token that
does not change, so the plot silently keeps the previous population and the
counts under it agree because they came from the same skipped update:

1. `histogram_helpers` keyed bin edges on `(count, first, last)`. A log axis is
   `logspace(log10(lo), log10(hi), n+1)` and a linear one `linspace(lo, hi, n+1)`
   — identical on all three. Switching an axis to log left `should_recompute`
   seeing nothing and the plot kept its linearly binned histogram. Now
   `bins_token`, which adds the **middle** edge; that separates any two monotone
   spacings over the same endpoints, which is the general form.
2. `MaskDataSelection.gate_key` had the same collision, and there the gate
   demonstrably selects different points either side of it.
3. `_compute_selection_hash` dispatched on the class *name* and mis-spelled
   `Gaussian2DSelection` as `Gauss2DSelection`, so every ellipse fell through to
   `str(sel)` — the object **address**, which does not move when the table edits
   the gate in place. Reshaping, resizing or inverting an ellipse changed
   nothing. The bitmap branch used the construction-time uuid while the brush
   paints into `sel.mask` in place. Now delegates to `mask_state.gate_key`, the
   routine the mask cache already keys on, so the two caches cannot disagree.
4. All three selection classes had a `selection_id` fast path in `__eq__`. The
   id is frozen at `__init__` and never mentioned `cov` or the log flags, so a
   round ellipse compared **equal** to an elongated one and a dragged interval
   equal to its pre-drag self. Removed; `selection_id` is for matching a table
   row to its object, not for describing the gate.
5. `cache_manager.HistogramCache` keyed on three sampled data values and on
   `np.sum(mask)`, and handed one dataset's histogram to another. Its 2-D key
   built an **object array** of the two edge arrays, whose `tobytes()` is a list
   of pointers. Now hashes contents.
6. `histogram_export.copy_2d_hist_csv` indexed `H[i, j]`, x first, while `H` is
   stored `(n_y, n_x)`: the square default binning exported the **transpose**,
   and an image histogram raised an uncaught `IndexError` so the copy silently
   did not happen.
7. `vectorized_ops.digitize_parallel` carried `fastmath=True`, which folds away
   its own `isfinite` guard: a NaN came out as bin **0**, a real bin at the left
   edge, while the NumPy fallback put it past the top edge. Which answer a column
   of NaNs got depended on whether numba was installed. Dropping the flag gives
   exact `np.digitize` parity and costs nothing (2M points into 512 bins: 10.9 ms
   with, 9.1 ms without, against 122 ms for `np.digitize`).
8. `fast_percentile_range` read `valid_data[index]` out of the **unsorted** array
   when both percentiles rounded to one rank — not a percentile of anything, and
   it moved when the rows were reordered. Also `save_mask_as_bitmap` crashed
   inside libtiff on an empty mask and silently wrapped a label past its dtype.

**Trap in re-deriving any of this**: the ndXplorer suite needs `chisurf` on
`PYTHONPATH` or 16 region-gate tests fail with `ModuleNotFoundError` and read as
a code defect.

The dependency is **intended** (user, 2026-08-05) and is now declared in
`modules/ndxplorer/pyproject.toml`. It is not an optional integration: region
and lasso gates are `chisurf.core.roi` shapes, the parameter and constants
tables are `chisurf.core.fitting.parameter` groups, and the data-frame editor,
curve-fit dialog and glyphs come from `chisurf.gui`. It had been used in all of
those and declared in none, so a clean install imported fine and then raised the
first time somebody drew a lasso.

It is deliberately **absent from `conda-recipe/meta.yaml`**, with a comment
saying so, because there is no chisurf conda package on any channel that recipe
builds against — listing it fails the build rather than documenting anything.
The recipe installs with `--no-deps` and its `test:` block only imports
`ndxplorer` and launches the GUI, so the package still builds. Add it there once
chisurf is published; do not "fix" the omission before that.

**Trap in the fixtures**: a square histogram cannot show a transpose, a mask
with all labels under 256 cannot show the 16-bit path, and a selection test that
builds a second object cannot show any of defects 3 and 4 — the table edits gates
**in place**, so the tests have to as well.

## ~~`IMP.bff.restraints.AVNetworkRestraintWrapper` is gone~~ — it was shadowed. Fixed 2026-08-10

> **RESOLVED 2026-08-10, and the diagnosis below was wrong.** The wrapper is not
> "an IMP API that moved" and it never went anywhere: it is in imp.bff at
> `pyext/src/restraints/AVNetworkRestraint.py:69`, and the local IMP 2.25 build
> now in `arm64` exposes it. It was **shadowed**.
> `modules/imp-tricks/src/sitecustomize.py` inserted imp-tricks' own tree at the
> *front* of `IMP.bff.__path__`; imp-tricks ships its own `IMP/bff/restraints/`
> package, and a subpackage resolves to the **first** matching directory and
> stops — so imp.bff's `restraints` was unreachable, submodules and exported
> names alike. imp-tricks' own `__init__` calls its classes "non-breaking
> additions to `IMP.bff`", which is exactly what they were not.
>
> Fixed in **imp-tricks** (`5967e77`), where it belonged: a subpackage found in
> both trees now gets the two directories unioned into one `__path__` (local
> first, so precedence is unchanged), and the shadowed `__init__` is evaluated
> against the live package so its public names are adopted. Nothing local is
> overwritten, and it recurses to any depth.
>
> **FRET suite: 16 failed / 112 passed → 6 failed / 122 passed.** All ten
> `AVNetworkRestraintWrapper` failures are gone. The six that remain are all
> `test_examples.py` and want `/Users/tpeulen/dev/olga`, a sibling checkout not
> on this machine; they say nothing about the code. Full write-up in
> [workflows/imp-local-build](../workflows/imp-local-build.md#what-the-build-fixed-and-what-it-did-not).
>
> **The lesson worth keeping**: "the attribute is missing" was recorded as an
> upstream API removal without anyone checking whether something on `sys.path`
> was standing in front of it. `IMP.bff.__path__` had two entries the whole
> time, and printing it would have ended the question in one line.

**Found 2026-08-05** while porting the FRET modelling plugin off mdtraj. Not
caused by that port — but the port is how they were noticed, so they are written
down rather than left.

**The measurement.** In the `arm64` env with IMP 2.24:

```
python -m pytest -q chisurf/plugins/modelling/fret/test
# 16 failed, 112 passed
```

Every failure reduces to one of exactly two causes, and neither involves the
trajectory code:

| Cause | Tests |
|---|---|
| `AttributeError: module 'IMP.bff.restraints' has no attribute 'AVNetworkRestraintWrapper'` | 13 (`test_imp_engine.py`, `test_dock_project.py`) |
| `FileNotFoundError: /Users/tpeulen/dev/olga/doc/data/T4L/screening_tutorial.fps.json` | 3 (`test_examples.py`) |

The second is a sibling checkout that is simply not present on this machine, so
those three say nothing about the code. The first is real, and the correction
above says why: the wrapper exists, but `IMP.bff.restraints` resolves to
imp-tricks' package rather than imp.bff's. Fix it in **imp-tricks** — either
re-export `AVNetworkRestraintWrapper` from its
`IMP/bff/restraints/__init__.py`, or make `sitecustomize` merge same-named
subpackages instead of letting the first entry on `__path__` win — not by
working around it here.

**A trap in re-measuring this.** A `git worktree` at HEAD is *not* a usable
baseline for this suite: `modules/` holds symlinks to sibling checkouts and is
gitignored, so a fresh worktree collects two import errors before it runs a
single test. Compare by classifying the failures' root causes instead, which is
what established that the mdtraj port added none of them.

## packaging: the release installs the tttrlib that development refuses (2026-08-05)

`pixi.toml` states the case against the published TTTR library plainly — conda
and PyPI are both capped at `0.26.2`, which predates the photon-simulation
engine and still carries the `compute_ics` defect that segfaults any image
correlation using frame lags — and `build_tools/build_tttrlib.py` is therefore
its *only* provider in a development environment, building `0.27.0` from the
sibling checkout.

`build_tools/build_installer.py` does the opposite. It passes `tttrlib` in
`conda_extras` for the macOS and Linux runtimes (resolved from bioconda) and in
`pip_nodeps` for Windows, so every shipped installer contains the version the
project has documented as wrong. A user's ICS correlation crashes where a
developer's works, and nothing in CI distinguishes the two — the installer smoke
test only asserts the main window appears.

Fixing it means building the library from source inside the installer, the way
`_install_imp_tricks` already clones and installs its sibling: the runtime env
would need `swig`, `ninja` and a compiler alongside the `cmake` it already
installs for labellib, and the build tools are stripped afterwards anyway. Left
undone here because it cannot be verified without a full installer run on each
platform.

## packaging: about twenty plugin CLIs ship with no command to reach them

`rattler-recipe/collect_entry_points.py` discovers a plugin's command only
through a `cli_entrypoint = "<name>=<module>:<func>"` assignment in the plugin's
`__init__.py`. A plugin that grows a `cli.py` without one is packaged with its
CLI unreachable — `python -m` still works from a checkout, which is why this
goes unnoticed. Current count: 29 plugins declare one, roughly twenty more have
a `cli.py`/`cli/` and do not, among them `accurate_fret`, `burst_2cde`,
`burst_bva`, `burst_h2mm`, `flc_2d`, `irf_estimator` and `batch_analysis`.

`burst_background` was the visible case: it *had* a console script, lost the
assignment when the plugin was rewritten as an AutoForm tool, and silently
dropped out of the recipe. That one is restored. The rest need a name each —
that is the only real work — and one line per plugin.

## `import tttrlib` is broken in the `arm64` env — a half-finished rebuild

**Found 2026-08-06**, mid-session, between two test runs that both passed:

```
ImportError: dlopen(.../tttrlib/_tttrlib.cpython-312-darwin.so):
  symbol not found in flat namespace '__Z18isFlimLabsITT1File...'
```

Nothing in ChiSurf caused it. `~/dev/tttrlib` has moved several commits ahead
and carries a large uncommitted change (`CMakeLists.txt`, new format docs), so
the installed `_tttrlib.so` references a symbol the currently-linked per-module
dylibs do not have — the package is a **directory of dylibs** now, and the link
step runs without a rebuild, so a partial rebuild leaves exactly this.

**Do not "fix" it by running `pixi run build-tttrlib`** unless you own that
tttrlib change: it compiles whatever C++ is in the working tree into the shared
env, and another instance's half-finished work will land on everyone. Either
wait for them to finish, or build from a clean checkout at a known commit.

**What it costs meanwhile:** any suite touching `tttrlib` cannot even be
collected — 37 collection errors across the plugin tests — so a green run is
not obtainable while it lasts, and a red one says nothing.

## A 3-atom AV fixture segfaults LabelLib

**Found 2026-08-06** finishing the mdtraj port. `test_pair_selection.py`
reaches `compute_efficiency_matrix_from_evaluators_trajectory` on a **3-atom**
"protein" (one ALA: CA, HA, N) and LabelLib's C extension segfaults:

```
Fatal Python error: Segmentation fault
  av.py:141 in _av_labellib   <- compute_av <- compute_avs_for_structure
  evaluate.py:234 in evaluate_trajectory
  pair_selection.py:292 in compute_efficiency_matrix_from_evaluators_trajectory
```

**Honest attribution:** the crash appeared when that test's fixture moved from
an mdtraj-written XTC to a ChiSurf-written DCD, so it is *plausibly* mine — but
the coordinates round-trip correctly and the PDB carries the right element
column, so what changed is the numbers reaching an AV grid, not their meaning.
An accessible volume around three atoms is degenerate input either way, and a
segfault is never the right answer to it. **Do not assume the port is
innocent** without checking; equally, do not assume the fixture is the only
caller that can reach this.

**Where to start:** guard `_av_labellib` against a structure too small to grid
(it should raise, not crash), then re-point the fixture at a real structure —
a 3-atom AV asserts nothing useful about efficiency matrices anyway.

**This is why `mdtraj` is still declared.** Every import of it is gone from the
tree, but a suite that segfaults cannot show the removal is safe, and removing
a dependency on the strength of a crash would be backwards.

## storage: a borrowed `Column` from the columnar store is not safe to cache

**2026-08-06.** In the simulation library's `DataStore`, a `Column` handed out
by `add()` or `store[i]` is a borrowed reference into the store's column
container. A structural change can invalidate it, and the stale proxy does not
raise — it reads freed memory and answers with an empty name and an empty
array. The symptom is a column that silently goes blank, which no assertion
catches.

**The append case is fixed at the source, and is not yet in any built
environment.** The container is now one whose references survive an append
(`std::deque`, `modules/core/include/DataStore.h`) — verified by building the
library into a scratch prefix and holding a proxy across fifty `add()` calls:
name, data and write-through all intact, where the shipped build reports `''`
and `[]`. **That change is uncommitted in the library checkout and the binary in
this environment is still the old one**, so every environment here still dangles
on append until it is rebuilt.

**Removal still invalidates, and unevenly.** `remove_column` invalidates some
proxies and not others depending on the index and the container — a vector erase
at index 2 leaves index 0 readable, a deque erase does not. So *whether* a given
proxy survives is not a contract in either build.

**The rule is therefore unchanged: never cache a proxy.**
`chisurf/core/datastore.py` re-fetches through `column_at()` and
`DataStoreSource` goes through it for every access. `test/test_datastore_seam.py`
asserts the positive invariant — `column_at` answers with live data across both
an append and a removal — and passes against the shipped build *and* the fixed
one. It deliberately does **not** assert that a stale proxy breaks: that would
be pinning a bug whose presence depends on the build.

**Two smaller gaps found the same way**, both real and both worked around in
`chisurf/core/datastore.py`: a boolean column has no zero-copy view and decodes
through a per-row Python loop (so a write through the returned array is silently
lost, and filtering a large boolean column is O(n) in Python), and `mask_numpy()`
returns a copy (so a single-cell mask change is a read-modify-write of the whole
mask). Both are listed in the [columnar-store concept](../subsystems/columnar-store.md).

## build: the sibling environment gets a build it cannot load

**2026-08-06.** The photon library is built into the pixi environment and
symlinked into the sibling conda environment. The two disagree about HDF5 — pixi
solves 2.1 (`libhdf5.320`), the conda environment carries 1.14 (`libhdf5.310`) —
so the shared build is unloadable in the sibling:

```
ImportError: dlopen(...): Library not loaded: @rpath/libhdf5.320.dylib
```

**`build-tttrlib` reports success**, because it verifies the environment it
installed into and that one is fine; the sibling breaks silently and shows up
only when a suite next runs there. Worked around by giving the sibling its own
build installed as a real directory instead of a symlink (recipe in
[build and env](../workflows/build-and-env.md)) — **which the next
`build-tttrlib` undoes**, re-creating the symlink.

The durable fix is one of: pin the same HDF5 in both environments, or make the
link step verify that the extension actually *loads* in every environment it
links into rather than only in the one it installed to. Neither is done.

## storage: seven pandas HDF5 call sites are dead in a freshly solved environment — RESOLVED 2026-08-06

**Resolved** by [PRD-82](../prds/prd-82.md) stage 2: all seven writers now go
through `chisurf.core.datastore.write_table`, which writes one dataset per
column and needs no optional HDF5 package. `to_hdf` and `HDFStore` appear
nowhere in the shipped package and `test/test_pandas_hdf5_seam.py` fails on one
coming back. Kept here for the part that is **still true**.

**A file written by an EARLIER release still needs that optional package to
open.** `read_table_frame` tries the columnar layout first and falls back to the
frame reader, which needs it; where it is absent the fallback is a named
`LegacyTableError` rather than an empty table, so the failure is legible instead
of silent. That is no worse than before — those files were unreadable there
either way — but it means the removal is complete for *writing* and not for
*reading history*.

A reader for the frame layout was written inside the simulation library and
**reverted deliberately**: that library reads photon data and has no business
knowing another ecosystem's container layout. Do not propose it there again.
The remaining options, neither taken: convert old files on open (needs the
package once, on a machine that has it), or read the layout in ChiSurf, which
means a new HDF5 dependency for a legacy path. Both are worse than the named
decline until someone has a file they actually cannot open.

## globalview: two graph builders, and they have already drifted

**2026-08-06.** The parameter graph is built twice. The plugin builds it locally
(`chisurf/plugins/core/globalview/api/graph.py`); the server builds it again, by
hand, for the `graph.build` RPC (`chisurf/server/services/graph.py`,
"mirrors the client-side logic"). They are not one implementation with two
transports — they are two implementations of the same contract, and today they
were fixed twice for the same defect: a link edge resolved by parameter *name*,
which drew an arrow from a follower to every same-named parameter in the session
(three fits with a `tau1` turned one link into three arrows, two of them false).
The server copy has also never had the `group` node type the plugin grew for
out-of-fit parameter groups, so a network fetched over RPC is missing every
plugin working model that a locally built one shows.

The durable fix is to delete the server copy and have `graph.build` call the
plugin's Qt-free `api/graph.py`, which already returns plain dataclasses. It was
not done here because the plugin `api` package has not been checked for
Qt-freeness in the server's import path, and unifying it is a wider change than
the GUI work that surfaced the defect. Until then, **a change to one builder must
be made to the other**, and the record is
[core tools](../plugins/core-tools.md#global-view-the-parameter-network).

## The assistant still fabricates a citation now and then

**2026-08-06.** Over thirteen live questions on `mistral-large-latest`, two
answers named a page that does not exist — `docs/concepts/pda.md` and
`docs/guides/42_fret_from_bursts.md`. Both are plausible file names for pages
that *could* exist, which is exactly why the model wrote them. Nothing reached
the reader: `ask.verify_citations` resolves every path, strikes the dead ones
and reports them, and both the panel and the CLI say so in as many words. So
the guard works and the behaviour underneath does not.

Worth knowing before trying to fix it: the fabricated paths appear **alongside
real, opened ones** in the same answer, so "did it read anything" does not
catch it — only resolving each path does. The obvious next step is to give the
model the page list it is allowed to cite (the `related` list already in every
`read_documentation` result), or to feed the struck paths back for one
correction turn the way `READ_FIRST` does for an unread answer. Neither was
done here because the current behaviour is honest and visible, and a second
retry turn costs every answer a round trip to fix one in six.

## (closed) The documentation assistant has never answered a question from a real model

**Closed the same day** — a working key arrived and the battery was run; see
the log entry and [LLM agent](../subsystems/llm-agent.md). What follows is the
original note, kept because it says what the measurement is.

**2026-08-06.** `chisurf/plugins/core/help/api/ask.py` and everything behind it
are covered by scripted-model tests (the restricted registry, the citation
collection, the panel's rendering of an answer, a no-read answer and a
failure), and the retrieval underneath is covered by asserting *which page*
comes back for a question. What has **not** happened is one end-to-end run
against a live provider: on the machine this was built on, the configured
Mistral key expired the same day (HTTP 401, "Your API key expired on
2026-08-06") and the OpenRouter account has no credit (HTTP 402, "can only
afford 213" of the 4096 reserved tokens). Both error paths are reported
clearly, which is itself worth something, but the *answer* path has only ever
run against `ScriptedLLM`.

What that leaves unknown is not the plumbing — it is whether the prompt and the
`answer-from-docs` skill actually make a model browse before it answers rather
than answering from memory and citing nothing. The measurement is exactly the
one the panel already shows: run `csc help ask "what does the gamma factor
correct for?"` with a working key and check that `answer.pages` is non-empty
and names `docs/concepts/accurate_fret.md`. If it comes back empty, the fix is
in the skill, not in the harness.

## An in-flight rename left `test_an_ambiguous_model_name_asks_for_the_full_one` red

**2026-08-06.** `test/agent/test_tools.py` fails in the working tree, and it is
not this change: another instance is renaming the TCSPC model from
`"Lifetime (new)"` to `"Lifetime"` and applied the rename mechanically to the
ambiguity fixture, which turned a prefix-only case into an exact-match one.
With the registry `["Lifetime", "Lifetime mixer"]`, asking for `"Lifetime"` is
not ambiguous — `resolve_model_name` finds an exact match and returns it, which
is the documented and correct precedence. The test is the defect, not the code:
the fixture needs a registry where no exact match exists (`["Lifetime ",
"Lifetime mixer"]`, as it effectively was before). Left alone here because the
file has another instance's uncommitted edits in it.


## Mutagenesis resets the view, and hidden waters come back

**2026-08-07**, reported by the user against the state-based wizard
(`03a04ca07`). Two defects, both about state the wizard is not preserving.

**1. The view is reset.** Something in the mutagenesis flow still moves the
camera. The build and the rotamer step are each wrapped in
`_wizard_keeps_the_camera` (`cmd/interactions.py`), and
`test_the_wizard_never_moves_the_camera` asserts `get_view_state()` is
unchanged across `wizard target` and two `wizard rotamer, next` — so the path
that does it is **not** one of those two, and the guardrail passes while the
user sees the fault. Candidates, in the order worth checking:

* `wizard apply` and `wizard clear`/`done` — neither is wrapped. Apply
  rebuilds the source object, which is exactly the operation that re-derives
  the scene centre and radius;
* `_wizard_delete_preview` — removing an object changes the scene bounds the
  same way adding one does;
* entering the wizard at all (`wizard mutagenesis`), or the residue pick that
  precedes it.

Take the measurement the same way the earlier camera bug was finally caught:
`get_view_state()` before and after **each** command in a full session
(`wizard mutagenesis` → pick → `target` → step → `apply` → `done`), not only
the two already covered. Note the trap recorded in the parity concept: the
symptom reads as *darkness* in a screenshot, because the molecule recedes
rather than the lighting changing.

**2. Hidden waters reappear.** Visibility set before the wizard runs is lost —
`hide solvent` (or any scoped `hide`) comes back on. Almost certainly the same
root cause as the first: whatever rebuilds the source object on Apply is
restoring the representation masks from the payload rather than carrying the
object's current ones across. If so, one fix closes both, and the test should
assert the *masks* as well as the view state, since a rebuilt object with
default visibility is indistinguishable from a correct one in a mesh count.

**Tried to fix, and it does not reproduce through the command path.** Measured
on 148L, driving the whole flow as commands (`wizard mutagenesis` → `target` →
`rotamer, next` → `apply` → `done`) and printing the 18-float view state and
the per-atom masks after each:

* the view is **identical at every step**, apply included — position
  `[0, 0, -467.83]`, near/far/fov `[1.65, 660.39, -20]`. So `apply` being
  unwrapped is *not* the cause, and wrapping it would fix nothing;
* the masks resize correctly: `sticks_mask` goes 1363 → 1370 with the atom
  count when a THR becomes a TRP, rather than being dropped or left stale;
* the water half could not be exercised at all — **148L carries no waters**
  (`tot=0`), so a fixture with solvent is needed to see it.

That leaves the **GUI interaction path**, which is what the report came from
and what none of this touched. Two candidates worth taking first:

* the mouse mode itself. In 3-Button Viewing, `SnglClk` is **Cent** — a single
  click centres on the atom under the cursor. Picking the residue to mutate is
  a click, so the "reset" may be the mouse mode doing exactly what the panel
  says it does, and the fix (if any) is that picking *for the wizard* should
  not re-centre;
* whatever the object menu's **H** button emits for waters, followed by
  `_refresh_objects_from_viewer` after apply. The command spelling is
  `hide everything, solvent`; a bare `hide solvent` is rejected
  ("Unsupported representation for show/hide: solvent"), so the two paths may
  not be setting the same state.

Reproduce with a structure that has waters, driving the GUI rather than the
command line — the standing correction in the parity concept applies: a test
that calls the handler cannot see what the widget does.

## structure: `ProteinCentroid` cannot coarse-grain nucleic acids

**2026-08-10.** Found while making `calc_internal_coordinates_bb` survive
crystallographic PDB files (three separate crashes, all fixed:
`KeyError: 'H'` on structures without hydrogens, `KeyError: 'CA'` on waters,
`ValueError: -1 is not in list` on the absent-atom sentinel). One failure was
left, because it is a capability gap rather than a guard:

```
>>> ProteinCentroid('test/data/atomic_coordinates/pdb_files/1rtd.pdb')
KeyError: np.str_('DG')      # protein.py, to_coarse
```

`residue_atoms_internal` is keyed by amino-acid name only, so `to_coarse`
raises on the first nucleotide. **1RTD is this project's designated
protein + DNA/RNA fixture** ([testing](../workflows/testing.md)), which means
the coarse-grained path has never been exercised on the structure class it was
supposed to be tested against — the two combined-molecule tests in the tree use
the all-atom path.

Not fixed here for one reason worth stating: `chisurf/core/structure/protein.py`
is route `imp` in the [numba retirement](../subsystems/numba-retirement.md) —
its counterpart already exists as `IMP.cgmol.protein`, and CLAUDE.md records
that molecular modelling has migrated to imp-tricks. Adding nucleotide
templates here would be work thrown away at that port. **Check whether
`IMP.cgmol` already handles nucleic acids before writing any**; if it does, this
closes by deletion.

## `pixi.toml` requires `wgpu`, and the lock file has never contained it

**2026-08-10.** Re-recorded after being removed from this file without a fix —
the entry went, the condition did not.

* `pixi.toml:78` declares `wgpu = "*"` as a conda dependency.
* `grep -c wgpu pixi.lock` returns **0**. The lock has no such package at all,
  so it predates that line and is stale against the manifest.
* `pixi run --frozen <task>` therefore still works — it ignores the manifest and
  uses the lock as-is. **Plain `pixi run` re-solves**, which is where this bites.

On conda-forge the package providing the `wgpu` Python module is named
**`wgpu-py`**; `wgpu` is a different (Rust) package. If the solve is failing,
that rename is the reason and the fix is one word in `pixi.toml`. Confirm with a
full `pixi install` before changing it — this entry deliberately stops short of
claiming the solve fails, because that was not re-measured here, only that the
lock cannot satisfy the manifest.

It matters out of proportion to its size: `pixi` is the single sanctioned
environment and build tool, every CI workflow uses it, and `build-extensions` is
a `depends-on` of every `test*` task. A broken default solve takes the whole
sanctioned test path with it, and `--frozen` masks that locally.

## ✅ FIXED — ChiMOL's chrome was laid out into boxes too small for its own text

**Found 2026-08-11** while capturing the before-half of the chrome for the
GPU-quad port; **fixed the same day** ([chimol-web](/plugins/chimol-web.md)).

Reported first as "an object menu runs off the right edge of the window", which
is what it looks like. It is not a clamping bug -- top-level menus *are* clamped
to the viewport and submenus already flip sides. The cause is one constant:

```python
char_w = self.FONT_PT * 0.62      # 6.2 px at 10 pt
```

Menlo at 10 pt advances **8.5 px**, so every box in the panel was budgeted 22 %
narrow. `assign sec. structure` was given 130 px and needs 177; because a menu
is clamped against the *right* edge, the 47 px of overflow ran off-screen
instead of merely overlapping. The truncated mouse-mode block
(`Mouse Mode 3-Button Viewin…`) and the cramped sequence strip were the same
constant, which is why they looked like three separate defects.

The width now comes from the baked glyph atlas -- the thing that actually draws
the text -- via `internal_gui.char_width()`.

A second, independent bug surfaced with it: `column_width` starts at PyMOL's
`internal_gui_width` of 220 and **only the splitter drag consulted
`minimum_column_width()`**, so until someone dragged it the mouse-mode block was
laid out wider than the column that positions it. `layout()` now holds the
column to its own minimum, which is the invariant
`test_internal_gui.py` was already asserting after a drag.

Control inventory is unchanged across the fix (11/56/66/81 reachable controls in
the four captured states); only the widths moved. Baselines in
`test/renders/chrome_baseline/` were deliberately re-taken.

## ✅ RESOLVED — ChiMOL's browser page renders; drive it with Playwright, not the Chrome tools

**Found and resolved 2026-08-11** ([chimol-web](/plugins/chimol-web.md)).

The browser tools drive a Chrome that is **not on the same host** as the shell.
A dev server that answers

```
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8792/     # 200
```

gives that Chrome `ERR_CONNECTION_REFUSED` at the same URL, on `localhost` and
`127.0.0.1` alike, with the shell sandbox disabled. Every read landed on
`chrome-error://chromewebdata/`, which is also why `navigator.gpu` read as
false -- it was being read on the error page.

**Playwright's Chromium runs in the same sandbox as the shell and works.** With
`--enable-unsafe-webgpu`, `navigator.gpu` is present and the page renders.
`test/test_browser_render.py` does the whole thing -- server, browser, Pyodide,
device, frame, pixels -- and is marked `slow`.

So: **to look at chimol in a browser from an agent session, use Playwright.**
The Chrome tools cannot reach a locally served page on this machine.

## ChiMOL's WGSL backend silently ignores `px_mode`, and selection markers look wrong

**Found 2026-08-11** from a user screenshot: selected atoms draw as red dots of
wildly varying size scattered through the cartoon, where PyMOL draws even pink
markers of a fixed pixel size.

`core/viewer.py` sets `meta["px_mode"] = True` in **three** places — the
`dots` representation (`:8492`), an overlay path (`:8564`) and the selection
indicator (`:8942`) — and `px_mode` appears **nowhere** in `wgpu_backend.py` or
`compute.py`. The backend's geometry signature reads only `meta["size"]` and
`meta["world_radius"]` (`wgpu_backend.py:906`), so a builder asking for
pixel-mode markers gets whatever that pair happens to mean. Size varying with
depth is what world-radius spheres do and what pixel-mode markers must not do,
which matches the screenshot. `_selection_marker_width` computes its value in
**pixels**, clamped to PyMOL's 3–10 band, so the units are certain at the
producing end.

**Not fixed, and not diagnosed past this point.** The open question is what the
impostor pipeline does with `size` when `world_radius` is false, and whether the
fix belongs in `impostor.wgsl`, in the interleave, or in teaching the backend to
honour `px_mode`. This is the "silently degraded path" shape the project rules
warn about: the flag is not rejected, it is simply never read.

## ChiMOL's test suite cannot collect while `chimol/` is on `sys.path`

**Found 2026-08-11.** `pytest chisurf/plugins/chimol/test/...` fails at
configure time:

```
INTERNALERROR   File ".../pdb.py", line 74, in <module>
    import cmd
ImportError: attempted relative import beyond top-level package
```

chimol has a top-level `cmd` package, so anything putting
`chisurf/plugins/chimol/chimol` on `sys.path` shadows the standard library's
`cmd` — which `pdb` imports, which pytest's debugging plugin imports at
configure time, before a single test runs. Same hazard CLAUDE.md already records
for `chisurf/math/` and the stdlib `math`, and the reason chimol's `host`
package is deliberately not called `platform`.

The suites run when the path is clean. Find what inserted it before trusting a
green *or* a red run — a collection error here says nothing about the tests.

## chimol: C > "by element" sets an object-wide colour *mode*, so it paints the whole molecule and not the selection

**Found 2026-08-11, reported by tpeulen:** "the coloring menu color by atom of
selection just colors the entire protein by residue color not by atom". Two
defects in one menu entry, and a missing menu.

**1 — the selection is ignored.** `chrome/object_menus.py:537` issues
`color byelement, {sele}`. In `cmd/rendering.py`, `color()` normalises
`byelement` to the mode `by_element` (`_normalize_color_mode`, l. 1601) and
hands it to `_apply_color_mode` (l. 1612), which is explicit about what it then
does — l. 1626: *"The colour mode is a property of an object, not of individual
atoms, so a selection here picks which objects it is set on"*. So the selection
is resolved only far enough to name the objects it touches; every atom of each
of those objects is repainted. Selecting one residue and colouring by element
recolours the whole protein. Worse, `_apply_color_mode` calls
`clear_color_overrides()` first, so it also **discards** whatever per-atom
colours were already there.

The correct path already exists in the same package and is unused by the menu:
`cmd/presets.py:252` `_color_by_element(sel, carbon=None)` writes per-atom
overrides through `viewer.set_atom_color_override` and its docstring gives the
reason — *"because a mode belongs to a whole object and this has to reach a
subset"*. The presets (`preset simple`, `ligands`, …) get this right; the C
menu does not.

**2 — "by residue colour, not by atom" is the cartoon path.** For a molecule
shown as cartoon the mode is consumed at `core/viewer.py:9287`, which builds
`_colors_per_ca` from the **CA atoms' elements** — every CA is carbon, so the
by-element mode has nothing to vary over and the ribbon does not turn CPK. What
the user sees instead is the previous per-residue colouring, unchanged.

**3 — the CNOS menu is missing.** PyMOL's C > "by element" is not one entry, it
is 49 (`junk/pymol-open-source/modules/pymol/menu.py:404`, `by_elem`):

- the first entry, `util.cnc(sele)` — the **CNOS** case the user asked for:
  colour H/N/O/S by element and **leave carbon alone**;
- 8 x `util.cba(<carbon_colour>, sele)` — colour by atom with a chosen carbon
  (tv_green, cyan, lightmagenta, yellow, salmon, grey90, slate, orange);
- submenus "set 2" … "set 5" (8 more carbon colours each, `by_elem2`–`by_elem5`)
  and "set 6/H" (`util.cbh`, 8 hydrogen colours).

chimol's `COLOR_MENU` has a single child, `by element`. `_color_by_element`
already takes the `carbon` argument these 40 entries need, so the menu data is
the gap, not the machinery.

**Where a fix goes:** make `COLOR_MENU`'s by-element children call the per-atom
path (a `cnc` / `cba` command, or `util.cnc`-equivalents) instead of
`color byelement`, and leave `color by_element` as the object-wide mode it
documents itself to be. Do not "fix" it by teaching `_apply_color_mode` to mask
atoms — the mode genuinely is per object, and `by_residue`/`by_ss`/`by_chain`
share that path.

**Not verified in a running viewer.** Read from the source; no screenshot taken.
The cartoon claim in (2) in particular should be confirmed against a rendered
frame before it is treated as settled.

## chimol: the mutagenesis wizard leaves a second sequence row behind

**Found 2026-08-11, reported by tpeulen with a screenshot.** After a mutation
the Sequence strip shows two rows — `1f5n` and a second row labelled
`mutation` — while the object panel on the right lists only `all`, `1f5n`,
`sele`. The extra row persists after the wizard has finished.

`mutation` is a real object by design: `cmd/interactions.py:621`
`_wizard_show_states` creates it (PyMOL's `do_library` does the same, one state
per rotamer) and `PREVIEW_OBJECT = "mutation"`. The sequence view builds one row
per entry in `_object_store` (`hosts/qt/window.py:1178`), so while the
preview exists a `mutation` row is expected.

**The leading hypothesis is refresh ordering in `_wizard_finish`**
(`interactions.py:838`), which runs:

1. `_wizard_commit` → `_apply_mutation`, and *that* is what refreshes the UI —
   `interactions.py:396` calls `_refresh_objects_from_viewer`,
   `_update_sequence_view`, `sync_internal_gui`. The `mutation` object is
   **still present** at this point, so the sequence view is rebuilt *with* its
   row;
2. `_wizard_delete_preview` (l. 805) → `viewer.remove_object(preview)`;
3. `viewer._update_view()` — a 3D redraw only.

Nothing re-runs `_update_sequence_view` after step 2, so the row outlives the
object. The same hole is in `_wizard_show_states`, which refreshes the object
list when the preview appears but never the sequence view.

**What does not fit, and should be checked first.** If both refreshers ran at
step 1 the *object panel* should be equally stale, and the screenshot shows it
clean — so either something else re-lists objects afterwards, or
`remove_object` reaches the panel by a route the sequence view does not.
Establish which before writing a fix.

**Also worth confirming:** the `mutation` row in the screenshot appears to span
the full 479–555 axis, but the preview carries a *single* residue — every atom
row is stamped with the source residue's `res_id`/`chain`
(`interactions.py:640`). Under `build_residue_alignment` that should render as
one letter in a row of gaps. If the row really is full-length, there is a
second defect in how a one-residue object is aligned, independent of the
staleness above.

## RESOLVED 2026-08-11 — chimol: the viewport's "Selecting Residues" line was decorative, and only the residue level existed

**Found 2026-08-11, user-reported** ("missing feature selection of CA, atoms,
currently only residues work"). PyMOL's mouse block carries a selection *level*
— Atoms / Residues / Chains / Segments / Objects / Molecules — and clicking the
word cycles it. chimol paints the line and stops there:

* `chrome/gui.py:398` `self.selecting = "Residues"`, painted at
  `:1835` and **never assigned again**;
* `core/viewer.py:2461` `self.selection_mode: str = "Residues"`, which has no
  other reader or writer in the tree.

So the level is a constant, there is nothing to cycle it with, and no code
consults it when a click lands.

**The blocker is the selection model, not the click.** The pick is already
atom-precise: `handle_mouse_click` (`view.py:4609`) resolves
`picked_atom_idx` and emits `atomSelectionChanged([idx])`. It then throws that
precision away — it maps the atom to its residue index and calls
`_apply_selection_indices`, whose entire state is `self._selected_residues`, a
list of **residue** indices (`:4734-4808`). Everything downstream is indexed the
same way: `residueSelectionChanged`, `objectResidueSelectionChanged`,
`refresh_selection_highlight`, the sequence strip, and the `sele` object.

That splits the work in two, and they are not the same size:

* **Chains / Objects / Molecules are cheap** — they are still sets of residues,
  so the click expands the picked atom to its chain's or object's residue
  indices before `_apply_selection_indices`. No model change.
* **Atoms (and "CA only") need an atom-indexed selection set**, because a
  residue-index list cannot express "one atom of this residue". That reaches
  the highlight renderer, the `sele` object and the sequence strip, all of which
  currently assume whole residues.

Do the cheap half first only if the split is stated; shipping Chains and
Objects while Atoms silently still selects the whole residue would make the
line *more* misleading than a constant, not less.

## RESOLVED 2026-08-11 — chimol: no mouse-driven measurement; PyMOL's Measurement wizard was missing

**Found 2026-08-11, user-requested** ("add measurement feat, like in pymol, meas
distance with mouse and clicking").

Both halves already exist and are simply not joined:

* the **measurements** — `cmd/measurements.py` has `distance`/`dist` (`:156`),
  `angle` (`:828`) and the dihedral, all drawing into `viewer._measurements`,
  which the scene already renders;
* the **wizard framework** — `cmd/interactions.py` runs the mutagenesis wizard
  with a viewport panel, prompt, per-step rows and a Done/Apply lifecycle
  (`_wizard_finish`, `_wizard_refresh`, `_wizard_gui`), and `menu_bar.py:175`
  lists wizards;
* the **atom-precise pick** — `handle_mouse_click` already resolves
  `picked_atom_idx` before discarding it for the residue (see the entry above),
  which is exactly the input a measurement needs and the reason this does *not*
  depend on the selection-level work.

What is missing is a `wizard measurement` that collects picked atoms and, at
two/three/four picks, calls the existing command. PyMOL's modes are the spec:
distance, angle, dihedral, plus its "no wizard" reset.

**Watch for:** the picked index is into `_all_atom_coords`, whereas the
measurement commands take *selections* — a pick has to be turned into an atom
expression (object, chain, resi, name) or the measurement API given an
index-taking entry point. Choose one deliberately; going through a selection
string round-trips through the parser on every click.

## RESOLVED 2026-08-11 — chimol: `distance` reported scene units and drew its dashes in the wrong place

**Found while building the measurement wizard, which depends on this code.**
Two mirror-image defects in `cmd/measurements.py`, both from the same cause:
`_resolve_selection_to_atom` returns **scene** coordinates —
`(xyz - raw_center) * _scale_factor`, and `_scale_factor` is **10**.

* the **value** was the scene length: measured against 148L's own file,
  `distance resi 1 and name CA, resi 21 and name CA` reported **258.450** for a
  **25.845 Å** pair. `rms`/`align` already carried the same correction
  (`measurements.py:1100-1105`), which is why the fault was confined to
  `distance`/`angle`/`dihedral`;
* the **positions** were double-transformed: `MolView._update_measurements`
  transforms whatever it is given into scene space unless
  `transform_to_scene` is false, so a scene coordinate stored as a measurement
  position is scaled and centred a second time. Its bbox came out at ±200 for a
  molecule spanning −11…68.

The *set* paths (`dist ... mode=2` and the rest) were **already right** —
they work from `atoms["xyz"]` — so the two halves of the same command disagreed
with each other, which is what made this hard to see: polar contacts drew
correctly and a two-atom measurement did not.

**Fixed** by `_scene_point_to_world`, applied in `distance`, `angle` and
`dihedral`. Guardrail: `test_measure_suite.py::test_two_atom_distance_is_in_angstrom`,
which checks against coordinates parsed from the PDB rather than against another
part of the same code — the one measurement here with a reference value.

## RESOLVED 2026-08-11 — chimol: a residue id is not unique across chains, and the selection matched on it alone

**Found while adding the `Atoms` selection level, which made it visible.**
`_selection_atom_positions` and the pick-to-residue lookup in
`handle_mouse_click` both matched atoms to residues on `res_id`. Residue ids
restart per chain, so on 1RTD (eight chains, each numbering from 1):

* selecting **one residue** marked **104 atoms** instead of 19 — every chain's
  copy of that number;
* one picked **atom** mapped back to **eight residues**;
* `handle_mouse_click` took `matches[0]`, i.e. the *first* chain's copy, so
  clicking a residue in chain E could select chain A's.

The missing half of the key was already in the tree: `_residue_chain_ids` is
built alongside `_residue_ids` at load and was unused here.

**Fixed** by `MolView._atom_residue_indices`, which keys on (chain, residue id)
and returns a per-atom index into the residue table, with `-1` for an atom whose
residue is not in it (a ligand where the trace is protein-only) rather than
silently borrowing a neighbour's. Every count in
`test_selection_levels.py` is cross-checked against the atom table, and the
fixture is deliberately **1RTD, not 148L**: a single-chain structure cannot tell
a chain-aware lookup from an id-only one, which is how this survived.

## RESOLVED 2026-08-11 — chimol: five reports on the viewport's own chrome

All five are the same shape of fault, which is why they are recorded together:
**a value that was configured, loaded or drawn, and read by nothing.**

* **The in-viewport prompt had a black backdrop** (`CMD_BG = (0, 0, 0, 190)`),
  which is invisible on the default black background — the prompt read as text
  lying on the molecule — and needlessly heavy on a white one. Now the same
  semi-transparent grey as the system-info panel, which darkens white and
  lightens black.
* **3-D labels were drawn at a hard-coded 10 points** while `label.size` sat in
  the display config at **14**, read by nothing: the setting was documented,
  stored, and could not change anything. `paint_labels` now takes the size,
  `WgpuRenderer._label_size` supplies it, `label_size` / `label_color` are
  registered settings, and the default moved to **16** (migration 17) because
  14 was never what anyone saw and 10 was reported as too small.
* **A measurement whose segment produced no dashes still drew its number** — a
  value floating over the molecule attached to nothing, indistinguishable from a
  label that has come adrift. `_dash_segments` returns nothing for a zero-length
  segment; the label is now suppressed with it.
* **A measurement's first pick drew nothing at all**, so a mis-aim and a
  mis-click looked identical. Picked atoms now carry the selection marker via
  `MolView.set_pick_markers` — deliberately *not* the selection: they never
  reach `sele` and they clear when the group becomes a measurement.
* **The sequence strip ran every chain into one row** named after the object.
  Residue numbers restart per chain, so the same number appeared several times
  with nothing to say which chain it belonged to. Now one row per chain,
  labelled in PyMOL's slash syntax (`1f5n/A`), each carrying
  `residue_indices` — the map back to the object's residue indices.

**The trap in the last one**, and the reason it needed care: a per-chain row's
columns are **not** the object's residue indices, and everything the strip talks
to speaks the object's. Without the map, clicking chain B's third residue
selects the object's third, which is chain A's — silently. Rows are also matched
by `object_id` now rather than by label, because the label carries the chain.
Pinned by `test_sequence_chains_and_labels.py`, which checks the rows *partition*
the object exactly and round-trips a selection through a later chain.

### Not reproduced: "the measurement label jumps around when I change the view"

Reported with a screenshot showing the number far from its dashes. **In the
current tree the label sits exactly on the segment midpoint and tracks the
camera** — `project_to_screen` agrees with the backend's own MVP to the last
decimal at four rotations, checked against `perspective`/`view_matrix` rebuilt
from `_scene_viewport`.

The likely cause is the double-transform fixed the same day (see the entry
above): `distance` stored **scene** coordinates and `_update_measurements`
transformed them into scene space a second time, which puts a measurement's
whole drawing somewhere else and moves it at a different rate from the molecule
as the camera turns. If it recurs after a restart, the thing to capture is
whether the *dashes* are also displaced or only the number — they are built from
one array, so a genuine split between them would mean something new.

## RESOLVED 2026-08-11 — chimol: the system-info panel covered the in-viewport prompt

**Reported with a screenshot** showing `(no system loaded)` sitting over the
`ChiMOL>` line. Both are anchored bottom-left of the same corner, and only one
of them is a Qt widget: the panel is a `QPlainTextEdit` stacked on the surface,
while the prompt and its feedback are painted **into** the surface by the chrome
painter. Qt therefore knows nothing about the prompt, and the panel — laid out
with `full_height` and `AlignBottom` — ran straight over it. It became obvious
only once the panel gained a backdrop the same day; before that the two sets of
text simply overprinted on black.

**Fixed** by giving the container grid a second row whose only job is to be
empty: the renderer spans both (it draws the whole surface, prompt included) and
the panel spans the first. Its height is `InternalGui.command_area_height()`.

**That method returns the maximum, not the current height**, and the reason is
the point: the log grows and shrinks as commands run, so a panel laid out around
the *current* height would overlap for as long as it took a printed line to
trigger the next relayout — a bug that appears only after output, which is
exactly when nobody is looking at the panel. `visible_log` is capped at
`feedback`, so the ceiling is a constant and reserving it needs no upkeep.

**The guard is in two halves** (`test_sequence_chains_and_labels.py`), because
the two rectangles are laid out by different code at different moments and
comparing them directly measures whichever ran last as often as it measures the
bug: one half asserts the reserve is at least what the prompt uses, the other
that the panel stays out of the reserve.

## RESOLVED 2026-08-11 — chimol: the system-info panel was a Qt widget, and is now chrome

The overlap fixed earlier the same day was a symptom. The panel was a
`QPlainTextEdit` stacked on the surface while every other thing in the viewport
-- the object list, the sequence strip, the mouse-mode block, the prompt -- is
drawn *into* the surface by `InternalGui` through the six-operation
`Painter` interface and rasterised as GPU quads. A Qt widget cannot see chrome
painted into the surface, which is why it sat on top of the prompt, and the
first fix was a spacer row in the container's grid **guessing** how tall the
prompt would get.

**The panel is now `InternalGui`'s** (`layout_info`, `_paint_info`,
`INFO_BG`/`INFO_FG`/`INFO_EDGE`, `_wrap_lines`). Consequences worth having:

* one object lays out the strip, the panel and the prompt, so "above the
  prompt" is arithmetic rather than a guess -- there is nothing left to keep in
  sync, and the container's layout is a single widget again;
* it draws on the **GPU path** with the rest of the chrome, so it costs quads
  rather than a stacked widget's compositing, and it will follow the chrome
  into a browser, where a `QPlainTextEdit` could never have gone;
* the text is **wrapped by character count** -- the chrome's font is monospace
  -- which the widget used to do for free. A file path has no spaces to break
  at, so a long run is cut rather than allowed to run off the panel;
* a viewport too short for one line **drops the panel** rather than drawing it
  over the strip or the prompt. Keeping its height and overlapping is precisely
  what the widget did.

`set_system_info_text` / `set_system_info_visible` now only store and request a
repaint; the text and palette are *pulled* by `refresh_gui_state` at paint time,
as the sequence colours and the frame position already were. `info_overlay`'s
settings are unchanged and still honoured -- `MolView.info_overlay_colors`
converts them for the chrome, and `max_width` / `min_width` / `full_height` are
now the panel's own `INFO_MAX_CHARS` / `INFO_MIN_CHARS` and content height.

## chimol: density maps are slow, and the NPC load has regressed (2026-08-11)

Two performance reports, filed rather than fixed at the user's direction —
*"just note as issues and continue with migration"*. Neither is measured yet;
what follows is the starting point so the next session does not begin at zero.

### Density maps are slow

The instruction is explicit: **learn from ChimeraX how it does this.** That is
the right reference — ChimeraX's volume viewer is interactive on maps chimol
struggles with, and the techniques are documented rather than folklore. What to
look for, in the order they usually matter:

* **Multi-resolution / step.** ChimeraX draws a map at a *step* (2, 4, …) and
  re-contours at full resolution only when asked. chimol has
  `stride_for_limit()` for the point cloud but the **isosurface contours the
  full grid every time** — a 180³ map is 5.8 M cells per level per rebuild.
* **Region cropping.** ChimeraX contours a sub-box, not the whole map.
* **Caching the surface per (level, step)** so re-showing a level is free —
  chimol re-runs marching cubes.
* Its `Volume`/`GridData` split is worth reading directly: the data source, the
  region, and the rendering settings are three separate objects, which is what
  makes "re-contour at a different step" cheap to express.

The contour **drag** is already fixed (0 rebuilds while dragging, 1 on release,
see PRD-101 req. 2); this is about the rebuilds themselves.

### The NPC takes forever to load — a regression

Reported as a regression, so the suspects are recent work, and the most likely
are **mine, from 2026-08-11**:

1. **Per-chain sequence rows.** `_sequence_rows_for_object` splits the strip by
   chain in Python, walking every residue and building per-row lists. The NPC
   is an integrative model with a very large number of chains, so this went
   from one row to hundreds, each with its own list comprehension over residues
   — and it runs inside `sync_internal_gui`, which is called often.
2. **`MolView._atom_residue_indices`.** Added for the cross-chain fix. It is
   O(n log n) over *every atom* and is recomputed on **every call** —
   selection markers, every pick, every highlight refresh. On a bead model with
   hundreds of thousands of particles that is a per-click cost that did not
   exist before. It should be cached per object and invalidated on structure
   change; the state fields are already the place for it.
3. Less likely but cheap to rule out: the measurement rows now walk
   `viewer._measurements` on every `sync_internal_gui`.

**Measure before changing anything** — time a load of the `npc_integrative`
demo against the commit before 2026-08-11, and profile `sync_internal_gui`
separately from the structure read. The demo exists precisely so this is one
command.

### Resolved 2026-08-12 — and none of the three suspects above was the cause

Measured, as the entry above insisted. The `npc_integrative` demo took
**113.2 s** end to end on an Apple M1 Pro (offscreen WebGPU/Metal, 234,184
beads). It now takes **9.3 s** — **12.1x** — and the three suspects listed above
were not involved. They may still be worth fixing on their own merits; they were
not what made the demo slow. This is the entry's own advice paying off, and the
reason to leave the wrong guesses in place above rather than quietly deleting
them.

What it actually was, in order of size:

1. **`MolView.get_atom_sphere_data` was quadratic** — 88.7 s of self time across
   three calls. For each atom it ran `np.where(self._residue_ids == rid)` over
   the *whole* residue array to find its colour: 234,184 x 234,184 comparisons,
   5.5e10 of them. Replaced by a stable `argsort` plus `searchsorted`, which is
   the same answer — the stable sort is what makes the leftmost slot of a run of
   equal ids the *first* match the loop took — in N log N. Verified identical
   over 380 randomised trials covering duplicate ids, gaps, unmatched ids,
   unsorted input and string ids.
2. **Ambient occlusion recomputed on a colour change** — 4.7 s. Occlusion is a
   function of geometry alone, and `spectrum molecule` changes only colours, but
   the neighbour search ran again with the same points and the same radius.
   Memoised on a hash of the coordinates in the one place occlusion is already
   gated. Results are handed out read-only: a caller shading one in place would
   poison every later hit, and that is a bug found days later in a colour.
3. **Beads built one row at a time** — 2.7 s of `atom_row`, once per bead, each
   allocating its own one-element structured array. The vectorised builder
   already existed (`make_bead_rows`, written for the RMF reader); the mmCIF
   reader simply was not using it. Verified identical on all twelve fields of
   `ATOM_DTYPE` over 200 randomised trials.

The pattern in all three is the same and worth naming: **none was an algorithm
anyone chose**. Each was a per-item Python loop that was correct and
unremarkable at a few thousand atoms and became the whole runtime at a few
hundred thousand. The remaining 9.3 s is dominated by one genuine neighbour
search (~3.0 s) that now runs once.

Reproduce with the profile harness described in
[chimol-viewport-ui](../plugins/chimol-viewport-ui.md).

### Open, in imp-tricks — the in-tree Martini table is not Martini 3

Found 2026-08-12 while assessing imp-tricks' Martini support for
[PRD-102](../prds/prd-102.md). Not fixed here because it lives in imp-tricks and
that work is scoped as research; recorded so it is not rediscovered.

* `MartiniParticle._size_nm` returns one sigma per size-class prefix. The shipped
  Apache-2.0 `martini_v3.0.0.itp` has several per class — regular beads take
  0.47 **and 0.50** (divalent ions), and tiny beads take **fourteen** distinct
  values from 0.34 to 0.438. Read the matrix; do not assume one sigma per class.
* `_well_depth` is a five-value lookup on a bead's first letter, collapsing all
  of P1…P6 to 4.0 kJ/mol. The real matrix has thousands of distinct epsilon
  values. As written this is a different force field wearing Martini's name.
* Synthesised missing-residue beads hardcode mass 72.0 regardless of bead size;
  the real masses are 72 / 54 / 36 for regular / small / tiny.
* A vendored `Martini3-IDP-parameters` directory carries **no license**. It is
  Martini3-IDP ([10.1038/s41467-025-58199-2](https://doi.org/10.1038/s41467-025-58199-2));
  resolve the license before anything ships with it.

Consequence for users: a Martini-shaped model here is a candidate for simulation
only through an exported GROMACS topology, never through the in-tree scoring.

### Open 2026-08-12 — chimol: the frame is 94 % chrome, not molecule

Measured on the same M1 Pro, same NPC, offscreen WebGPU/Metal, once the load
costs above were fixed. Frame time went **45.7 ms -> 36.9 ms** (22 -> 27 fps)
by caching the sequence gradient, and the profile then says plainly where the
rest is:

* `_chrome_quads` is **37.8 ms of a 41 ms frame**. It rebuilds **~2,800 quads
  and ~330 text runs from scratch every frame**, in Python.
* The molecule itself barely appears in the profile. It is built once and drawn
  by the GPU; drawing 234,184 beads is not what costs.

So "chimol's UI is slow" and "the NPC demo is slow to interact with" are the
same defect, and it is **not** a rendering-scale problem. The chrome is
immediate-mode — every panel, row and glyph re-emitted per frame — and the
sequence strip of an integrative model with hundreds of chains is thousands of
cells wide.

The fix is a dirty-flag cache on the chrome quad buffer: the chrome changes on
hover, focus and state, not on camera motion, and camera motion is when frames
matter. **Not done here** because `internal_gui.py` and `emtk/*` are
being actively edited by another agent (+2,496 uncommitted lines, and the chrome
baseline PNGs themselves are modified), so it would collide.

Note for whoever picks it up: `test_chrome_painter.py`'s five baseline
comparisons are **currently failing in the working tree** for that same
in-flight reason, so they cannot be used as a regression check until that work
lands. Confirmed not caused by the colour caching above —
`_build_sequence_gradient_colors` is called **zero** times during those tests.

One caching trap, already paid for once: the gradient cache first handed out its
array **read-only**, to stop a caller recolouring the shared copy. That is the
right instinct and it immediately found two real in-place writers (`spectrum`,
and the per-atom sort path) — but as a shipped behaviour it turns aliasing into
`assignment destination is read-only` raised from inside a command that did
nothing wrong. It now returns a copy, which is one memcpy against rebuilding the
ramp. The separate defensive copy added in `_recompute_colors_per_ca` is worth
keeping regardless: it wrote overrides in place into whatever array the colour
mode returned.

### Corrected and advanced 2026-08-12 — the chrome numbers, measured without a profiler

The entry above put `_chrome_quads` at 37.8 ms of a 41 ms frame. Those figures
came from `cProfile`, which inflates Python-heavy code badly — 33,876 `_quad`
calls a frame is exactly the shape it mis-measures. **The conclusion survived;
the numbers did not.** Timed directly, with no profiler:

| | before | after |
|---|---|---|
| `_draw` (no readback) | 26.0 ms | **17.0 ms** |
| `_chrome_quads` | 25.2 ms | 16.4 ms |
| `refresh_gui_state` | 10.6 ms | **3.1 ms** |
| `draw_frame` (offscreen) | 36.1 ms | 31.1 ms |

So the chrome really is ~97 % of the render, and the molecule really is about
1 ms — an independent measurement of 234,184 impostors on this M1 puts them at
0.94 ms, which agrees.

**Two measurement traps here, both of which cost time and both of which look
like a result:**

1. **`draw_frame` on the offscreen canvas includes a GPU-to-CPU readback** —
   about 10 ms of the 36. That is an artifact of measuring headlessly and is
   not paid by a real window. Time `_draw` for the render.
2. **Hiding the chrome to see what it costs does not work.** Setting
   `gui.visible = False` and `gui.sequence_visible = False` changed the frame
   time by nothing, which reads as "the chrome is free" and is wrong:
   `refresh_gui_state` re-asserts both flags from the viewer **every frame**.
   That is the same per-frame clobber that has bitten `info_visible`,
   `info_text` and `selecting`. Measure the function, not the flag.

**Fixed:** `refresh_gui_state` was hashing the per-residue colour array with
**blake2b, on every frame** -- 234,184 x 4 float64 is 7.5 MB, and it measured
**9.9 ms**, more than building every quad in the chrome and ten times the cost
of drawing the beads the colours describe. The cost is the algorithm, not the
size: a cryptographic hash runs near 1 GB/s where a NumPy reduction runs at
memory bandwidth. Nothing there needs collision resistance against an
adversary — it needs to notice that a colour command changed the colours. It is
now a handful of reductions (total, three strided totals, one position-weighted
total over a subsample) at **0.29 ms, a 34x saving**, verified to detect
**400/400** single- and triple-residue recolours and to detect a reordering.
The honest limit is written at the function: an array permuted so that all five
reductions are preserved would be reported unchanged. No colour command does
that.

**Still open, and now the whole of it:** the remaining 16.4 ms is building
~2,800 quads and ~330 text runs from scratch every frame. It wants a dirty-flag
cache on the chrome vertex buffer — the chrome changes on hover, focus and
state, not on camera motion, and camera motion is when frames matter. Not done
here because `internal_gui.py` and `emtk/*` are under active edit by
another agent.

### 2026-08-12 — the chimol suite's exit code lies, and four tests are stale

A full run: **3360 passed, 25 failed, 1 error, exit 134**. Every part of that
sentence needs qualifying, which is the point of this entry.

**The exit code was a teardown crash, not a test failure.** `WgpuRenderer`
captured its instance dict as a **keyword-only default**
(`def _mark_closed(*_args, _d=self.__dict__)`) on a `destroyed` slot. That works
until interpreter shutdown, when `__kwdefaults__` may already be torn down; the
slot then raises *"missing 1 required keyword-only argument: `_d`"* from inside
Qt's signal, which becomes **SIGABRT after every test has already passed**.
Fixed here by capturing in a closure cell, which cannot be stripped and keeps
the property that motivated the default — it captures the `__dict__`, not
`self`.

**A second teardown crash remains: SIGSEGV (exit 139)** when several
wgpu-using test files run in one process. It also happens after the tests
themselves have finished, and it truncates pytest's summary, so a run can look
like it ended mid-test when it did not. Not diagnosed. **Read the summary line
from the log rather than trusting the exit code**, and re-run a suspicious file
on its own.

**Two of the 25 failures were pollution, not failures.** `test_create_extract`
and `test_config_and_ss` fail in a full run and **pass in isolation** — this
suite has known global-state leakage. Always confirm a failure alone before
believing it.

**Seventeen belong to another agent's in-flight work**, not to any change:
`test_display_config_prompt` (12) — `settings_window.py` is staged as *deleted*
while still present in the tree, mid-refactor; and `test_chrome_painter` (5) —
the chrome baseline PNGs are themselves modified in the working tree.

**Four are genuinely stale tests** describing behaviour that has deliberately
changed, and each should be updated by whoever owns the change:

* `test_camera_framing::test_a_widget_that_was_never_laid_out_frames_square`
  asserts a degenerate viewport by sizing the window to the *panel column* width
  and expecting almost no scene. The object list is a **floating window now, not
  a docked column**, so `scene_width` correctly returns the full width (221, not
  &lt;16). The guard it protects is still worth testing; the way it builds the
  degenerate case is not.
* `test_demos` (2) — the demo menu comes back empty. `demo_catalog.py` is
  untracked in-flight work.
* `test_surface_splat` — expects `splat` and gets `fast`; the default in the
  untracked `surface_quality.py` changed.

### Resolved 2026-09-03 — the SQLite databases named `<sqlite3.Connection object at 0x…>`

The call site stayed unconfirmed, but the mechanism is now pinned and guarded
in mmfdb itself. `MFDatabase.__init__` forwards `db_path` to
`parse_database_target`, whose old `raw = str(location)` accepted anything — a
`Connection` passed positionally became the string
`"<sqlite3.Connection object at 0x…>"`, matched "no `://`", and was treated as
a SQLite *path*. `connect()` then created that file and `_initialize_schema()`
bootstrapped the full mmfdb schema into it — which is why the strays were
~1 MB of fresh-schema databases (77 tables, the 226-row vocabulary) rather
than empty files. The one zero-byte stray is the other shape: a bare
`sqlite3.connect(<repr>)` read, of the kind `local_admin_status` in the
mmfdb-admin GUI does — a SELECT over `sqlite_master` creates the file and
leaves it empty.

Fix (mmfdb `repository.py` + `store/sql_backend.py`): both entry points now
raise `TypeError` for a non-str/non-PathLike location, with a message that
says to pass an open connection as `connection=` instead.
`local_admin_status` validates its argument too. A regression test
(`tests/test_sql_backends.py::test_a_connection_as_path_is_rejected_and_never_creates_a_file`)
asserts the raise *and* that no file appears in the working directory. The
strays themselves, with their `-wal`/`-shm` sidecars, are deleted; the
`.gitignore` carries a `<sqlite3.Connection object at 0x*` pattern so any
regression is visible rather than silent.

Found 2026-08-12 while clearing the repository root for a full commit. Five
untracked files sit there with names like
``<sqlite3.Connection object at 0x157baf790>``, and `xxd` says each really is a
database: they begin `SQLite format 3`.

So the cause is unambiguous even though the call site is not: **something passes
a `Connection` where `sqlite3.connect()` expects a path**. `connect()` stringifies
its argument, and the repr of a Connection is a valid filename, so instead of
raising it silently creates a *new, empty* database named after the object's
memory address. Nothing fails, nothing is logged, and the real database is never
touched -- which is why five of them accumulated without anyone noticing.

The shape to look for is a helper that accepts "a path **or** a connection" and
forwards it to `connect()` on the path branch without checking which it got.
`chisurf/plugins/spectra_downloader/download/` has two functions taking a bare
`db` argument and two that call `sqlite3.connect(<arg>)` directly, which is the
most likely neighbourhood, but this was **not** confirmed -- do not treat that as
the answer.

Worth fixing rather than deleting the files: a `connect()` that quietly makes an
empty database is a data-loss shape. Any write that went to one of these went
nowhere.

**Also left in the repository root, deliberately uncommitted:** `MARK.txt` (a
DataCurve debug dump), `_smoke_nb_tmp.py`, a **zero-byte** `elements.py`,
`chisurf_project.csp`, `simulation_output_20260811_051840/`, `demo/` (2.8 MB of
`.ptu`), and about 2.8 MB of loose PNGs from surface and GUI work -- including
`200.png`, which is the artefact of the `ray 200, 150` filename bug fixed today.
None of it is source; all of it is safe to delete, and that is the user's call
rather than an agent's.

### Resolved 2026-08-12 — the chrome is cached between frames

The entry above left "the remaining 16.4 ms is building ~2,800 quads and ~330
text runs from scratch every frame" as the whole of the problem, and named the
fix: a dirty-flag cache, because the chrome changes on hover, focus and state
and **not** on camera motion, which is the only time anyone watches the frame
rate. Done.

Measured on the same M1 Pro, same 234,184-bead nuclear pore:

| | before | after |
|---|---|---|
| `_draw` | 14.97 ms | **4.50 ms** |
| `_chrome_quads` | 13.71 ms | **2.62 ms** |
| `refresh_gui_state` (inside it) | 2.40 ms | 2.50 ms |

**3.3x**, and the remaining chrome cost is almost entirely `refresh_gui_state`,
which is now the next thing worth attacking: it re-derives the per-residue
colours every frame through `get_residue_colors`, which is 2.2 ms of the 2.5.

Two smaller wins landed with it: `QuadPainter.vertices` uses `np.fromiter` with
an exact count rather than `np.asarray` (4.1 ms to 2.9 ms on a chrome frame, for
identical output), and an `array("f")` accumulator was **tried and rejected** --
it is 1.7x *slower* than a list, because per-element conversion on every
`extend` costs more than one batch conversion at the end. Worth recording so
nobody tries it twice.

**The cache's one failure mode is silent**, so it is guarded by
`test_chrome_cache.py`, which compares the cached path against a freshly emitted
build after each of twenty-two real interactions. Written first, it immediately
caught two genuine omissions from the fingerprint:

* `SequenceRow.selected` -- the strip highlights the selection, and the set is
  mutated **in place** in three separate places, so neither the row's identity
  nor the list's length notices a change;
* the **command-line feedback log** -- every command appends a line that is
  drawn as text. `select everything` moved exactly nine quads while the rows,
  the sequences and the windows were all unchanged, which is what pointed at it.

Method worth reusing: when the differential test failed, the control was to run
the same sweep with the cache *disabled*. That showed 52/54 rather than 42/54,
and the two remaining mismatches were the progress overlay, which animates and
counts seconds and so differs between any two paints. Without that control the
animation would have looked like a cache bug.

A selection larger than `InternalGui.SELECTION_HASH_MAX` (4096) deliberately
never compares equal, so the frame rebuilds -- hashing 234,184 selected residues
would cost more than the paint it saves, and rebuilding is exactly the behaviour
that was there before.

### Rejected twice — sharing the sequence gradient read-only

The next 1.3 ms after the chrome cache is a single `ndarray.copy()`:
`_build_sequence_gradient_colors` hands out a copy of its cached ramp, which on
an integrative model is 234,184 x 4 float64 -- 7.5 MB -- copied on every frame,
because the sequence strip re-reads the colours every frame.

Sharing it read-only instead has now been tried **twice**, and the second
attempt is the one worth recording. By then the one known mutator had been
fixed: `_recompute_colors_per_ca` takes an explicit writable copy before
applying per-residue overrides in place. It still failed, and not narrowly --
**50 failures in the object-menu suite alone**, plus `spectrum`, the per-atom
sort, colour-by-element and camera persistence.

The conclusion is not "add another copy at the next mutator". It is that
`_colors_per_ca` is written in place from *many* places, and the copy is not
defensive against a hypothetical caller — it is a copy the code needs. Anyone
tempted a third time: the saving is 1.3 ms, and the failure mode is a command
raising *"assignment destination is read-only"* from a call site that has done
nothing wrong.

The real fix, if this 2.5 ms is ever worth attacking, is upstream of the copy:
`refresh_gui_state` calls `get_residue_colors` on every frame purely to notice
that the colours changed, and the colours change only when a command changes
them. A change signal on the viewer would remove the call, the copy and the
signature together. That is a larger change than it sounds, because there is no
one place a colour changes -- which is exactly why the per-frame re-read exists.

### Rejected — memoising `_recompute_colors_per_ca`

The second attempt on the same 2 ms, and it failed the same way as the first.

`get_residue_colors` is called on **every frame** by the sequence strip -- that
is how a `spectrum` or a `color` reaches the strip, there being no signal to
listen to -- and it recomputes the whole per-residue colour array each time. The
obvious fix is to skip the recomputation when nothing it reads has changed, with
a key over the colour mode, the residue names, the chains, the atoms, the base
colour, the per-residue override and the per-atom projection (`_ca_rgba`, hoisted
above the key precisely so it would be covered).

Result: **152 failures in the object-menu suite**, plus spectrum, the per-atom
sort, colour-by-element and the appearance suite. Reverted; `view.py` is
byte-identical to before and all 272 object-menu tests pass again.

The lesson is now well evidenced from two directions -- the read-only attempt
and this one. **The colour pipeline is mutated in place from many places that a
key over its declared inputs does not see.** Any further attempt at this level
is likely to fail the same way.

If the 2 ms is ever worth having, the change is structural rather than another
cache: give the viewer an explicit **colour revision** bumped by the commands
that change colours, and have `refresh_gui_state` consult that instead of
re-deriving the array to notice. That is a real refactor -- there is no one
place a colour changes today, which is exactly why the per-frame re-read exists
-- and it should be done deliberately, not smuggled in behind a memo.

For scale: after the chrome cache and the frame-rate fix, `_draw` on the
234,184-bead nuclear pore is **6.7 ms** with the developer instruments on. This
2 ms is the last large CPU item, and it is guarded by a suite that catches every
attempt at it -- which is the system working.

## The whole chimol suite segfaults in one process; the files do not

**Found 2026-08-12.** `pytest chisurf/plugins/chimol/test` (3,496 tests) dies
around 16-17% with `Fatal Python error: Segmentation fault`. The dump says
**`Garbage-collecting`**, then `_mark_closed` in `hosts/qt/wgpu_view.py`, then
whatever was allocating when the collection ran -- twice in a row it was
`geometry/guide_frames.py:_flip_sweep` calling `.tolist()`, once under
`create`, once under `spectrum`, i.e. two different tests.

That is the same shape as the pyqtgraph teardown crash above and should be read
the same way: **the named caller is not the culprit.** `_mark_closed` is two
dict writes; it cannot fault. What faults is the C++ teardown that emitted
`destroyed` -- a `WgpuMolView` widget abandoned by an earlier test, collected at
an arbitrary later allocation, with a wgpu poller thread still running.

**It does not reproduce per file.** `test_demos.py` alone -- which contains the
test that was running -- is clean, so bisecting by the file named in the
traceback finds nothing. It needs a process that has already built and dropped
many viewers.

Not fixed. The fix is deterministic viewer teardown rather than leaving the
canvas to the collector; the `destroyed` connection in `wgpu_view.py` (whose
comment records two *earlier* shutdown crashes at the same seam) is where to
start. Until then, run chimol tests **per file or per directory**, which is what
the project asks for anyway on cost grounds.


### Open 2026-08-13 — chimol: `orthoscopic` is a setting nothing reads

Found while giving `reinitialize` a single push path for the display config.
`camera.orthoscopic` is a registered setting with a default, it appears in the
settings panel, `set orthoscopic, on` reports success and writes it — and
**nothing in the renderer ever reads it**. `CameraState._orthoscopic` is set
only from a restored view tuple, and no projection consults either. So the
control is fully wired at the settings end and connected to nothing at the
other.

It is deliberately **not** in `chimol/apply.py`'s `PUSHED_PATHS`: adding it
there would make a setting that does nothing look wired up, which is the
failure mode that module exists to end.

Closing it is a feature, not a fix — an orthographic projection matrix, plus
the two places that derive a distance from the field of view. Until then the
setting is honest only in that it changes nothing.

### Open 2026-08-13 — chimol: two chrome baseline PNGs are stale after the eye change

`test_chrome_painter::test_the_chrome_is_unchanged_by_the_painter_interface`
fails for the `panel` and `panel_and_sequence` states, and **only** those two —
the two that contain the object list. The object list's eye stopped being the
letter `o` and a hyphen and became a drawn pictogram, so those pixels legitimately
moved; the other three states (`command_line`, `menu_open`, `movie_transport`)
still match byte-for-byte, which is what says the change is the eye and nothing
else.

The fix is one command:

    QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.chrome_baseline

It was **not** run here because every file in
`chimol/test/renders/chrome_baseline/` is already modified and staged in the
working tree by another agent instance's in-flight work. Re-capturing would
write my change into their staged files, and a PNG cannot be split into "my
hunks" the way a source file can. Whoever owns those staged captures should
re-run it; the images will then carry both changes, which is correct.

## chimol's full test suite segfaulted (fixed 2026-08-13)

**Symptom.** `pytest chisurf/plugins/chimol/test` died with SIGSEGV around 7%
of the way in, inside an unrelated test. The file it died in passed on its own,
and the test it died on moved between runs -- the marks of a fault that is not
where it appears.

**How to read the fault report.** The give-away is two lines, not the stack:

```
Current thread ...:
  Garbage-collecting
  File ".../renderer/wgpu_view.py", line ??? in _mark_closed
  File ".../geometry/cartoon.py", line 128 in _transport_ups
```

`Garbage-collecting` directly above a chimol frame means the code below it did
not call the code above it. A collection ran at an arbitrary allocation point
-- here, ordinary cartoon geometry -- and destroyed a widget left over from an
*earlier test*, whose C++ destructor called back into Python.

**Cause.** `WgpuRenderer.__init__` connected a `_mark_closed` slot to Qt's
`destroyed` signal so rendercanvas's loop would not probe a dead wrapper. The
slot mutated the instance `__dict__`, and when the last reference is dropped by
the collector that mutation happens *mid-collection*.

**Fix.** Stop pushing the state out. `_rc_get_closed` and `_rc_close` are
overridden to ask `_cpp_alive()` -- one cheap C++ call in a `try` -- so the
question is answered when rendercanvas asks it, on its own stack. No chimol
code can run during a collection any more.

**Do not reintroduce it.** Two earlier attempts pushed the state from the same
signal (a keyword-only default holding `self.__dict__`, then a closure over
it). The first exited 134 at interpreter shutdown *after* every test passed;
the second is the segfault above. The full history is in the comment block
above `_cpp_alive` in `hosts/qt/wgpu_view.py`.


## Clicking empty space does not clear the selection (open)

`MolView.handle_mouse_click` documents PyMOL's rule -- *"left-clicking away
from any atom should deactivate the selection"* -- and says that with nothing
picked it falls through to a `set` of no indices. It does not: a selection
survives a click on an empty point **inside** the viewport.

Found while wiring picking into the browser host and **not browser-specific**;
the toolkit-free path is simply where it was first exercised, because that is
the configuration the page runs. Guarded by a strict `xfail` in
`chisurf/plugins/chimol/test/test_browser_picking.py`, so it flips to a
failure -- and starts guarding the behaviour -- the moment it is fixed.

To reproduce, take a point at least 40 px from every projected atom rather
than a coordinate off the surface: a click the viewer never considers proves
nothing about the rule, and `(-10000, -10000)` was the first thing tried.


## The screenshot helper predates the WebGPU port, and returns a blank image (open)

`test/screenshot.py` is the tool the project rule *"never implement a GUI
blind"* depends on. It cannot photograph chimol any more, and it **fails
silently**: the image is a uniform grey rectangle of the right size rather than
an error.

Cause. The helper finds the 3-D view with
`widget.findChildren(QtWidgets.QOpenGLWidget)` and captures it with
`gl.grabFramebuffer()`. chimol's renderer is `WgpuRenderer` -- a plain
`QWidget` presenting a WebGPU surface -- so there is no `QOpenGLWidget` to
find. Its whole docstring argues about the offscreen platform plugin and GL
contexts, which is the *previous* renderer's problem.

Both routes are dead, and neither says so:

* `QT_QPA_PLATFORM=offscreen` + `win.grab()` -> uniform grey. A presented
  WebGPU surface is not in the widget's backing store.
* the documented route (real window server, `WA_DontShowOnScreen`,
  `shoot(win, ..., area="window")`) -> also uniform grey, because the
  `QOpenGLWidget` search finds nothing and the fallback is the same
  `widget.grab()`.

Consequence. Any chimol GUI change "verified by screenshot" since the WebGPU
port was verified against a blank image. The rule has been unenforceable for
this plugin and nothing reported it.

What a fix needs. The renderer already composites its chrome into the frame
(`host/qt_overlay.paint_chrome_into`) and `WgpuMeshRenderer` can render
offscreen -- `test/chrome_baseline.py` and the visual-rendering tests both get
real pixels that way. So the capture should go through the *renderer*, not
through Qt: draw a frame into a texture, read it back, and composite the
chrome, which is also the only route that works for the browser host. Until
then `screenshot.py` should raise rather than return grey.


## Browser clicks land in the wrong place -- two boxes, not one (open)

Picking now runs in the page, and it misses. Not a constant shift: the error
grows toward the bottom and the right, because the projection and the render
use **differently sized rectangles**.

The renderer draws with (`hosts/web/page.py`):

    viewport=(0.0, 0.0, self.scene_width() * dpr, self.scene_height() * dpr)

where `Viewer.scene_width/height` *do* subtract the panel column and the
sequence strip. So the molecule is drawn into a shorter, narrower box -- but
anchored at **y = 0**, where the desktop anchors it under the strip
(`CanvasRenderer._scene_viewport` returns `(0, strip, ...)`).

The projection runs on `SceneSink`, which inherits `CameraState.scene_width()`
and `scene_height()`. Those return the **full** surface -- their docstrings say
so outright: *"No panel is reserved"*, *"No strip is reserved"* -- so
`scene_origin_y()` is 0 and the aspect used for the projection matrix is the
whole canvas rather than the scene box.

So: drawn in one rectangle, projected in another. `scene_origin_y()`'s own
docstring is the statement of the invariant being broken -- *"both the
projection and the render viewport need it and they must not disagree by a
pixel: they are what decides whether a click lands on the atom under the
cursor."*

**Same root cause as the five missing host features.** `SceneSink` is a sibling
of `CanvasRenderer`, not a child, so it has no `_internal_gui` and cannot know
what the chrome reserves; `Viewer` therefore hand-rolls the scene metrics and
the two halves drift. Re-basing `SceneSink` fixes the offset and the missing
features together -- see the relocation concept.

**Why the test suite did not catch it.** `test_browser_picking.py` projects an
atom and clicks at the projected coordinate. That is self-consistent under any
projection, correct or not: it proves the pick *path* is wired, never that the
projection agrees with what was drawn. A real check has to render a frame and
find the molecule's pixels, then click those -- the same "measure it, do not
re-derive it" rule the trajectory test now follows.

## test_prd_mentions and test_plugin_help_guide_seam are red at HEAD for unrelated plugins (open) — both resolved 2026-09-03

**Found 2026-08-14, during the chimol relocation** (which is *not* the
cause — verified against HEAD before touching anything).

Two guardrail suites fail on plugins whose modernisation is in flight
elsewhere:

* ✅ **RESOLVED 2026-09-03** `test_prd_mentions.py`: every current offender was
  cleaned rather than allow-listed — the `fret/core` forwarders' and
  `model_manager`'s "(PRD-97)"/"(PRD-38)" parentheticals dropped, the
  `flc_2d` parity test and `lumis_quest` CREDITS.md reworded, the historical
  "(PRD-109/122/130/133)" asides in
  `core/{fluorescence/burst,math/{linalg,optimization},structure/av,
  fluorescence/tcspc/irf_estimation}` and `gui/chiplot/backends` rewritten to
  say what happened without the number. The allow-list's genuinely stale lines
  (`core/fio/trajectory/{__init__,xtc}.py` — the latter file no longer exists)
  were struck. Both guards green.
* ✅ **RESOLVED 2026-09-03** `test_plugin_help_guide_seam.py`: the six plugins
  now ship their `help.md`/`guide.json` — see the plugin-manager-rebuild entry
  below.

`mfd_prepare` was mid-restructure (its files were staged for deletion in the
shared index), which is why the PRD fix did not land with the relocation; the
restructure finished **2026-08-15** and its PRD mentions and the broken
`ServiceDispatcher.method` registration were fixed together (commit
`e7f9a3835`). What this entry called "free wins" are now taken.

## ✅ FIXED — lumis_quest: `test_a_hitched_frame_does_not_throw_anybody_through_a_wall` fails on the working tree

**Found 2026-08-14 (T-20260814-05). Fixed by 2026-08-23** — the npcs edit the
entry blamed landed, and the full lumis + games suite runs green (434 passed,
3 skipped) with the hitch-step test among them. Kept as a FIXED stub so a
reader can tell a healed failure from one nobody filed.

**Original text.** Deterministic failure (3/3 runs) in
`chisurf/plugins/misc/games/lumis_quest/test/test_npcs.py`. The cause is an
**uncommitted in-flight edit to `api/npcs.py`** (working-tree diff of
-125/+59 lines against HEAD by a peer session, still evolving at time of
writing) — the test is pure `api.npcs` physics and imports no GUI module, so
the T-20260814-05 presentation work cannot be implicated. Not fixed by the
finder because the file is actively owned mid-edit: reverting or patching it
would discard the peer's work. Whoever lands the npcs change owns the test;
if it is still red after their landing, the hitch-step resolution in
`npcs.update` lets a beast end a 0.75 s step inside a solid (observed at
(710.0, 376.0), a `beast` inside a wall of the test world).

## test_keyboard_layout's browser-host case fails on T-20260814-01's in-flight rewire (open)

**Found 2026-08-14, during the relocation's full-suite run.** The test builds
`object.__new__(Viewer)` and stubs `viewer.gui`; the half-finished
`hosts/web/page.py` on disk routes `key()` through `self.sink.on_key_press`
instead. Fails identically on the pre-move disk state — carried verbatim to
`~/dev/chimol` — so it is that ticket's to finish, not relocation fallout.
Full-suite tally after the relocation: 3625 passed, 41 skipped, and this one
failure.

## Six plugin-suite failures that predate the dependency work (open) — 4 of 6 fixed 2026-09-03

**Found 2026-08-20, during the plugin-dependency change's `pytest test/plugins`
run.** All six reproduce on HEAD content and are unrelated to manifests,
discovery or load order; verified by checking the relevant files with
`git show HEAD:<path>` rather than by assuming.

State after the 2026-09-03 sweep (arm64 env, `QT_QPA_PLATFORM=offscreen`):

- ✅ **FIXED** `burst/test_mmfdb_h2mm_simulation.py::test_model_selection_scan_is_exposed`
  — the scan is a `tttrlib.DataStore` now, not a frame: `.columns` is the list
  of `Column` objects and `Column == str` raises the truth-value ambiguity the
  test showed. The test's spelling moved to `.names`
  (`list(h2mm.scan.names) == [...]`); the store's column order is first-seen,
  which is the order `store_from_rows` builds, so the assertion holds. Whole
  file: 5 passed.
- ✅ **FIXED, and it was hiding a real defect**
  `burst_selection/test_export_guards.py::test_export_bur_writes_non_empty_frame`
  — the test fed a `pandas.DataFrame` where production holds a `DataStore`, and
  `write_csv_table` no longer converts frames, so the export silently reported
  "Export failed". **Behind it, both exporters (`export_bur`,
  `export_flr_cif`) guarded on `self._last_frame.empty` — a pandas attribute
  the DataStore does not have — so in production, with a real table, the
  guard itself raised `AttributeError` and neither export could run at all.**
  The guards now test `n_rows() == 0`; the test builds its table through
  `store_from_rows`, the way the pipeline does. 6 passed.
- ✅ **FIXED** `test_plugin_entrypoints_import[fps_json_editor]` and `[fret]`'s
  root cause is unchanged — `IMP.bff.fret` does not exist — **but the
  environment question is now answered**: the forwarders
  (`plugins/modelling/fret/core/*.py`) name a Python subpackage that exists
  only in `/Users/tpeulen/dev/imp.bff/cmake-build-debug`, and that build
  cannot even initialise under the arm64 env (its `IMP/__init__.py`
  path arithmetic fails before any import). The env's installed build
  (`/Users/tpeulen/dev/imp/cmake-build-arm64`) has the flat C++ surface —
  `fret_efficiency`, `FretSpectrum`, `histogram_rada`, … — and no `fret`
  subpackage. So this is the PRD-97 stream's decision, on the record now:
  either install the `IMP.bff.fret` Python portion into the active imp build,
  or de-forward `fret/core` onto the flat surface. **Still open.**
- **Still open on purpose** `test_plugin_demo_gating.py::test_every_game_declares_itself_a_demo`
  and `::test_opting_in_brings_the_demo_hub_back` — the three game manifests
  still carry `"demo": false` and `chisurf/gui/chigame/` is still modified in
  the shared tree (re-verified 2026-09-03). It belongs to whoever owns the
  chigame work; flipping the flag hides the Games entry from the default menu.

Tally at the end of the original change: 6 failed, 319 passed, 1 skipped (down
from 18 failed, since 12 of the original failures *were* caused by the change
or by manifest-scanning tests that mistook chimol render baselines for plugin
manifests, and were fixed).

## Pre-existing failures found during the plugin-manager rebuild (open) — both fixed 2026-09-03

**Found 2026-08-20.** None were caused by that change; each was checked against
the working tree's own state before the rewrite began.

- ✅ **FIXED 2026-09-03**
  `test/test_ui_schemas.py::test_the_written_schemas_match_the_generator` —
  the schema work flagged as uncommitted in August has long since landed; the
  written schemas under `chisurf/core/dataspec/schemas/` had simply drifted
  from the generator again. Regenerated with
  `python -m chisurf.core.dataspec.schema` (`guide.schema.json` +16 lines,
  `view.schema.json` +243). The whole file: 325 passed.
- ✅ **FIXED 2026-09-03**
  `test/test_plugin_help_guide_seam.py::test_every_gui_plugin_has_help_and_guide`
  — the six unlisted GUI plugins (`mfd_prepare`, `plot_settings`,
  `tttr_to_pto`, `filetools`, `lumis_quest`, `ninja_adventure`) now ship
  `help.md` and `guide.json` beside their GUI modules, written against what
  each tool actually does; no code change was involved, exactly as the seam
  promised. Whole file: 121 passed, 20 skipped. The allow-list was not
  touched.

## ✅ FIXED — chiplot's WGPU backend: middle-drag opens a selection rectangle instead of panning

**Found 2026-08-20** (user report). In the `wgpu` native chiplot backend
(`chisurf/gui/chiplot/backends/wgpu/_canvas.py`), a middle-button drag does not
pan the view the way it does in pyqtgraph — instead it opens a rubber-band
selection rectangle, whenever the "left button pans" preference
(`gui.plot.pyqtgraph_config.leftButtonPan`) is off, i.e. the panel is in
left-drag-zooms mode.

The docstring on `_mouse_press` already states the intended pyqtgraph
semantics: "Only the *left* button grabs a region, a marker or the corner
button — pyqtgraph's items ignore the middle one, so a middle drag pans across
a fit range instead of moving it." `_is_view_drag_button` correctly admits both
`QtCore.Qt.LeftButton` and `QtCore.Qt.MiddleButton` into the drag path
(`_canvas.py:856-864`). But the branch that decides pan-vs-rubber-band
(`_canvas.py:920-927`) only inspects `self._left_button_pans()` — it never
checks *which* button is down:

```python
if self._left_button_pans():
    self._panning = True
    ...
else:
    self._rubber = (px, py, px, py)
```

So with `leftButtonPan=False`, a middle-button press falls into the `else`
branch and starts a rubber-band drag exactly like a left click would, even
though the middle button is supposed to always pan regardless of that
preference. With `leftButtonPan=True` (the default) the bug is invisible,
because both buttons pan anyway — that is likely why it was not caught by the
existing tests.

**Fixed 2026-08-20**: the pan branch now also fires on a middle-button press
regardless of the preference (`_canvas.py:923`,
`if event.button() == QtCore.Qt.MiddleButton or self._left_button_pans():`).
Covered by
`test/gui/test_chiplot_wgpu.py::test_a_middle_drag_still_pans_when_left_draws_a_zoom_rectangle`,
which sets `leftButtonPan=False` via `set_left_button_pans(False)` and asserts
a middle drag still pans (`_panning is True`, `_rubber is None`, range
changes). Full file: 57 passed.

The legacy `opengl` backend (`chisurf/gui/chiplot/backends/opengl/_canvas.py`)
has no equivalent pan/rubber-band logic at all, so this is specific to the
WGPU backend, which is the one under active migration
([chiplot](../subsystems/chiplot.md)).


# chimol: three things a documentation grab walked into (2026-08-31)

Found while making `docs/guides/make_screenshots.py` regenerate the figures for
[the molecular-viewer guide](../../docs/guides/44_molecular_viewer.md). Two of
the three are chimol's, filed here because chimol is a companion checkout with
another instance active in it; none is fixed.

## The Objects dock is retired, and the overlay that replaced it lists nothing

`chimol/hosts/qt/window.py` states it plainly — *"Objects is permanently hidden
(the list is in the viewport)"* — so `window.objects` no longer exists and the
old grab raised `AttributeError`. That part is intended.

What is **not** intended: the viewport Object List draws only `all` and `sele`.
With three real objects loaded it still shows those two rows, before and after
`refresh_objects()`:

```python
win = MolViewPluginWindow(); win.load_structure_from_path(pdb)
Cmd(win).do("create ligand, resn NAG")
list(win.viewer.objects)      # ['obj2', 'obj3', 'obj4']
win.refresh_objects()         # overlay still shows only `all` and `sele`
```

So the panel that replaced the dock does not yet do the dock's job. Consequence
for the docs: `chimol_objects_panel.png` and `chimol_groups_panel.png` in guide
44 show the **retired** Qt dock. They were deliberately *not* regenerated from
the overlay — that would swap two figures that show the old UI correctly for two
that show the new UI wrongly. The guide's prose around them (rows carrying
PyMOL's five **A S H L C** menus) still describes what the overlay draws, so it
is not misleading, only dated.

## The ray tracer draws a mesh contour as streaks

`isomesh` renders as a clean wireframe cage through the WebGPU path and as long
crossing bars through `ray`. Same scene, same commands:

```
molmap all, 6
isomesh m, molmap_6     # NO level -- see below
orient all
zoom all
ray out.png, 900, 650
```

This blocks regenerating `chimol_molmap.png` and `chimol_map_isomesh.png`, which
are chrome-free ray renders; the existing files are correct and were left alone.

**Worth knowing whichever path you use:** give `isomesh` **no level**. A map
opens already contoured, and a level argument *appends* a second contour rather
than restyling the first — the solid surface the map opened with then hides the
mesh, and the figure looks like `isomesh` silently did nothing.

## `orient` with no target resolves nothing on a bare viewer

`Viewer.add_structure(..., name="148l")` does not take the name; the object is
auto-named (`obj2`). A bare `orient` / `zoom` then fails with *"orient: nothing
to orient"* and leaves the camera wherever it was — which reads as a badly
framed render rather than as an error, because the message goes to the error
callback a script usually discards. Name `all` explicitly.

# ~~H2MM's fallback engine is correct but 300x slower than the reference~~ — RESOLVED (2026-08-31)

Found immediately after fixing the `NameError` that stopped `_estep` running at
all (see `okf/log.md`, same date). With the fix, `test_ab_vs_h2mm_c.py` gets
*past* the correctness assertion —

```
assert mine.loglik == pytest.approx(ref.loglik, rel=1e-4, abs=1.0)   # passes
```

— and fails the one after it:

```
numba H2MM 307.55x the H2MM_C time/iter - performance regression
assert 307.54749331660156 < 1.5
```

**This is not a regression from that fix.** It is what retiring numba left
behind: `core/h2mm.py` is now interpreted Python running an `O(N·n²)` loop
photon by photon, and the guard was written when a JIT stood behind it. Before
the fix the same test failed earlier and louder, with a `NameError`.

**It does not affect normal use.** `core/engines.py` prefers the tttrlib C++
backend (`_use_tttrlib()`) and only falls back to this module, so the GUI, the
wizard and the export all take the compiled path. The slow path is what you get
when tttrlib is missing, when a caller reaches into `h2mm.fit_states` directly
(which is what the benchmark does), or when the tttrlib call raises and the
fallback catches it — and that last one is silent apart from a log line.

Two things are therefore stale rather than broken, and neither is fixed:

* the guard asserts a `< 1.5x` ratio that the architecture no longer promises
  for this module. Either it should compare the *tttrlib* path against the
  reference — which is the path users get — or it should be marked as measuring
  the fallback and given a realistic bound;
* the fallback is still called "the numba engine" in `engines.py`
  (`backend()` returns the string `'numba'`, and the fallback warning names it),
  which will mislead the next reader: there is no numba left in it.

**Resolved the same day, by deleting the fallback** (`T-20260831-02`). Neither
follow-up was needed in the end:

* the perf guard now benchmarks the engine users actually get, and **passes** —
  1.04× the reference on the 2-state case and **0.48×** on the 3-state one, so
  ChiSurf is *faster* than `H2MM_C` there. Both parametrisations had been red;
  they are green.
* nothing is called "the numba engine" any more because there is no second
  engine. `active_backend()` returns `'tttrlib'` or raises.

`core/h2mm.py` went 1210 → 376 lines, keeping only the data types
(`H2mmModel`, `BurstPhotons`, `prepare_bursts`, `factory_model`,
`simulate_bursts`). The whole H2MM + burst_gs suite went from 535 s to 138 s,
which is the same slow EM leaving the tests.

# Further tttrlib delegation — the five candidates, settled (2026-08-31)

The table below was published earlier the same day as **candidates, not
findings**: five unused tttrlib entry points sitting next to an in-tree module
that *might* implement the same thing. All five have now been settled by
importing and A/B-ing on real data. Three were false candidates — the symbol
name matched a subsystem and computed something else — which is exactly the
failure mode the original note warned about.

| tttrlib symbol | what it actually computes | verdict |
|---|---|---|
| `BurstML`, `BurstMLFitResult` | FRET_burstML (Hoffmann *et al.*): a **joint diffusion + kinetics + photon-counting** likelihood over burst photon sequences, 5·n parameters (`n0`, `tau_diff`, `k`, `f`, `E`, `bkg`), radial coordinate discretised and eigendecomposed per parameter set. | **false candidate.** `core/fluorescence/mle/` is a typed facade over `fit2x` (`DecayFit2`/`DecayFitProblem`) and carries no algorithm of its own; the nearest in-tree relative of `BurstML` is `burst/gopich_szabo.py`, which has no diffusion term. Nothing to delete — this is a *missing feature*, not a duplicate. |
| `BurstFeatureExtractor`, `BurstFeature` | Per burst `[start, stop, size, duration (s), rate (Hz)]`, per-channel photon counts, and uncorrected `E = A/(D+A)`. | **false candidate, but verified numerically.** On 293 bursts of `BH_SPC132.spc` it reproduces ChiSurf's `.bur` arithmetic exactly (size max\|Δ\| = 0, duration 1.8e-15 ms after the s→ms conversion). It is a strict *subset* — no per-detector first/last photon, no per-detector duration or mean macro/micro time, no per-window count rates, no corrected E/S (γ/α/β/δ) — and it only reads a `tttrlib.BurstFilter`, which ChiSurf never has: its boundaries come from eight searches, several of them in-tree (BOCPD, CUSUM, Kalman). Delegating five of ~40 columns would add a conversion path without removing an algorithm. |
| `DecayPhasor`, `StreamingPhasor` | Sine/cosine moments of a decay, normalised by its integral, with IRF calibration. | **duplicate — deleted.** The imaging phasor already delegated (`CLSMImage.get_phasor`) and `StreamingPhasor` was already live in the acquisition pipeline; the duplicate was the unreachable `core/fluorescence/tcspc/phasor.py`. See [FLIM and the phasor approach](imaging-flim-phasor-theory.md) for the measurement. |
| `maxent_invert` | Skilling–Bryan MEM: minimise `‖Ax − b‖² − ν²·S(x)` by an active-set bound-constrained QP inside a Newton outer iteration. | **duplicate — deleted.** `core/math/optimization/mem.py::maxent` had the same signature, no callers, and the **wrong sign** on the entropy gradient: it returned `chi2` as the objective but `grad_chi2 − ν²(1 + ln x)`, which minimises entropy instead of maximising it. On a 3-peak/30-node inversion its objective is worse at every ν, and at ν = 30 it drives S to 5.5e-6 (every component on the 1e-8 floor) where the compiled solve holds S = −87. tttrlib's own registry entry had already recorded `mem.py` as "not equivalent … which is why that was rejected as a reference". |
| `OptsCluster`, `ResultsCluster` | **Single-molecule localisation**: 2-D Gaussian PSF fitting (`fit2DGauss`, `maxNPeaks`, `elliptical_circular`), whose results carry `peak_x/y`, `sigma_x/y`, `background`, `chi2`, `imageID`, `pixelID`. | **false candidate**, as the earlier tracker already suspected. Nothing to do with `core/ml/cluster/`. |

Also settled while surveying, and *not* from the table:
`plugins/core/acq/tcspc_devices/simulation/core/algorithms.py` picked the
excitation focus with `elif <name> and hasattr(tttrlib.SimGrid, <ctor>)` ending
in `else: # gaussian3d (default / fallback)`, so a library missing
`gaussian_lorentzian` or `numeric_from_file` silently simulated a different
optical model. It now raises. And `core/ml/cluster/_hdbscan.py`
carried an in-tree `O(n²·d)` brute-force core distance and an `O(n²)` Prim MST
behind a `hasattr` probe on `tttrlib.mutual_reachability_mst`. They agreed
**bit for bit** (max\|Δ\| = 0 in core distance, in every MST edge weight and in the
edge set) on 500 and 2000 real photons from `BH_SPC132.spc` at `min_samples`
3/5/10, and were 700–3000× slower. Deleted; a missing kernel now raises.

Already delegating, listed so nobody re-checks: `DecayFitNExp` (tcspc models),
`StreamingCorrelator` (fcs), `GopichSzabo`, `HMM`, `TwoCDE`, `BVA`,
`tcspc_run_mem`, `HmmSurrogate`, `sim_occupation_fractions`, `SimEngine`,
`richardson_lucy_2d`, `PdaBurstLikelihood`.

**What is left from this survey.** Nothing to delete. One genuine *gap*:
`BurstML` implements a method ChiSurf does not have at all — freely-diffusing
burst analysis where diffusion through the focus, conformational kinetics and
photon counting are fitted jointly, without binning. `burst_gs` fits kinetics on
photon sequences but assumes the burst is the observation window and carries no
diffusion term, so the two are complementary rather than competing. The entry
point is `tttrlib.BurstML` (`set_burst_data(times_ms, colours, offsets)`, then
`fit(init, lower, upper, n_states, n_colours, jmax, qmax, t_th, n_th)`);
`examples/single_molecule/plot_burstml_two_state.py` upstream documents the
5·n parameter layout and simulates data the likelihood's own forward model
generated, which is the fixture a plugin would be built against.

**The method that worked**, and the traps it caught, are worth reusing:

- Run the A/B on a **real** file, not synthetic data (synthetic photons put 2CDE
  into its sentinel branch and proved nothing).
- Call it **the way callers call it** (passing `[]` for BVA's micro-time ranges
  made a correct path look like it returned only zeros).
- **Match the unit and index conventions before concluding anything.**
  `DecayPhasor` takes frequency in *cycles per micro-time channel*, not per
  nanosecond; passing the physical frequency makes it return `(≈0, ≈0)` and look
  like a different quantity entirely. `BurstFeatureExtractor` reports duration in
  seconds and rate in Hz where the `.bur` contract is ms and kHz. Both looked
  like disagreements at first and were unit mismatches.
- Report `max|Δ|`, never "they agree" — and when they differ, settle it against
  an **independent third** calculation rather than against either side. The
  MaxEnt verdict came from SciPy L-BFGS-B on the documented objective; the
  phasor verdict from writing the definition out as a weighted sum; the MST
  verdict from SciPy's `minimum_spanning_tree` over an explicit
  mutual-reachability matrix.

## `.native` calls outlive the backend they were written against

**2026-09-02.** `lightpath_simulator/gui/node_types.py` reached past chiplot
with `plot_w.native.hideAxis('left')` and three more, under a comment saying
chiplot had no verb for it. chiplot has had `set_axis_visible` for a while, so
the comment outlived the gap it described -- and when chiplot's native backend
stopped being pyqtgraph, `hideAxis` became an `AttributeError` that took the
whole node factory down with it and left the beam-path simulator unable to
build its default path.

Fixed there. The general shape is the risk: **a `.native` call is a bet on
which backend chiplot happens to have**, and it is invisible to the import
guard because it reaches pyqtgraph without importing it.
`test/chiplot_native_allowlist.txt` is the list of remaining bets.

## RESOLVED 2026-09-03 — `IMP.bff.av` no longer exists — three test/models failures (2026-09-02)

`chisurf/core/structure/av/__init__.py` imported
`IMP.bff.av.compute.compute_av`, but the installed imp build (the arm64 env's
`/Users/tpeulen/dev/imp/cmake-build-arm64`) carries no `IMP.bff.av` Python
subpackage — the PRD-117-style move put the builder on the flat `IMP.bff` C++
surface. Failed: `test/models/test_fret_structure.py` (both tests),
`test/fluorescence/test_structure.py::test_labeled_structure`, and
`test/models/test_detector_setups.py::test_a_missing_setups_file_never_blocks_a_headless_run`
(the last two only through shared import/state).

**Fixed 2026-09-03** by pointing the wrapper at the new surface — verified by
introspection and by running the AV parity set, not by renaming:

* `_compute_av()` → `IMP.bff.compute_av`, which takes **one (N, 4) xyz+radius
  array** and `r1/r2/r3` separately (no `dye_radii=`, no `backend=`), and
  returns an `AccessibleVolume` read through `get_ng()/get_density()/
  attachment_point`.
* The other lazy imports moved to module-level functions that exist now:
  `density_to_points` (returns one `(n, 4)` array, not `(n, points)`),
  `random_distances`, `av_pair_statistics` (deterministic across calls;
  takes the point clouds directly), `mean_position_distance`,
  `histogram_rda` (takes **point arrays**, no longer the duck-typed AV —
  real `States` or nothing), `split_contact_volume_masks` (returns
  `[contact_mask, free_mask]`, wants 2-D radius/centre arrays),
  and `IMP.bff.DynamicAccessibleVolume` (built from the real upstream AV plus
  an `ObstacleAtoms`; `dye_radius` renamed `probe_radius`).
* **The site strip is the load-bearing part.** With the FRETStructure model
  defaults (`linker_width=4.5`, `radius1=4`, grid 0.5) the raw-array door
  returned **zero** points for the hGBP1 18/577 sites while upstream's own
  PDB door returned 106k for the same parameters — because the PDB door
  strips the attachment residue to backbone + attachment atom
  (`default_strip_mask`), which is what keeps the source from obstructing
  itself. The wrapper now applies the same keep-set before calling.
* `allowed_sphere_radius=None` now passes the **derive sentinel** (`-1.0`)
  instead of the flat settings value 2.0. Upstream derives
  `max(1.5, linker_width/2 + grid/2)`; the search inflates obstacles by half
  the linker width, so a flat 2.0 at `linker_width=4.5` walls the source in —
  exactly the fps.json-door bug upstream's `AV.h` documents as fixed by the
  same derivation. The yaml key `fps.allowed_sphere_radius` is no longer read
  by the wrapper.

With `QT_QPA_PLATFORM=offscreen`, `test/fluorescence/test_structure.py`
(7), `test/models/test_fret_structure.py` (3) and
`test/models/test_detector_setups.py` (5) all pass. The Qt-offscreen
platform is required for the last two — bare `QApplication([])` aborts the
interpreter headless, which had masked these tests' progress earlier.

**`DynamicAV` was rewired end-to-end the same day** (it shared the dead
import): the upstream class renames every field to a getter
(`get_diffusion_map`, `get_quenching_rate_map`, `get_fret_rate_map`,
`get_rate_map`, `get_occupancy`), needs `update_diffusion_map()` before
`update_occupancy()` will run, and `donor_decay` takes `(t_max, t_step,
n_out)` positionally returning a `GridDiffusionResult` read through
`get_time/get_fluorescence/get_density`. The PET quenching table is now
`PETParametersMap`: ChiSurf's `structure.json` `Quencher` block
(`{RES: {ATOM: [rate (1/ns), contact_distance (Å)]}}` — the residue-varying
number is the rate, the shared 2.9 Å the contact radius) maps onto
`PETParameters(comp_id, rate_constant, contact_distance)`. Exercised
end-to-end on hGBP1 site 18 (quenching field max 5.55/ns, occupancy
normalised, decay integrated to f(∞)=0.067). One honest gap: upstream's
`n_out` sampling semantics returned fewer samples than requested in the
smoke test, and the AV-decay model (`av_decay.py`) has no test coverage of
its own — nothing pins the output length the fit sees.

The fret-plugin forwarders still naming `IMP.bff.fret.*` are a *separate*
gap and remain open — see the plugin-suite entry below.

## Bounded LM stalls when the bounds span decades (2026-09-02) — FIXED

Fixed via [PRD-120](../prds/prd-120.md) (2026-09-02): `IMP.bff.Minimizer::fdjac2_step`
takes the smaller in magnitude of an internal-relative and an
externally-relative forward-difference step for two-sided bounds, so a
decade-spanning box no longer collapses the LM step. ICS 2D-Gaussian
chi2r 608 → 1.03 bounded, matching unbounded. `test_graph_fit_ics.py`'s
bounds-off workaround is gone.

## ✅ FIXED — `pch_mixture` indexes `avg_numbers` by the length of `brightnesses`, and reads past the end (2026-09-02)

Filed against tttrlib by `chisurf/core/models/pch/pch.py`'s `pch_mixture`
wrapper, which raised a defensive `ValueError` in front of the delegation and
documented the bug in its own docstring ("filed upstream ... this raises
until it is fixed there"). Confirmed **fixed in tttrlib**, `okf/BUGS.md`
("`pch_mixture` indexes `avg_numbers` by the length of `brightnesses`, and
reads past the end", fixed 2026-08-10): a mismatched `(brightnesses,
avg_numbers)` pair used to be read with no bounds check — not a crash, a
*silent* one, because the `avg_numbers[s] <= 0.0` guard on the very next line
then skipped the species whose occupancy read past the end into zeroed
memory, and the result was a normalised, finite histogram of *fewer species
than were asked for*. `pch_mixture` now throws `std::invalid_argument` naming
both sizes, surfaced to Python as `ValueError`.

**Verified present in the environment chisurf actually runs in**, not just
in the tttrlib checkout: the `arm64` conda env's installed
`tttrlib.pch_mixture` raises `ValueError: pch_mixture: brightnesses (3) and
avg_numbers (1) must have one entry per species` for a mismatched pair,
2026-09-02. The chisurf wrapper's own length check is kept regardless, as
defense in depth (one call earlier, a message this module controls, and no
dependency on which tttrlib build happens to be linked) — its docstring now
says so instead of "filed, awaiting a fix". `FidaModel` does not go through
`pch_mixture` (it uses the pure-Python `fida.fida_pch` generating-function
path) and was not affected by this defect; its own axis problem is the
separate refusal documented under PRD-121 in `okf/prds/prd-121.md`.

## `AnisotropySpectrum` applies the G-factor before the mixing (2026-09-02)

Found porting the MFD patterns onto the graph's producer nodes (PRD-128).
The engine node's polarised mixing applies ``G`` in a different slot than
the Schaffer form the MFD side derives from: at ``G = 1`` the two spellings
are algebraically identical for every ``l1``/``l2``, away from it they are
not (at ``G = 2``, ``l1 = l2 = 0.1`` the recovered anisotropy differs by a
factor of two). `chisurf/core/fluorescence/mfd/patterns.py`
(`_polarized_spectrum`) works around it by driving the node at ``g = 1``
and applying ``G`` afterwards as a perpendicular-channel gain — one
multiplication, not a second copy of the algebra. **Not corrected in the
node** because `AnisotropySpectrum` must stay bit-identical to
`chisurf.core.fluorescence.anisotropy.decay.calculcate_spectrum`, which the
fitted TCSPC models are pinned against; fixing the ordering is an
engine-side change that must move both together, with the VV/VH parity
tests re-based in the same commit.

## No `AcceptorSpectrum` producer node — the sensitized-acceptor transform is a second implementation (2026-09-02)

`mfd/patterns.py::acceptor_lifetime_spectrum` computes the sensitized
acceptor's rise/decay spectrum in numpy because nothing in `IMP.bff` emits
it — the decay graph's producers cover the donor (`FretSpectrum`) and the
polarisation (`AnisotropySpectrum`); no fitted TCSPC model has needed the
acceptor rise yet. The transform belongs *in* the engine (an
`AcceptorSpectrum` node taking the quenched donor spectrum plus ``tau_a``
and ``tau0``); until that node exists the numpy transform stays, stated
loudly in its docstring rather than hidden behind a fallback. This is the
one recorded exception to PRD-128's "patterns.py computes no spectrum
algebra of its own".

## RESOLVED 2026-09-03 — `test_change_dihedral` red: the test relied on two accidents, not on the dihedral machinery

`test/fluorescence/test_structure.py::Tests::test_change_dihedral` expected
zeroing ``omega`` and calling ``update()`` to move the first atoms;
coordinates came back unchanged. **Both halves of the premise were wrong, and
neither had anything to do with the dihedral machinery:**

1. **``s1.omega *= 0.0`` never wrote anything.** The ``omega`` getter returns
   ``internal_coordinates[self._omega_indices]['d']`` — fancy indexing, hence a
   **copy** — so the in-place multiply modified a temporary. True since the
   property was introduced (2019); the *setter* writes through, the augmented
   assignment does not.
2. **The first atoms cannot move under ``omega`` at all.** The omega rows sit
   at the CA atoms; residue 1's row carries dummy anchors ``(0, 0, 0)``, and
   the first *effective* omega is the CA of residue 2 — atom 7. Atoms 0–6
   (N, CA, C, O, CB, … of MET 7) are built before any omega and are unmoved by
   a real omega write (verified: zeroing every omega moves 3449/3456 atoms, max
   Δ 170 Å, first mover exactly atom 7).

The test had been green because the old internal→cartesian reconstruction was
lossy enough to jiggle the first atoms on every ``update()``; the numba-removal
stack made the round-trip exact (Δ ≈ 2e-15), which turned the dormant no-op
into a red assertion. Fails identically on a clean worktree at HEAD, so it was
never working-tree fallout.

**Fixed the test** (2026-09-03): set ``s1.omega = np.zeros_like(s1.omega)``
through the property, then assert atoms `[:7]` stay and atoms `[7:]` move.
Not from the 2026-09-02/03 PRD wave; the internal-coordinate code was never
wrong. Sibling `test_labeled_structure` was the already-recorded
`IMP.bff.av` import baseline — also fixed, see above its entry.

## The `common.py` move left two stale `cs.core.common`/import sites — 24 pda2c tests red, one PDB parse path dead (found & fixed 2026-09-03)

The working tree's `chisurf/core/common.py` → `chisurf/core/support/common.py`
relocation (part of the large uncommitted refactor) did not move all of its
callers with it. Three separate symptoms, one cause:

* `chisurf/core/models/pda2c/simple.py` imported `Pda2cModelMixin`,
  `mask_zero_photon_bins`, `pda_1d_residuals_from_s1s2` and
  `resolve_fit_settings` from `chisurf.core.support.common` — the *relocated
  general helpers* module — when they live in
  `chisurf/core/models/pda2c/common.py`, the *pda2c* module of the same
  basename. Every import of `simple.py` raised, which took down
  **24 tests** across `test_pda2c_diagnostics.py` (12),
  `test_pda2c_statistics.py` (9) and `test_pda2c_saw_nu.py` (3) with one
  `ImportError`. **Fixed**: the import now names `chisurf.core.models.pda2c.common`.
  All 47 pda2c tests pass.
* `chisurf/core/fio/structure/coordinates.py` still spelled the old namespace
  eight times (`cs.core.common.atom_weights`, `CHARGE_DICT`,
  `TITR_ATOM_COARSE`, `VDW_DICT`) — even though it *already imported*
  `chisurf.core.support.common`. Killed `parse_string_pdb`'s mass/radius
  assignment and the PQR writer. **Fixed** to the `chisurf.core.support.common`
  spelling; found because `test_structure_Structure` failed with
  `module 'chisurf.core' has no attribute 'common'`.
* `chisurf/core/structure/av/__init__.py:564` had the same stale
  `cs.core.common.quencher` reference. **Fixed** the same way.

The trap worth keeping: `support/common.py` and `models/pda2c/common.py` share
a basename, and a mechanical `chisurf.core.common` → `chisurf.core.support.common`
rewrite pastes over *both* kinds of caller. A file that stopped importing is a
red suite; a file that now imports the wrong `common` and silently loses
`atom_weights` is a wrong-answer path — the PDB parser's `except KeyError`
printed "Cloud not assign parameters" and kept going.
