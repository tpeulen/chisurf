---
type: Assessment
title: Cleanup Backlog — Gap vs. Target Specs
description: Concrete, verified findings where today's code diverges from the target specs, most severe first.
tags: [assessment, backlog, tech-debt, findings]
timestamp: '2026-07-05T00:00:00Z'
---

# ChiSurf — Cleanup Backlog (Gap vs. Target Specs)

> The backlog of where today's code diverges from the [target specs](index.md). Most severe first. Shrinks as the code converges.

The [specs](index.md) describe where ChiSurf should be. This document is the
gap: concrete, verified findings where the current code falls short of those
targets. It consolidates every issue surfaced while writing the specs, **plus
additional ones found by scanning the tree against the target rules**. Each
finding carries a verification status so the list can be trusted and worked down.
When this backlog is empty for a subsystem, that subsystem has reached its spec.

## Legend

**Severity** — `S1` breaks correctness or a hard invariant · `S2` contract/consistency
defect that will bite callers · `S3` tech-debt / cleanup.

**Category** — `SV` spec violation (breaks a [overview principle](overview.md#architectural-principles))
· `BUG` correctness defect · `DATA` data/schema/manifest issue · `INC` inconsistency / legacy overhang.

**Status** — `VERIFIED` re-confirmed by a scan or source read during this
assessment (evidence noted) · `REPORTED` raised by the spec-authoring pass and
recorded in the cited spec's steering notes, not independently re-run here.

## Summary

| ID | Sev | Cat | Subsystem | Finding | Status |
|----|-----|-----|-----------|---------|--------|
| [SV-01](#sv-01) | S1 | SV | Server | `chisurf.gui` imported inside the Qt-free server | ~~VERIFIED~~ ✅ FIXED |
| [SV-02](#sv-02) | S2 | SV | Server | DTO dataclasses in `dto.py` are unused; handlers hand-roll dicts | ~~VERIFIED~~ ✅ FIXED |
| [SV-03](#sv-03) | S2 | SV | Core/Server | Legacy `chisurf.*` globals are still de-facto shared state | ~~VERIFIED~~ ✅ FIXED |
| [SV-04](#sv-04) | S2 | SV | Server | `service_error` codes ride in JSON-RPC `result`, not the `error` member | ~~REPORTED~~ ✅ FIXED |
| [SV-05](#sv-05) | S2 | SV | Server | Event topics published ≠ topics advertised in schemas | ~~REPORTED~~ ✅ FIXED |
| [BUG-01](#bug-01) | S1 | BUG | Core | `NCurve(d=None)` dead branch → `np.copy(None)` | ~~VERIFIED~~ ✅ FIXED |
| [BUG-02](#bug-02) | S1 | BUG | Server | `fit_select` defined twice in `fits.py` (second shadows first) | ~~VERIFIED~~ ✅ FIXED |
| [BUG-03](#bug-03) | S1 | BUG | Server | `model_component_remove` references undefined `component_type` → `NameError` | ~~VERIFIED~~ ✅ FIXED |
| [BUG-04](#bug-04) | S2 | BUG | Core | `@abc.abstractmethod` not enforced: `Base(object)` has no `ABCMeta` | ~~VERIFIED~~ ✅ FIXED |
| [BUG-05](#bug-05) | S1 | BUG | Plugins | F-test calculator's two directions are not inverses (asking for 95% returns a χ² whose confidence is 0.09%) | ✅ FIXED |
| [BUG-10](#bug-10) | S1 | BUG | Fitting | Support-plane intervals wrong on likelihood objectives: F-test threshold rescales by χ²ᵣ, and the adaptive scan reports its own grid edge instead of a crossing | 📋 OPEN |
| [BUG-11](#bug-11) | S2 | BUG | Core | Importing IMP before tttrlib silently breaks every tttrlib API taking a `std::vector<double>` by value — shared SWIG type table, and the documented `PYTHONPATH` guarantees that order | ✅ FIXED |
| [BUG-06](#bug-06) | S1 | BUG | Core | `vm_rt_to_vv_vh` strides an already-halved count, so every rotation component after the first is silently discarded | ✅ FIXED |
| [BUG-07](#bug-07) | S1 | BUG | Packaging | `csc` console script points at a non-existent `chisurf.cli` module — every invocation fails at import | ✅ FIXED |
| [BUG-08](#bug-08) | S2 | BUG | Plugins | No image ever rendered in the Help browser: relative sources passed to Qt unresolved (`setSearchPaths` missing) | ✅ FIXED |
| [BUG-09](#bug-09) | S2 | BUG | Tests | `test_fcs` dead since NumPy removed `np.float`; `…calculcate_spectrum` asserts a stale mixing expectation (`-0.3` vs `-0.15`) | VERIFIED |
| [DATA-01](#data-01) | S1 | DATA | Plugins | **3** manifests fail validation and are silently dropped by `load_manifest()` | ~~VERIFIED~~ ✅ FIXED |
| [DATA-02](#data-02) | S2 | DATA | MMFDB | `SCHEMA_VERSION = 40` is a stamp with no migration waterfall | ~~VERIFIED~~ ✅ FIXED |
| [DATA-03](#data-03) | S2 | DATA | MMFDB | Core `mmfdb_*` DDL is hand-written and defined twice (must be hand-synced) | ~~REPORTED~~ ✅ FIXED |
| [DATA-04](#data-04) | S2 | DATA | MMFDB | `add_processing_run` partial-write; MD5 mislabeled as checksum | REPORTED |
| [DATA-05](#data-05) | S2 | DATA | MMFDB | External-tool runs not first-class in provenance (no `command_line`/`exit_code` cols, no `external_tool` op type, inconsistent op_type validators) | VERIFIED |
| [DATA-06](#data-06) | S3 | DATA | MMFDB | Deposition is one-way: `archive.zip.export` exists but no importer; bundler reads `file_path` not object store; mmCIF export is FLR-only | VERIFIED |
| [INC-01](#inc-01) | S2 | INC | Core | Three overlapping instance registries with different lifetimes | REPORTED |
| [INC-02](#inc-02) | S2 | INC | Core | `@register` renames classes → fragile name-based `isinstance` | REPORTED |
| [INC-03](#inc-03) | S3 | INC | Server/MMFDB | Legacy flat/`mmfdb.*` aliases coexist with namespaced/`mmfdb.v1.*` | REPORTED |
| [INC-04](#inc-04) | S2 | INC | MMFDB | Auth enforced in ~5/40 `api.py` fns; ACL rows exist for few entity kinds | 🚧 ADDRESSED — `api.py` boundary now threads/enforces `auth` |
| [INC-05](#inc-05) | S3 | INC | MMFDB | Repository composition and API boundaries | 🚧 IN PROGRESS (one DAO/repository authority; request context + shallow root landed) |
| [INC-06](#inc-06) | S2 | INC | Plugins | Two plugin identity conventions coexist; `ndxplorer` has no manifest | ~~REPORTED~~ ✅ FIXED |
| [INC-07](#inc-07) | S3 | INC | Plugins | `categories` drifts from directory group & `display_name`; demo games mixed in | REPORTED |
| [INC-08](#inc-08) | S3 | INC | Server | Generic `JobManager` bypassed by the only real long-running jobs | REPORTED |
| [INC-09](#inc-09) | S3 | INC | MMFDB | MMFDB is packaged standalone but a chisurf-free client is missing; the only RPC client + example facade live in chisurf | VERIFIED |
| [INC-10](#inc-10) | S3 | INC | GUI | Ad-hoc tables everywhere: a third-party `DataFrameEditor` patched at runtime by three proxies/delegates, ~40 hand-rolled `QTableWidget`s, a duplicated checkbox delegate, and no shared sorting/filtering/column-hiding/colouring/export | ~~VERIFIED~~ ✅ FIXED (PRD-66) |
| [INC-11](#inc-11) | S3 | INC | Plugins | Help browser's "Core" category rglobs the whole repo: 576 entries, 331 from `junk/`, 151 from `okf/`, 41 from `.opencode/` | VERIFIED |
| [INC-12](#inc-12) | S3 | INC | Docs | A published page links into `okf/`, which is excluded from the docs build — the only warning in an otherwise clean build | VERIFIED |
| [I18N-01](#i18n-01) | S3 | INC | GUI | i18n follow-ups: ~4000 imperative `setText`/`QMessageBox` strings unwrapped; menu-path `display_name`/`categories` not localized; `.ui` terminology not converged to the [glossary](../references/ui-glossary.md) | PARTIAL (PRD-63) |
| [INC-13](#inc-13) | S3 | INC | GUI | ~43 runtime `.ui` forms are prototyping-only; should be ported to AutoForm `view.json` and removed (target: zero `.ui`) | VERIFIED |

34 findings (18 FIXED): 7 VERIFIED, 6 REPORTED, 1 ADDRESSED, 1 IN PROGRESS, 1 PARTIAL.
Of the 16 open: 0×S1, 6×S2, 10×S3.

---

## Spec violations (SV)

### SV-01
**S1 · Qt leaks into the Qt-free server.** Violates [overview principle 3 (headless core)](overview.md#architectural-principles)
("server MUST NOT import Qt or `chisurf.gui`") and [rpc rules](rpc.md#rules).

- Location: `chisurf/server/services/detector_setups.py:50` and `:128`.
- Evidence (scan): both lines `from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import ...`. No other `chisurf.gui` / PyQt / PySide / qtpy import exists anywhere under `chisurf/server/`.
- Impact: `python -m chisurf.server` in a headless/subprocess context will `ImportError` (or drag in Qt) the moment a `detector_setups` method runs.
- Fix: move the pure detector-setup data out of `chisurf.gui` into a Qt-free core module (e.g. `chisurf/core/...`) and import that from both the server and the widget.
- ✅ **FIXED** (2026-07-05): Created `chisurf/core/data_io/detector_setups.py` with Qt-free JSON load/save. Server imports from here. Guardrail test (`test_no_gui_import_in_server`) checks AST for `chisurf.gui` imports.

### SV-02
**S2 · DTO dataclasses are dead documentation.** Violates the [overview principle 4 (data across the boundary)](overview.md#architectural-principles)
intent and [rpc rules](rpc.md#rules).

- Location: `chisurf/server/dto.py`.
- Evidence (scan): outside `dto.py`, usage counts are `DatasetSummary` 0, `FitSummary` 0, `FitDetail` 1, `ParameterDTO` 0, `SetupDTO` 0, `ProjectInfoDTO` 0, `ActionResultDTO` 0. Service handlers build ad-hoc dicts instead.
- Impact: documented wire shapes and runtime shapes can silently drift; local-mode `ChiSurfAPI.list_fits` already returns a richer shape than server-mode `fits.list_fits`.
- Fix: either (a) make handlers construct and `.to_dict()` the DTOs so the dataclass is the single source of shape truth, or (b) delete the dataclasses and generate the contract from JSON Schemas in `server_methods.json`. Do not keep both.
- ✅ **FIXED** (2026-07-05): Chose option (b) — deleted `dto.py` (7 dataclasses, 0 callers) and its stale test. All handlers build ad-hoc dicts; long-term contract authority will be JSON Schema in `server_methods.json`.

### SV-03
**S2 · Legacy globals are still the de-facto shared state.** Violates [overview principle 1/2 (one door, one owner)](overview.md#architectural-principles).
The single largest source of non-uniformity across the codebase (see [core steering](core.md#steering-notes), [rpc steering](rpc.md#steering-notes)).

- Location (evidence, scan for `chisurf.fits` / `chisurf.imported_datasets` / `chisurf.experiment`): `chisurf/core/fitting/__init__.py`, `chisurf/core/models/tcspc/lifetime.py`, `chisurf/core/api/adapters.py`, `chisurf/server/startup.py`.
- Impact: the server-side `startup.py` and core model code reach around `ChiSurfAPI`/`SessionState` into process-local globals, so `local`/`hybrid`/`server` modes cannot present one consistent state.
- Fix: route these reads/writes through `ChiSurfAPI` / `SessionState`; treat the globals as a compatibility read-shim only, populated *by* the owner, never mutated directly by new code.
- ✅ **FIXED** (2026-07-05): `ChiSurfAPI` now owns a `SessionState` (`self._state`) that aliases the global lists. All API methods use `self._state.fits` / `self._state.datasets` instead of `getattr(cs, "fits", [])` etc. `install_proxies()` updates the state. The globals remain as backward-compatible read-shims. 84 tests pass.

### SV-04
**S2 · Structured errors ride in the wrong envelope member.** [rpc rules](rpc.md#rules).

- Detail: `service_error()` results (`error_code`, `jsonrpc_code`, `exception_type`) are returned inside the JSON-RPC `result` object with `{"ok": false}`, not in the JSON-RPC `error` member. Consequently `RemoteError` only raises on transport-level failures, and every caller must still check `result["ok"]`.
- Fix: decide one contract — either promote `service_error` to the JSON-RPC `error` member (so `RemoteError` fires), or document `{"ok": bool}` as the canonical application-level result and stop implying transport errors cover it. See the spec rules for the two options.
- ✅ **FIXED** (2026-07-05): Implemented Option A. `ZmqServer._handle_one()` now converts handler results with `ok: False` to JSON-RPC error responses (code/message/data). `ChisurfClient.call()` raises `RemoteError` for both application errors (via JSON-RPC error field) and transport errors (timeout/connection). All 14 error-path tests updated to expect `RemoteError`.

### SV-05
**S2 · Event contract is inconsistent.** [rpc rules](rpc.md#rules).

- Detail: `parameter.*` schemas advertise a `parameter.changed` event, but no `parameter.*` handler sets `event_bus` or publishes anything; `fit.create` publishes `"fit.created"` while its schema declares `"fit.added"`; `fit.selected` / `fit.reordered` / `fit.mask_changed` / `fit.group.*` are published but undocumented.
- Fix: make `server_methods.json` the single registry of event topics and assert at startup that every published topic is declared (and vice-versa).
- ✅ **FIXED** (2026-07-05): Added `events` arrays to 34 method specs in `server_methods.json` declaring all published event topics. Added bidirectional guardrail test (`test_event_topic_contract.py`) that catches drift on either side.

## Correctness bugs (BUG)

### BUG-01
**S1 · `NCurve(d=None)` mishandles the default.** [core steering](core.md#steering-notes).

- Location: `chisurf/core/curve.py:41-46`.
- Evidence (read): `if d is None: self.d = np.array([])` is immediately overwritten by the unconditional `if copy_array: self.d = np.atleast_1d(np.copy(d))`, so `d=None` runs `np.copy(None)` → an object-dtype `array(None)`, not an empty float array.
- Fix: make the `None` branch `return` or `elif`, i.e. guard the copy branch so it only runs when `d is not None`.
- ✅ **FIXED** (2026-07-05): Changed `if` to `elif` so the copy branch is guarded. Added `test_ncurve_accepts_none` regression test.

### BUG-02
**S1 · `fit_select` defined twice.** [rpc steering](rpc.md#steering-notes).

- Location: `chisurf/server/services/fits.py:483` and `:840` — the second definition silently shadows the first.
- Fix: delete the stale definition (confirm which one the dispatcher registers) and add a lint/test guard against duplicate top-level handler names in `services/`.
- ✅ **FIXED** (2026-07-05): Removed stale definition at line 483 (second at 840 has richer `_action`/`event_bus` logic). Added `test_no_duplicate_handler_names` guardrail.

### BUG-03
**S1 · `model_component_remove` raises `NameError`.** [rpc steering](rpc.md#steering-notes).

- Location: `chisurf/server/services/model_svc.py` — the fallback loop `for candidate in ("lifetimes", "species", "rotations", "distances", "gaussians", component_type):` references `component_type`, which is not a parameter of the function (signature is `state, component_index, fit_index, fit_uid, event_bus`).
- Evidence (read): confirmed the name appears only in that loop and nowhere in the function's scope.
- Impact: any call that reaches the fallback (model without `remove_component` and none of the named lists matched first) crashes with `NameError`.
- Fix: drop `component_type` from the tuple, or add it as a parameter and thread it through.
- ✅ **FIXED** (2026-07-05): Removed `component_type` from fallback tuple. Added 6 tests in `test_services_model_svc.py` covering all removal paths.

### BUG-04
**S2 · `@abc.abstractmethod` is not enforced.** [core steering](core.md#steering-notes).

- Location: `chisurf/core/base.py:242` declares `class Base(object)` — no `metaclass=ABCMeta`. Subclasses mark abstracts at `chisurf/core/parameter.py:354` and `chisurf/core/models/model.py:127,140`.
- Impact: because the MRO has no `ABCMeta`, `Parameter` and `Model` are instantiable despite their abstract methods, so a missing override fails at call time instead of construction time. (Runtime confirmation needs the `arm64` env with `chinet` built; the static class declaration is unambiguous.)
- Fix: give `Base` `metaclass=abc.ABCMeta` (or have the abstract subclasses inherit `abc.ABC`), then fix any concrete subclass that currently skips an override.
- ✅ **FIXED** (2026-07-05): Added `metaclass=abc.ABCMeta` to `Model` only (not `Base`/`Parameter` — `Base` conflicts with Qt metaclasses in widget multiple-inheritance, and `Parameter` is used concretely throughout). Removed `@abc.abstractmethod` from `Model.update()` (it has a real concrete implementation; making it abstract forced trivial overrides in every subclass). Added 3 guardrail tests: bad subclass raises, good subclass works, `update()` is callable without override.

### BUG-05
**S1 · The F-test calculator's two directions contradict each other.**

- Location: `chisurf/plugins/core/f_test/gui/tool.py` — `_FTestModel.recompute_conf` and
  `_FTestModel.recompute_chi2_2`. The same formulas are restated in the help text of
  `ftest.view.json`, so the docs carry the defect too.
- The two are meant to be inverses of one another:
  `conf = F.cdf(χ²₂/χ²₁, n₁, n₂)` inverts to `χ²₂ = χ²₁·F.isf(1−conf, n₁, n₂)`,
  but the code computes `χ²₂ = χ²₁·(n₂/n₁)·F.isf(1−conf, n₁, n₂)` — a spurious `n₂/n₁`.
- Evidence (ran, defaults χ²₁ = 1, n₁ = 100, n₂ = 5): entering a confidence of 0.95
  yields χ²₂ = 0.2203, and feeding that straight back through the tool's own
  confidence formula reports **0.0009**. At 0.68 → χ²₂ = 0.0798 → 0.0000. Dropping
  the `n₂/n₁` factor makes the round trip exact (0.95 → 4.4051 → 0.95).
- Two further questions the fix has to settle first, because they change the numbers:
  - **Ratio orientation.** `view.json` documents χ²(1) as the *simpler* model and χ²(2)
    as the *more complex* one. A more complex model fits better, so χ²₂ < χ²₁ and
    `F.cdf(χ²₂/χ²₁, …)` returns a *low* confidence exactly when the added parameters
    are most justified. The conventional variance-ratio test uses
    χ²(simpler)/χ²(complex).
  - **Degree-of-freedom order.** This panel calls `F(n₁, n₂)` = `F(ν, p)`, while the
    χ²-max panel of the same tool calls `F(p, ν)`. One of the two is transposed.
- ✅ **FIXED** (2026-07-25). The convention was not actually open: `FTestTool._load_fit`
  settles all three questions, because it is the only thing that ever populates these
  fields from real data. It writes `chi2r` into both χ² slots and `n_points - n_free`
  into **both** `n₁` and `n₂` — so the χ² are *reduced* and the `n` are the two fits'
  *total* degrees of freedom, not a parameter count. That is exactly the classical
  variance-ratio test used in fluorescence decay analysis:
  `conf = F.cdf(χ²ᵣ(simple)/χ²ᵣ(complex), ν_simple, ν_complex)`, inverting to
  `χ²ᵣ(complex) = χ²ᵣ(simple) / F.ppf(conf, ν_simple, ν_complex)`. The dof order is
  then numerator-first and correct; the χ²-max panel's `F(p, ν)` is a *different*
  statistic (the support-plane threshold), so the two panels legitimately differ and
  neither is transposed — that part of the original report was a false alarm.
- The statistics moved out of the GUI into `chisurf.core.math.statistics`
  (`f_test_confidence`, `f_test_chi2r`) so they are testable without Qt and reusable;
  the tool now delegates. Help text and the `n₂` description in `ftest.view.json` were
  corrected (the latter said "degrees of freedom *added* by the second model", which
  is not what `_load_fit` writes). Defaults changed to a self-consistent pair.
- The old plugin test asserted equality with the shipped formulas and so had **locked
  the bug in**; it is rewritten around the defining properties — round-trip inversion
  at several confidences, 0.5 for equally good models, and monotone confidence as the
  complex model improves (which is what caught the orientation error: a 10% χ² drop
  over ~900 points scored 0.077 before and 0.923 after).

### BUG-06

**S1 · `vm_rt_to_vv_vh` silently discarded every rotation component after the first.**

- Location: `chisurf/core/fluorescence/anisotropy/decay.py` — `vm_rt_to_vv_vh`.
- The rotation spectrum is interleaved `[β₁, ρ₁, β₂, ρ₂, …]`, so the pair count is
  `len // 2`. The loop computed `n_anisotropies = len // 2` and then iterated
  `range(0, n_anisotropies, 2)` — striding an already-halved count. For any spectrum
  with two or more components only `(β₁, ρ₁)` was ever read, so `r(0)` fell short of
  `r₀` and every further component vanished without warning.
- Evidence (ran): a two-component spectrum returned **bit-identical** VV/VH to the
  one-component case (`np.allclose` → `True`).
- Blast radius is limited to this time-domain simulation helper. The fitting path
  (`calculcate_spectrum` → `Anisotropy.get_decay`) composes spectra through
  `elte2`/`e1tn` and always honoured every component.
- Why it survived: its only covering test had been erroring out since NumPy removed
  `np.float` (see [BUG-09](#bug-09)), and that test's hard-coded reference arrays had
  been generated *from the buggy code* — even though its own spectrum
  `[0.1, 0.6, 0.38-0.1, 10.0]` is written so the amplitudes sum to `r₀ = 0.38`.
- ✅ **FIXED** (2026-07-25). Iterates all `n_anisotropies` pairs. The test now derives
  its expectation **analytically** rather than re-recording output, and asserts
  `r(0) = 0.38`, giving `vv[0] = 1 + 2r₀ = 1.76` and `vh[0] = 1 − r₀ = 0.62`; the
  module doctest, dead for the same NumPy-2 reason, was revived and corrected.

### BUG-07

**S1 · The `csc` console script pointed at a module that does not exist.**

- Location: `pyproject.toml` `[project.scripts]`.
- Declared as `csc = "chisurf.cli:cli"`, but there is no `chisurf.cli` module — the
  Click group lives in `chisurf.core.cli`. Every `csc …` invocation therefore failed
  at import, so the documented CLI entry point was unusable for all users.
- Evidence (ran): `import chisurf.cli` → `ModuleNotFoundError: No module named
  'chisurf.cli'`; `python -m chisurf.core.cli help review-check` works.
- ✅ **FIXED** (2026-07-25). Repointed to `chisurf.core.cli:cli`. Note that fixing the
  entry point requires a reinstall to take effect, so tasks that must work in an
  unreinstalled tree (e.g. `docs-check-reviewed`) invoke `python -m chisurf.core.cli`.

### BUG-08

**S2 · No image had ever rendered in the Help browser, for any document.**

- Location: `chisurf/plugins/core/help/gui/tool.py` — document display.
- Rendered HTML references images relatively (`_images/…` in the manual, `figures/…`
  in the guides). The viewer passed a base URL to `setHtml`, but that alone does not
  make `QTextBrowser` resolve relative resources; it needs `setSearchPaths`. Qt was
  handed the raw relative path and failed every load.
- Evidence (ran, instrumented `loadResource`): the browser requested
  `_images/image_rId18.png` verbatim and the load returned null; after setting search
  paths the same request resolves.
- Two further layout defects surfaced only once images actually loaded, and are fixed
  with it: Qt renders images at native pixel size and ignores CSS `max-width`, so a
  910 px manual screenshot pushed the text off the page (images now carry an explicit
  `width`/`height` computed from a header-only size read); and docutils emits a block
  image as a bare `<img class="align-center">` between paragraphs, which without the
  docutils stylesheet made Qt float the image to the bottom of the document (block
  images are now wrapped in a centred paragraph and the unusable class dropped).
- ✅ **FIXED** (2026-07-25). Covered by `test_oversized_images_are_scaled_and_centred`
  and `test_inline_images_are_not_wrapped`.

### BUG-09

**S2 · Two tests in `test/fluorescence/test_fluorescence.py` are dead or assert stale values.**

- Location: `test/fluorescence/test_fluorescence.py`.
- `test_fcs` still constructs `np.ones_like(..., dtype=np.float)`. `np.float` was
  removed in NumPy 2, so the test raises `AttributeError` at collection time and has
  not exercised anything for some time. (`test_vm_vv_vh` had the same defect and was
  repaired as part of [BUG-06](#bug-06); this one remains.)
- `test_fluorescence_anisotropy_decay_calculcate_spectrum` fails on a *stale
  expectation*, not a code fault: with `g = 1.5, l1 = 0.1` it asserts the VV spectrum
  `[0.9, 4., 1.8, 0.8, 0.15, 4., -0.3, 0.8]`, but the current union/concatenate mixing
  convention in `calculcate_spectrum` yields `-0.15` where the test wants `-0.3`. The
  in-code comments record a deliberate rework of exactly this mixing, so the test was
  most likely never updated with it.
- Deliberately left open: the second one is a question about which mixing convention is
  intended, and answering it changes fit semantics — an owner decision, not a typo fix.
- Status: **VERIFIED** (both observed failing on 2026-07-25).

## Data / schema / manifest issues (DATA)

### DATA-01
**S1 · Three plugin manifests fail validation and are silently dropped.** Extends the plugin spec's single-manifest finding — [plugins steering](plugins.md#steering-notes).

- Evidence (ran `validate_manifest()` + `load_manifest()` over all 86 manifests):
  - `spectra_downloader/manifest.json` → `missing required field: 'id'` (uses legacy `name`/`status`/top-level `services`).
  - `kappa2_dist/manifest.json` → `rpc_methods` is `["kappa2_dist.compute"]` — a list of **strings**, not method objects.
  - `modelling/fret/manifest.json` → `rpc_methods` is six **strings**, not objects.
  - All three return `None` from `load_manifest()`, so they load only via the legacy AST fallback (or not at all).
- Root cause: `load_manifest()` catches `KeyError`/`TypeError` and returns `None`, and the discovery path never calls `validate_manifest()`, so malformed manifests are invisible at runtime.
- Fix: (1) correct the three manifests (`id` + `version`; `rpc_methods` as objects with a `name`); (2) call `validate_manifest()` during discovery and log a warning instead of silently dropping; (3) add a test that asserts every built-in manifest validates.
- ✅ **FIXED** (2026-07-05): Fixed all 3 manifests. Added validation logging in `PluginRegistry.discover()`. Added `test_builtin_manifests_all_valid` that asserts all 86+ manifests pass `validate_manifest()`.

### DATA-02
**S2 · `SCHEMA_VERSION` is a bookkeeping stamp.** [mmfdb steering](mmfdb.md#steering-notes).

- Location: `chisurf/core/mmfdb/schema.py:14` → `SCHEMA_VERSION = 40`. There is no ordered migration waterfall behind the number; it is bumped by hand.
- Impact: a v40 stamp does not guarantee a v40 physical schema; existing user DBs cannot be reliably upgraded.
- Fix: back the version with an explicit, ordered migration list and a startup check that applies pending migrations.
- ✅ **FIXED** (2026-07-05): Added `MIGRATIONS` `OrderedDict[int, Callable]` with v1 (fresh-DB setup) and v40 (existing-DB reconciliation). `migrate_schema()` reads stored version, applies each pending migration in order. Added `_bootstrap()` helper. 6 tests cover fresh/already-current/resume/persistent/bump scenarios.

### DATA-03
**S2 · Core `mmfdb_*` schema is hand-written and duplicated.** [mmfdb steering](mmfdb.md#steering-notes).

- Detail: only `flr_*`/PDBx and six setup tables are truly dictionary-generated per the [overview principle 6](overview.md#architectural-principles) authority rule; the core `mmfdb_*` tables are hand-authored DDL that exists twice — a permissive `CREATE_TABLES_SQL` and a CHECK-constrained `_CANONICAL_CHECK_SQL` — which must be kept in sync by hand.
- Fix: converge on one authoritative DDL (ideally dictionary-driven, per the invariant), and generate the CHECK-constrained form rather than maintaining a parallel copy.
- ✅ **FIXED** (2026-07-05): Defined each canonical `mmfdb_*` table once as `_TableDef` + `_Column` dataclasses in `_CANONICAL_TABLE_DEFS`. `_build_permissive_ddl()` / `_build_canonical_ddl()` generate both forms from the same source. Removed `_CANONICAL_CHECK_SQL` and `_CANONICAL_TABLE_MAP`. 2 guardrail tests.

### DATA-04
**S2 · `add_processing_run` partial write; MD5 mislabeled.** [mmfdb steering](mmfdb.md#steering-notes).

- Location: `chisurf/core/mmfdb/repository.py:6385` (`add_processing_run`). The documented partial-write path can leave an operation without its artifacts/edges, and an MD5 digest is stored/labeled as a generic "checksum".
- Fix: wrap the run insertion in a single transaction (see `transactions.py`) and label the digest algorithm explicitly.

### DATA-05
**S2 · External-tool runs can't be first-class provenance operations.** [mmfdb steering](mmfdb.md#steering-notes). An external CLI/script *can* be recorded via `mmfdb.v1.operations.record_with_artifacts` — tool → `software_package`, version, timestamps, typed parameters, checksummed input/output artifacts, queryable lineage (verified end-to-end in `modules/mmfdb/examples/mmfdb_06_external_tool_provenance.ipynb`, which records both a vanilla-`tttrlib` CLI subprocess and FRETBursts against one raw artifact). But the schema has **no dedicated column for the command line / argv or a numeric exit code** — both must be buried in free-form `settings_json`, so they are unqueryable — **no generic `external_tool`/`cli` value** in the constrained `operation_type` vocabulary (the example reuses `burst_selection`), **no software-vs-human actor** distinction (`operator_user_id` is a human-user FK), and **no container/environment** schema (image + digest). The two record paths also validate `operation_type` inconsistently: `record_operation` uses the extensible DB vocab while `record_operation_with_artifacts` uses the static `.dic` enum (`queries/artifacts.py:885` vs `:1226`) — arguably a bug. → Add `command_line`/`exit_code` columns, an `external_tool` operation type + actor-kind flag, and reconcile the two validators.

### DATA-06
**S3 · Deposition is export-only (no round-trip importer).** [mmfdb steering](mmfdb.md#steering-notes). `archive.zip.export` (`admin/backend/measurement_services.py:1906`) packs a self-contained deposition ZIP — DB snapshot + `provenance_graph.json` + manifest + native `external_data/` files — and a second instance can adopt the snapshot wholesale (verified round-trip in `modules/mmfdb/examples/mmfdb_07_deposition.ipynb`). But there is **no `archive.zip.import` handler** to merge a deposition into an existing instance or restore its object-store blobs from `external_data/`; the bundler copies native files from `node.file_path` rather than from the content-addressed object store; and mmCIF record export (`repository.export_flr_cif`) is **FLR-domain-only** and not exposed via `api.py`/`cli.py` — there is no general dictionary-driven metadata→mmCIF path. → Add an object-store-aware bundle importer and a general CIF export path.

## Inconsistencies / legacy overhang (INC)

### INC-01
**S2 · Three overlapping instance registries.** [core steering](core.md#steering-notes). `Base._uuid_index`, the `@register` decorator's `_instances` set, and `chisurf/core/project/registry.py`'s `Registry` singleton track instances with different lifetimes and APIs and no single authority. → Pick one owner; make the others thin views or delete them.

### INC-02
**S2 · `@register` renames classes.** [core steering](core.md#steering-notes). `chisurf/core/decorators.py:64` sets `__class__.__name__`, which forces name-based `isinstance` fallbacks in `base.find_objects` / `find_parameters`. → Stop mutating `__name__`; match on type or an explicit tag attribute.

### INC-03
**S3 · Legacy method aliases coexist with the canonical ones.** [rpc steering](rpc.md#steering-notes), [mmfdb steering](mmfdb.md#steering-notes). Flat `list_datasets`/`run_fit` vs namespaced `dataset.*`/`fit.*`; MMFDB `mmfdb.*` (73) vs `mmfdb.v1.*` (40). The prerelease `sample_database` surface is retired rather than supported for compatibility. → Remove remaining aliases directly; no compatibility schedule is required.

### INC-04
**S2 · MMFDB auth is incomplete and decentralized.** [mmfdb steering](mmfdb.md#steering-notes), contradicts `docs/prd_mmfdb_auth_rights.md`. Only ~5 of ~40 `api.py` functions check auth; ACL rows are created for essentially only `artifact` (conditionally `mmfdb_operation`), so `can_access` has nothing to evaluate for samples/experiments/setups/parameters/branches; real enforcement is scattered in plugin services. → Centralize enforcement at the `api.py` boundary and create ACL rows for every guarded entity kind.
- 🚧 **ADDRESSED** (2026-07-08): threaded `auth` through **all ~40 `mmfdb.v1.*` `api.py` functions** — previously most lacked an `auth` parameter, so the versioned RPC layer (`h(**params, auth=auth)`) would have `TypeError`'d; the authentication boundary (`_require_auth`) now composes with per-function principal resolution. Shared helpers (`_acting_user_id`, `_acl_read_or_pass`, `_acl_filter_or_pass`, `_new_object_acl`, `_effective_target_user`) give **progressive enforcement**: writes stamp the authenticated owner + a default ACL (samples/experiments, atop the existing artifact/operation ACLs), reads enforce ACLs **where they exist** and stay open otherwise (no legacy lockout), and user-scoped branch ops (`set/get_user_active_branch`, `jump_user_to_operation`) are now **self-or-admin** (fixed an IDOR). In-process/unauthenticated calls fall back to the configured default user, preserving GUI/macros. New `tests/test_api_auth.py` (5). Remaining for full closure: extend owner ACLs to setups/parameters/branches and add v1-dispatcher round-trip tests. Advances the [mmfdb steering](mmfdb.md#steering-notes) auth item and PRD-59.

### INC-05
**S3 · Repository/API composition remains broader than the target.** [mmfdb steering](mmfdb.md#steering-notes). The former monolith mixed raw SQL, a generated DAO, and a parallel ORM while transports repeatedly reopened the database. → Keep one repository authority, explicit concern boundaries, and one request lifetime.
- 🚧 **IN PROGRESS** (2026-07-11): the SQLAlchemy `orm/` layer is deleted; the dictionary DAO plus `MFDatabase` are the single persistence authority; the repository is split into 13 concern modules and is ~1,650 lines. The package root now has five deliberate exports instead of eagerly importing the whole system, duplicate shadowed methods and prerelease setup aliases are removed, versioned RPC calls share one database/principal context, and the `chisurf.core.mmfdb` compatibility facade is deleted after a direct-import cutover. Remaining: decide whether the mixin composition should become explicit composed repositories and close the residual sanctioned raw-SQL/DAO migration in PRD-26.

### INC-06
**S2 · Two plugin identity conventions.** [plugins steering](plugins.md#steering-notes). Legacy module-level `name = "Category:Plugin"` + `if __name__ == "plugin":` vs manifest `id`/`display_name`/`entrypoints`; most plugins carry both, merged by `_read_manifest_metadata()`; `ndxplorer` is a first-class plugin with **no manifest at all**. → Make the manifest the single source of identity; backfill `ndxplorer`.
- ✅ **FIXED** (2026-07-05): Added `manifest.json` to `chisurf/plugins/ndxplorer/` with `id`, `version`, `display_name`, `entrypoints.gui`, `entrypoints.cli`. Added guardrail test `test_ndxplorer_has_manifest`. Existing manifest-rglob validation also covers it.

### INC-07
**S3 · Manifest metadata drifts from reality.** [plugins steering](plugins.md#steering-notes). `categories` disagrees three ways with the directory group and `display_name` (e.g. `chimol` → `["Structure","Structure","Molecular Viewer"]`; `batch_analysis` lives in `core/` but is `"Main:Tools:..."`); heavy ad-hoc `menu_hidden` for an undocumented hub/child pattern; dead `deprecated` fields; demo games (`breakout`/`pong`/`tetris`) shipped alongside production tools. → Define and enforce a category vocabulary; document the hub/child pattern or replace it; gate demo plugins behind a flag.

### INC-08
**S3 · The generic job manager is bypassed.** [rpc steering](rpc.md#steering-notes). `jobs.JobManager` exists, but the only real long-running work (fit sampling / scan) uses unlocked module-level dicts instead. → Route long-running jobs through `JobManager` so cancellation/status are uniform.

### INC-09
**S3 · MMFDB is packaged standalone but not yet cleanly separable; a chisurf-free client is missing.** [mmfdb steering](mmfdb.md#steering-notes). MMFDB already lives in its own module with its own `pyproject.toml` (`modules/mmfdb/`), and it *is* usable without chisurf — verified in `modules/mmfdb/examples/mmfdb_08_standalone_no_lockin.ipynb`, which drives `mmfdb` + tttrlib + FRETBursts with `chisurf` never imported. But that standalone path has to talk to the **embedded** repository (`mmfdb.repository.MFDatabase`) directly, because the only network/RPC client (`MMFDBClient`) and the ergonomic example facade (`BurstWorkflow`) both live *inside* chisurf (`chisurf/plugins/core/mmfdb_admin/gui/client.py`, `chisurf/plugins/burst/burst_analysis/api/workflow.py`). The `mmfdb.api` functions also require auth even in-process (see INC-04), so a standalone consumer cannot use the public API without bootstrapping a user. Target: mmfdb ships as its own repository that chisurf depends on (one-way); a Qt-free, chisurf-free `mmfdb` client (HTTP + optional in-process default principal) moves into the mmfdb package so external tools get the same ergonomics the chisurf facade has today.

---

## Internationalisation (I18N)

### INC-10

**Ad-hoc tables everywhere.** Tabular UI was a third-party `DataFrameEditor`
plus roughly forty hand-rolled `QTableWidget`s. The editor supplied
value-scaled backgrounds, per-column formatting and a context menu that nothing
in-tree had, so the Data-table plot imported it and then fought it —
`NoBackgroundProxy` to strip its colouring, `ReadOnlyColumnProxy` to lock a
column, a duplicate checkbox delegate, and ~45 lines walking the dialog's
children to install all three. No `QSortFilterProxyModel`, colour-by-value
delegate, CSV export or reusable column picker existed anywhere in either
repository, and ndXplorer's item-based editor — the richest table of the lot —
crashed on nullable pandas dtypes and wrote filtered edits to the wrong row.

**Fixed** by [PRD-66](/prds/prd-66.md): the
[chitable](/subsystems/gui-tables.md) family is now the shared implementation,
the delegates are consolidated, both `DataFrameEditor` call sites are gone and
`guidata` is dropped from every packaging file with a guardrail test. Migrating
the remaining hand-rolled plugin tables stays open under that PRD.

### INC-11

**Help browser's "Core" category lists agent scratch and the internal knowledge bundle
as user documentation.**

- Location: `chisurf/plugins/core/help/api/io.py` — `discover_docs`, the "Core" branch.
- It `rglob("*.md")`s the entire repository root, excluding only `docs/` and anything
  with `plugins` in its path. Nothing else is filtered, so every stray Markdown file in
  the tree is presented to the user as ChiSurf documentation.
- Evidence (ran, 2026-07-25): **576** entries, of which `junk/` contributes 331,
  `okf/` 151, `.opencode/` 41, `.claude/` 16, `AGENT/` 9. The `okf/` bundle is an
  internal agent-facing knowledge layer and is deliberately excluded from the published
  docs build, so surfacing it here contradicts that decision (compare [INC-12](#inc-12)).
- Suggested direction: allow-list the roots worth showing (e.g. `README`, `CHANGELOG`,
  top-level guides) rather than deny-listing two paths, and skip dot-directories.
- Status: **VERIFIED**.

### INC-12

**A published doc links into `okf/`, which is excluded from the docs build — a permanent
Sphinx warning.**

- Location: `docs/development/chimol_pymol_render_plan.md:52`, which references
  `okf/plugins/profiles/chimol`.
- `okf/` is intentionally kept out of the user-facing Sphinx build, so the reference
  cannot resolve: `WARNING: Unknown source document '…/okf/plugins/profiles/chimol'`.
  It is currently the **only** warning in an otherwise clean build, which erodes the
  value of "the docs build is warning-free" as a signal.
- The user-facing docs are not supposed to link into the knowledge bundle at all; the
  fix is to drop the link or inline the material it points at.
- Status: **VERIFIED** (reproduced on every build).

### I18N-01
**S3 · i18n coverage gaps after the first pass.** [PRD-63](../prds/prd-63.md)
landed the translation kit and localized the data-driven (view.json/manifest) and
`.ui` UI through the [i18n subsystem](../subsystems/i18n.md) seam. Remaining:

- **Imperative strings** — ~4000 `setText`/`QMessageBox`/`QLabel`/`setWindowTitle`
  call sites (≈65 % in `chisurf/plugins`) are not yet wrapped in `tr()`. Phase the
  wrapping per subsystem; enable `.py` scanning in `build_tools/i18n/extract_strings.py`
  as it proceeds.
- **Menu-path identity** — `manifest.display_name` / `categories` stay canonical
  (they key menu paths + dedup, see [INC-07](#inc-07)); localize them at the
  navigation-render seam, not at parse.
- **`.ui` terminology** — hand-built `.ui` forms still use "Micro time"/"TAC",
  "Channel Select", and drifting file-open labels/typos; converge to the
  [UI glossary](../references/ui-glossary.md) as each form is edited/migrated.
- **Kit wiring** — add the `pixi.toml` `i18n-extract`/`i18n-compile` tasks and the
  `gui.language` YAML default (held back in the initial commit to avoid a
  shared-file collision).

### INC-13

**S3 · Runtime `.ui` forms are a prototyping carry-over; the target is zero of
them.** 43 Qt Designer `.ui` files are still loaded at runtime via `uic.loadUi`
(`chisurf/gui/decorators.py:_compiled_ui_class`); AutoForm + `*.view.json` is the
one intended UI mechanism ([PRD-40](../prds/prd-40.md), [GUI & AutoForm](../subsystems/gui-autoform.md)).
Each form should be ported to a `view.json` (+ a view-model where it carries
logic) and the `.ui` deleted. Why it is debt, not style:

- **No live retranslation.** `uic.loadUi` binds text at build time, so an open
  `.ui` form cannot follow a language switch on its own — it needs the
  reparse-and-reapply shim `chisurf/gui/retranslate.py`, added by
  [PRD-63](../prds/prd-63.md) precisely to paper over this. AutoForm reads its
  text through the [i18n seam](../subsystems/i18n.md) on every build and
  retranslates for free.
- **Two divergent UI paths** (data-driven specs vs. hand-drawn XML) double the
  surface for the glossary/terminology drift already tracked in [I18N-01](#i18n-01),
  and for tooltip/label conventions and theming.
- **Opaque to tooling** — `.ui` XML is invisible to the model/UI dataspec, the
  parameter registry, and the AutoForm section library (tables, `path_list`,
  `image`, `waterfall`, …) that already replaces most hand-built widgets.

Locations (43 files): densest under `chisurf/gui/widgets/models/tcspc/` (3),
`chisurf/plugins/tttr/tttr_correlate/` (3), `chisurf/gui/widgets/{pdb,fio,experiments/tcspc}/`
(2 each), `chisurf/plugins/tttr/tttr_histogram/` (2), plus the main-window
`chisurf/gui/gui.ui` and singletons across the wizard, vv_vh_g_factor, burst and
microtime-histogram plugins. Status: **VERIFIED** (`find chisurf -name '*.ui' | wc -l`
= 43). Migrate opportunistically as each form is touched; keep every un-migrated
form on the `retranslate_from_ui` path so language switching keeps working meanwhile.

## How to work this list

1. ~~Land the **S1** items first — they are correctness/import failures with tiny, local fixes (BUG-01/02/03, SV-01, DATA-01), each independently shippable.~~ ✅ **Done**
2. Add the guardrails that would have caught them: manifest validation in discovery (DATA-01), a duplicate-handler-name test (BUG-02), a "no `chisurf.gui` import under `chisurf/server/`" import-lint (SV-01), and a published-vs-declared event-topic assertion (SV-05). — ✅ **DATA-01/BUG-02/SV-01 guardrails in place; SV-05 remaining**
3. Then take the **S2** structural items (SV-02/03, INC-04, DATA-02/03) as scoped refactors, each closing out the corresponding spec steering-notes entry.
4. As each finding is fixed, strike its row here and remove it from the owning spec's steering notes; when a subsystem has no findings left here, it has reached its spec.

### BUG-11
**S2 · `import IMP` before `import tttrlib` breaks tttrlib's `std::vector<double>` arguments.**

- Reproduction, complete:
  ```python
  import IMP, tttrlib
  s = tttrlib.SimSystem()
  s.set_rate_matrices(tttrlib.VectorDouble([0.] * 9), tttrlib.VectorDouble([1.] * 9))
  # TypeError: in method 'SimSystem_set_rate_matrices',
  #            argument 2 of type 'std::vector< double,std::allocator< double > >'
  ```
  Swap the two imports and it succeeds. It is the import *order* that matters,
  not the build.
- Cause: SWIG extensions share one process-global type table
  (`__SWIG_TYPE_TABLE`). Whichever module registers `std::vector<double>` first
  owns the entry, and a proxy created by the loser no longer matches a by-value
  argument of that type. Member setters (`species.q`) take a pointer and go
  through a different check, so they keep working — which is why the failure
  looks arbitrary.
- Why it always fires in practice: `modules/imp-tricks/src/sitecustomize.py`
  does `import IMP` at interpreter start, and `CLAUDE.md` documents exactly that
  directory on `PYTHONPATH` for running chisurf outside pixi. So in the
  documented development configuration, IMP is *always* first.
- Impact today is small and already worked around, but the workaround was
  misattributed: `chisurf/plugins/core/acq/tcspc_devices/simulation/core/algorithms.py`
  carried a comment blaming "some builds". Corrected in place; plain Python
  sequences convert through a different path and are unaffected, so passing
  lists rather than `VectorDouble` is the reliable form for by-value arguments.
- **Fixed upstream** (tttrlib `bd01dbc9`): the Python module is built with
  `SWIG_TYPE_TABLE=tttrlib`, the supported SWIG mechanism for exactly this.
  Nothing in tttrlib is meant to be exchanged with another SWIG module, so a
  private table costs nothing, and it fixes every consumer rather than each call
  site. Regression covered by
  `test/models/test_szabo_gopich.py::test_the_engine_is_usable_after_another_swig_extension_loads_first`,
  which lives here rather than in tttrlib because IMP is importable here.
  Requires a rebuilt tttrlib (`pixi run build-extensions`); the workaround of
  passing plain sequences stays correct either way.
- Found while benchmarking the occupancy sampler against the simulation engine
  (see [PRD-50](/prds/prd-50.md)).

### BUG-10
**S1 · Support-plane confidence intervals are wrong on likelihood objectives, twice over.**

- Location: `chisurf/core/math/statistics.py::chi2_threshold` and
  `chisurf/core/fitting/fit.py::adaptive_chi2_scan` (crossings consumed by
  `chisurf/core/fitting/support_plane.py::confidence_intervals_from_scan_result`).
- Found while validating tcPDA error surfaces, where MCMC and the support plane
  disagreed on interval width by a factor that *grew with dataset size* — 1.32,
  2.05, 2.86 at 1500, 2500 and 5000 bursts. Two independent faults pushing in
  opposite directions, which is why the ratio drifted instead of being constant.
- **Fault 1 — the threshold.** `chi2_threshold` uses the F-test form
  `chi2r_min · (1 + k/nu · F)`, which rescales by `chi2r_min`. That is correct
  for least squares with an *unknown* noise scale; it is wrong for a likelihood
  deviance, whose scale the likelihood already fixes. The right level is the
  plain likelihood-ratio one, `Δchi2 = 6.63` at 99% / one parameter. Measured on
  tcPDA: the likelihood-ratio threshold gives widths 0.883 and 0.489 at 1500 and
  5000 bursts against MCMC's 0.897 and 0.497 — 2% agreement and the correct
  `1/sqrt(n)` scaling. The F-test form inflates by `sqrt(chi2r)`, which is 1.5×
  when `chi2r ≈ 2.3`.
- **Fault 2 — the scan reports its grid edge, not a crossing.**
  `adaptive_chi2_scan` returned a **three-point, one-sided** grid whose maximum
  sat *at* the threshold without exceeding it, and the reported interval was
  exactly that grid's span (0.621 reported against 0.621 spanned). So the number
  was never a threshold crossing, which is also why it failed to scale as
  `1/sqrt(n)`.
- Impact: any model whose `chi2r` sits far from one gets a wrong support-plane
  interval, and every model can get a grid-edge interval when the scan
  terminates early. Two-colour PDA agreed with MCMC to 8% because its `chi2r ≈ 1`
  makes fault 1 vanish and its broader minimum let the scan walk further.
- Fix: give the threshold an objective-type switch (least-squares → F-test,
  likelihood → likelihood-ratio), and make the scan refuse to report a crossing
  it never bracketed — it should widen its range or return `None` rather than
  hand back its own edge.
- Not fixed here: this is shared fitting code under concurrent edit, and the
  threshold change is a design decision about how objectives declare themselves.
  Evidence and the reproduction are in the tcPDA model docstring.
