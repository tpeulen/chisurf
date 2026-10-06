---
type: Plan
title: Handover -- fit-window emtk pages, Plot settings, docs conversion, manual screenshots (2026-10-06)
description: State and open front of the fit-window/Plot-settings emtk port, the rST->MyST docs conversion, the manual screenshot refresh and the view-scheme question, for the next agent.
tags: [handover, fit-window, emtk, plot-settings, docs, screenshots, schema]
timestamp: '2026-10-06T00:00:00Z'
---

# Handover: fit window, Plot settings, docs (2026-10-06)

All work is **committed locally in chisurf, nothing pushed**. Read
[fit window](../subsystems/fit-window.md) "Where to pick this up" first; it is
the durable resume list for the GUI half. This page adds the docs half and the
commit map.

## Commits (chisurf, newest last)

| Commit | What |
|---|---|
| `369595863` | chiplot `Panel` (Qt-free plot panel); pages declare panels |
| `ad0fec046` | Posterior graph / Chain diagnostics / What-if in emtk and back in every fit window |
| `c2e7414bc` | Pages are not `QWidget`s; *Plot settings* dock is one emtk surface (`chisurf/gui/plots/emtk_settings.py`) drawing each page's AutoForm `settings_view` |
| `501e90bcf` | OKF: order-dependent GUI failures predate the port |
| `4dfa137c8` | Docs rST -> MyST Markdown (only `docs/development/api.rst` stays rST) |
| `c1a7b80d3` | View scheme: emtk layout keys are `Section` dataclass fields |
| `1182fe7ea` | Global-fit editor actions fixed; loaded background/lin-table keep names |
| `18ce05f1c` | Manual screenshots retaken (65 new, 95 legacy removed) |
| `42c1b21e0` | known-issues: defects found while retaking screenshots |

tttrlib `c9ed3b305`: board entry T-20261006-PAGEOBJ (done). Still unpushed from
earlier: emtk `62c7d5f` (line-drawing perf; `pixi.lock` must be re-pinned after
push), chimol `9425146` -- push only with the owner's approval.

## Open front, in order

1. **View-scheme authority (owner decision pending).** `test/test_ui_schemas.py`
   fails ~102 specs (71 already at `3b4f8b6db`). The scheme is generated from the
   Qt loader's section dataclasses (`chisurf/core/dataspec/__init__.py`,
   `schema.py`); emtk's `view_form` accepts more: section types `row` (47 specs),
   `progress` (10), `parameter_table` (6) and window/dock keys `name`, `dock`,
   `window`, `tab`, `page`, `panels`, top-level `description`; 20 specs do not
   load in the Qt loader at all; 35 failing specs are ndxplorer's. Recommended to
   the owner: emtk publishes its dialect (types + keys) and the generator merges
   it with the loader's. Re-derive the list: `pytest test/test_ui_schemas.py -q`,
   then histogram the "was unexpected" / "is not one of" lines. Trap: do **not**
   add keys to the scheme only -- `test_every_declared_field_is_in_the_scheme`
   requires scheme == dataclass fields (that is what `c1a7b80d3` fixed).
2. **34 legacy manual screenshots remain** (`kind: legacy screenshot` in
   `docs/references/figures.yaml`). Each has its reason in
   `okf/validation/manual-screenshots/{fcs,anisotropy,general,fitting}.json`
   (`not_replaced`): data not in the repo (A568, DNA, live-cell, HEK293T,
   A488+eGFP joint), spreadsheets, external plots. rId127/138/139 (global-fit
   editor) were blocked by the editor bug fixed in `1182fe7ea` -- they can be
   retaken now with `docs/guides/screenshots/manual_anisotropy.py` /
   `manual_fcs.py`. Retake pattern: script function -> `docs/manual/figures/`,
   register entry with recipe, re-record the page's review hash
   (`chisurf.plugins.core.help.api.review`), `python build_tools/docs/make_registers.py`.
   Trap: when rewriting a page body, do not cut at the first occurrence of its
   opening sentence -- it is also the front-matter `description`; three pages
   lost their front matter that way (all repaired).
3. **Figure register: 137 unrecorded** (was 8) since `make_registers.py` reads
   MyST `{image}` blocks; nearly all are guide figures made by
   `docs/guides/screenshots/*.py` -- grep the PNG name in those scripts to get
   `origin`, add `kind`/`recipe` in `figures.yaml`. Ratchet:
   `chisurf/plugins/core/help/test/test_doc_registers.py::test_every_image_used_is_registered`.
4. **Defects in known-issues (2026-10-06 section)**: global fit after a run
   (members not redrawn, Info chi2r exactly 1.0000 -- check it evaluates the
   windows' fit objects), Parse-Model link menu lists ~150 parameters, FCS hub
   ms/s lag units, Confocor3 single-channel loading, Global View Load needs the
   server, python-docx missing in the `arm64` env (save stops at the report),
   guide 10 stale menu path.
5. **GUI items** -- see the fit-window concept list: old projects' saved plot
   settings only tested for LinePlot/ProteinMC; FitInfo takes only local file
   drops; emtk `view_form` collapses a `weight: 0` info leaf in an `n_col` panel
   (fix in emtk with a test); Figure 24 is now real (`manual_donor_reference.png`).

## Known pre-existing red tests (not from this work)

`test_plots_no_orphan_modules`, `test_prd_mentions` (stale `core_fit.py`
allow-list entry), `test_settings_feature_parity[check]`, the docs crosslink/OKF
front-matter failures for guides 87/88/94/97/98 and two development pages,
`test_fit_presentation_contract.py` exit crash, and the order-dependent set in
the fit-window concept item 6. A/B any new failure against a clean worktree
(`git worktree add --detach <dir> HEAD`, absolute `PYTHONPATH` to
`/Users/tpeulen/dev/chisurf/modules/...`) before blaming a change.

## Environment notes

`arm64` conda env; GUI tests need `QT_QPA_PLATFORM=offscreen` and
`PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:."`.
Screenshot scripts must import `test.gui.fit_window_page_probe` before chisurf
(the stdlib `test` package shadows the repo's otherwise) and print with
`flush=True` before `os._exit`. Shared tree: commit only your hunks through a
temp `GIT_INDEX_FILE`, then `git reset -q -- <paths>` to resync the real index.
