---
type: Reference
title: UI terminology glossary (canonical labels)
description: The canonical, preferred spelling for each recurring user-facing concept across ChiSurf's tools, plus the rejected variants — the source-language authority for the translation kit and for harmonising interfaces.
resource: chisurf/gui/i18n/
tags: [ui, i18n, terminology, harmonisation, labels, glossary]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

ChiSurf grew a large tool ecosystem in which the *same* concept is often labelled
differently from one tool to the next ("Micro time" vs "Microtime" vs "TAC";
"Detector" vs "Channel"; a dozen spellings of the file-open button). This concept
is the **single canonical vocabulary**: for each recurring user-facing concept it
records the one preferred label, the variants it replaces, and why.

It serves two jobs at once:

1. **Harmonisation** — new and edited UI text (labels, titles, tooltips) should
   use the canonical term so the interface reads as one coherent application.
2. **Translation source** — English is the canonical source language for the
   translation kit (see [/subsystems/i18n.md](/subsystems/i18n.md)). Every source
   string a translator sees comes from these labels, so canonicalising *before*
   translating avoids near-duplicate catalogue entries. Canonicalise first, then
   extract with `pixi run i18n-extract`.

The glossary is the *target*. Where the current code still disagrees, that is
tracked in the [cleanup backlog](/specs/assessment.md), not silently "done".

# Canonical terms

| Concept | Canonical label | Rejected variants | Notes |
|---|---|---|---|
| Photon nanotime within the excitation period | **Micro-time** | Microtime, Micro time, micro-time (mid-label), TAC | Hyphenated, first word capitalised at label start. "TAC" is hardware jargon — allowed only in explanatory parentheses, e.g. "micro-time (TAC) bins". |
| Photon arrival clock across the experiment | **Macro-time** | Macrotime, Macro time | Parallels Micro-time. |
| The photon-nanotime histogram (TCSPC output) | **Decay histogram** | Decay, Histogram, decay histograms | Use the two-word form for the object; "decay" alone is fine as an adjective ("decay axis"). |
| A configured physical measurement setup / detection arrangement bound to an experiment | **Detector** | — | Distinct from *Channel* (below). Used as the experiment view-spec section title. |
| A routing / detection channel index inside a TTTR stream | **Channel** | — | A real, separate concept from *Detector* — a detector setup may expose several routing channels. Do **not** merge the two terms; keep "Channel" for TTTR routing indices and "Detector" for the setup entry. |
| Bring a data file into a tool | **Load** | load, LoadModelFile, "Load … File" | Verb for pulling *data* into the active tool. |
| Open a folder, editor, window or help resource | **Open** | — | Distinct from *Load*: "Open settings folder", "Open Help". Keep the Load/Open split — it is meaningful, not an inconsistency. |
| Add a new item to a managed list/group | **Add** | add, "+" (bare) | The `add_label` default; use "Add <thing>" for clarity where space allows. |
| The instrument response function | **IRF** | irf, Irf | Acronym, all caps. |
| Correction factor gₚ/gₛ | **G-factor** | g factor, gfactor | Hyphenated. |

# Style rules (labels & titles)

- Keep labels **short**; put detail in the tooltip (`description`) — see
  [/architecture/gui-layout.md](/architecture/gui-layout.md) and the
  "short labels, tooltips" practice.
- Sentence case for section titles and field labels ("Channel definition", not
  "Channel Definition") unless a term is a proper noun/acronym.
- Emoji action glyphs come from the shared `Glyphs` set and the canonical action
  registry `TOOL_ACTIONS` (`chisurf/gui/widgets/tool_buttons.py`) — reuse those
  rather than hand-picking a new emoji for an existing action.

# Scope of the current harmonisation pass

Applied now (data-driven layer — `*.view.json` / `manifest.json`, the seams that
localise through [/subsystems/i18n.md](/subsystems/i18n.md)):

- Micro-time title outliers folded to the canonical form (audifier panel title;
  the "Mean Micro-Time" image dock title).

Deliberately **not** changed (and why):

- `Channel` → `Detector`: rejected — they are different concepts (see table).
- `Load` → `Open`: rejected — the split is meaningful.
- `display_name` / `categories` in manifests: these double as menu-path / identity
  keys (`chisurf/core/plugin/registry.py`), so they stay canonical English and are
  localised at the navigation-render seam, not at parse — a tracked follow-up.

Deferred to the [cleanup backlog](/specs/assessment.md):

- Hand-built `.ui` files still use "Micro time" (two words), "TAC", "Channel
  Select", and several file-open spellings/typos ("resoltion", "distirbution").
  These converge to the canonical terms when each `.ui` is migrated to AutoForm
  or edited.
