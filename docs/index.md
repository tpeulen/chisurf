---
okf_version: "0.2"
type: Index
title: ChiSurf documentation
description: ChiSurf is an interactive global-analysis platform for time-resolved and single-molecule fluorescence data — time-correlated single-photon counting (TCSPC), fluorescence correlation spectroscopy (FCS), and single-molecule FRET (smFRET).
tags: [fitting, global-analysis, photons, tcspc, correlation, fcs, fret, smfret]
---

# ChiSurf documentation

**ChiSurf** is an interactive global-analysis platform for time-resolved and
single-molecule fluorescence data — time-correlated single-photon counting
(TCSPC), fluorescence correlation spectroscopy (FCS), and single-molecule FRET
(smFRET). This documentation is organized in four layers:

* **Getting started** — install ChiSurf, launch it, and run a first analysis.
* **Fundamentals** — the photophysics, instrumentation and counting statistics
  the analyses assume, independent of any one method.
* **Concepts** — the theory behind each technique (what the models mean and why),
  self-contained and cited.
* **Guides** — step-by-step, *how to do it in ChiSurf*, with real screenshots of
  the actual user interface, cross-linked to the matching concept.
* **Reference** — file formats, settings, the full plugin catalogue (every plugin
  and every parameter), and the Python API.
* **Literature** — every work the documentation cites, each linking through to
  the publisher's page.

Every page also carries a short machine-readable header naming what kind of
page it is and what it is about, so the built-in assistant can find the right
one before it answers. The header is metadata: it never appears in the rendered
page. See [Asking the documentation](guides/70_ask_the_documentation.md).

```{toctree}
:maxdepth: 2
:caption: Getting started

getting_started/index
```

```{toctree}
:maxdepth: 2
:caption: Fundamentals (photophysics)

fundamentals/index
```

```{toctree}
:maxdepth: 2
:caption: Concepts (theory)

concepts/index
```

```{toctree}
:maxdepth: 2
:caption: Guides (how-to in ChiSurf)

guides/index
```

```{toctree}
:maxdepth: 2
:caption: Fitting interface & worked examples

manual/index
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/index
```

```{toctree}
:maxdepth: 1
:caption: Literature

references/index
```

```{toctree}
:maxdepth: 1
:caption: Development

development/index
```

## Indices and tables

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
