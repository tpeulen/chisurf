---
type: PRD
prd: "63"
title: "PRD-63: Internationalisation & UI-language harmonisation"
description: Add a translation kit (extract → catalogue → runtime switch) that localizes the data-driven view.json/manifest and .ui UI from a single Qt-free seam, seed a German catalogue, and use the same funnel to harmonise inconsistent UI terminology against a canonical glossary.
status: in-progress
phase: "unassigned"
resource: chisurf/core/i18n.py
tags: [prd, i18n, translation, localization, autoform, harmonisation]
timestamp: '2026-07-24T00:00:00Z'
---

# Summary

ChiSurf had no i18n layer: every label was hardcoded English across 85
`view.json`, 98 `manifest.json`, 43 `.ui` forms, and ~4000 imperative call
sites, and the same concept was often labelled differently between tools. This
PRD adds a reusable translation kit and localizes the modern data-driven UI from
one seam, while introducing a canonical UI vocabulary that doubles as the
translation source and as the harmonisation target.

Implementation and architecture live in
[/subsystems/i18n.md](/subsystems/i18n.md); the canonical vocabulary is the
[UI glossary](/references/ui-glossary.md).

# Motivation

- **Reach.** ChiSurf targets an international audience (e.g. the NFDI4Chem German
  fluorescence-databank context); a translatable UI is a prerequisite.
- **Leverage.** The data-driven AutoForm/manifest architecture funnels almost all
  modern UI text through two parse functions — localizing there covers the whole
  ecosystem cheaply, and `.ui` strings come for free via `QTranslator`.
- **Harmonisation.** Building the source-string catalogue forces a single
  canonical term per concept, fixing "Micro time / Microtime / TAC",
  "Detector / Channel", and file-open label drift.

# Approach

1. **Qt-free core seam** `core/i18n.py` (`tr`, identity default, swappable
   backend, `get/set_locale`) so `core`/server stay toolkit-free.
2. **GUI bootstrap** `gui/i18n.py:install_translation()` in `get_app()` — binds
   `QCoreApplication.translate` and installs the `.qm` before any window builds.
3. **Central seams** localize view.json (`dataspec._section_from_dict`), RPC
   forms (`dataspec/rpc.py`), and manifests (`manifest.from_dict`); tooltip/status
   funnels catch static imperative strings. `.ui` is covered for free.
4. **Kit** `build_tools/i18n/extract_strings.py` + `pixi run i18n-extract` /
   `i18n-compile`; `en`/`de` `.ts`/`.qm` catalogues (German seed).
5. **Glossary** `references/ui-glossary.md` + canonicalise the data-driven label
   outliers.

# Definition of Done

- [x] Qt-free `core/i18n.py` seam (identity default; headless test).
- [x] `QTranslator` bootstrap + `gui.language` locale plumbing.
- [x] view.json / manifest / RPC / tooltip / status seams localized.
- [x] Extractor + `en`/`de` catalogues + compiled `.qm`; `.qm/.ts` packaged.
- [x] UI glossary + micro-time label harmonisation in the data-driven layer.
- [x] Headless tests (`test/test_i18n.py`) + full view.json parse regression.
- [x] `pixi.toml` `i18n-extract`/`i18n-compile` tasks + `gui.language` YAML default.
- [x] **Language selector in Settings** — `gui.language` renders as an
      endonym combo (discovered from shipped `.qm`), stores the locale code,
      persists via `set_language`, and switches live via
      `gui/i18n.py:apply_language()`; incidentally revived the theme combo by
      fixing `SettingsItemDelegate._get_setting_path` for value-column indices.
      Guarded by `test/gui/test_language_selector.py`.
- [x] **German catalogue ~90% complete** — 2218/2456 messages finished
      (UI chrome, view.json/manifest display-names + tooltips, and the long
      markdown help panels); the ~238 remaining are non-translatable by design
      (Qt signal/slot names, shortcuts, math symbols, identifiers, URLs) and fall
      back to source. Filled non-destructively; `de.qm` recompiled.
- [x] **Second locale shipped — French (`fr`)** as a generalisation proof: the
      selector now offers English / Deutsch / Français, and the app renders French
      live. `chisurf_fr.ts` derived from the context-complete `de.ts`; UI chrome
      translated (~285 strings), `fr` registered in the extractor `DEFAULT_LOCALES`
      and `i18n-compile`, guarded by `test_language_selector`. Remaining French
      strings fall back to English (per-string Qt fallback).
- [ ] Follow-ups: imperative `setText`/`QMessageBox` wrapping (phased), menu-path
      `display_name`/`categories` localization at the nav seam, `.ui` terminology
      convergence, completing the French catalogue, and further locales.

# Non-goals (this pass)

Wrapping the ~4000 imperative plugin strings, and translating menu-path identity
keys — both tracked in [/specs/assessment.md](/specs/assessment.md).
