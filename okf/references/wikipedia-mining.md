---
type: Reference
title: Wikipedia mining — citation harvest for the docs corpus
description: A local English Wikipedia dump used as a citation index for docs/references/bibliography.yaml; what was harvested, the licence boundary that forbids prose reuse, and how to re-run the extraction.
tags: [reference, documentation, bibliography, citations]
timestamp: '2026-08-24T00:00:00Z'
---

# Wikipedia mining — citation harvest for the docs corpus

A full English Wikipedia dump is kept on external media and used as a **citation
index** for ChiSurf's documentation. It is not a prose source. This concept
records the licence boundary, what the first pass took, and how to re-run it.

## The licence boundary — read this before copying anything

Wikipedia text is **CC BY-SA 4.0**; ChiSurf is **GPL-3.0-or-later**. Folding
Wikipedia prose into `docs/` would drag an attribution-and-share-alike
obligation onto the documentation and force a per-page provenance trail that
nobody will maintain. So the rule is the same one
[quickfit3-mining.md](quickfit3-mining.md) already sets for GPL sources:

- **Bibliographic data is fact and is freely harvestable** — authors, title,
  journal, year, volume, pages, DOI. This is what the dump is *for*.
- **Prose, figures and tables are not taken.** Every sentence added to `docs/`
  in this pass was written for ChiSurf, in ChiSurf's voice, against the primary
  papers the citation harvest surfaced.
- **A harvested DOI is verified against Crossref before it lands.** Wikipedia
  citation templates carry typos and mismatched identifiers, and
  `bibliography.yaml` says outright that a wrong DOI is worse than no DOI.

## The corpus

| Item | Value |
|---|---|
| Dump | `enwiki-20260801-pages-articles-multistream.xml.bz2` (26.67 GB) |
| Index | `…-multistream-index.txt.bz2` (284 MB) → 25,792,234 articles |
| Location | `/Volumes/SD1TB/wikipedia/enwiki-20260801/` |
| Tools | `/Volumes/SD1TB/wikipedia/tools/` |

**Multistream is the format that matters.** The dump is a concatenation of
~258,000 independent bz2 blocks of ~100 articles each, and the index gives the
byte offset of the block holding any page. One article therefore costs one
range read plus one small decompression — and because the offsets are absolute,
`extract.py` serves them over HTTP `Range` when the local file is still
downloading. The extraction did not wait for the 26.67 GB to land.

**Do not fuzzy-grep the index.** Substring matching over 25.8 M titles is
useless — `kasha` matches *Kashani*, `palm` matches *Palm Sunday*, `fcs` matches
football divisions. A first pass returned 16,202 candidates that were mostly
noise. Exact-title lookup against a curated seed list is the working method;
word-boundary regex on the title field only is the discovery method.

## First pass (2026-08-24)

99 articles extracted from a 107-title seed list (the 6 misses are redirects,
not gaps) → 2,120 distinct cited works, 1,751 carrying a DOI → 138 candidates
not already in `bibliography.yaml` and cited by a *core-method* article → **41
added, every DOI Crossref-verified, every key cited by a page.**

Where they landed:

| Area | Added | Notable |
|---|---|---|
| FCS | 15 | Magde/Elson/Webb 1974; Meseth 1999 (two-component resolution limit); Hess & Webb 2002 (focal-volume artefacts) |
| Image correlation | 8 | Petersen 1993 (ICS); Digman 2005 (RICS); Digman 2008 (N&B) — the page had **zero** citations before |
| Hidden Markov | 5 | Baum 1970 (the original recursion); Ghahramani 1997 (factorial); Götz 2022 (blind benchmark) |
| Photophysics | 12 | Perrin 1934/1936 (ellipsoid rotation); Dexter 1953; IUPAC quantum-yield standards |
| Simulation | 1 | Börner 2018 (camera-based smFRET) |

Content gaps the harvest exposed, and which were filled in the same change:

- **`docs/concepts/image_correlation.md` cited nothing at all.** The method
  family had no attribution and no history.
- **Quantum yield had one thin paragraph** in
  `docs/fundamentals/lifetime_and_quantum_yield.md`, despite $Q_D$ setting
  $R_0$ and $Q_A/Q_D$ entering $\gamma$ *linearly*. Now carries the relative
  method, the $n^2$ term, inner-filter limits, and the quinine-standard warning.
- **`docs/concepts/anisotropy.md` assumed a sphere throughout.** A general rigid
  body has three diffusion coefficients and up to five exponentials, so a
  multi-exponential anisotropy decay is *not* evidence of two populations — a
  reading error the page previously invited.
- **The FCS two-component resolution limit was missing.** Two species need
  $\tau_D$ ratios of ~1.6 (≈ a factor 4 in mass) before a fit can see them.
- **PCH had no cumulant route**; HMM had no warning that dwell-time histograms
  cannot fix a connectivity.

## Re-running it

```bash
python3 tools/harvest_cites.py          # articles/*.wiki -> tools/works.json
# then rank against the existing bibliography, verify via Crossref, and insert
```

`extract.py` needs `offsets.bin` (built once from `index.txt`); `build_offsets()`
regenerates it. The seed list is `tools/seeds.txt` — extend it rather than
widening the regex.

## Where to pick this up

1. **The seed list is 107 titles and the fluorescence corpus is larger.** The
   obvious next tranche is the super-resolution and instrumentation families
   (STED/PALM/STORM, SPAD arrays, TIRF, light-sheet), none of which were seeded,
   plus the FCS variants ChiSurf lacks pages for — svFCS, TIR-FCS, SPIM-FCS.
   [quickfit3-mining.md](quickfit3-mining.md) already flags TIR-FCS and SPIM-FCS
   as clear gaps with ~70 models between them, so the two mining efforts point
   at the same hole from different sides.
2. **1,751 harvested DOIs were reduced to 138 candidates by requiring a
   core-method citer.** That filter is deliberately harsh and the discarded set
   was never read. Re-ranking with a lower threshold is cheap — `works.json`
   is on disk — and is the fastest route to a second tranche.
3. **Nothing checks that a `{cite}` key resolves.** The dangling-citation and
   footnote-definition audits in this pass were ad-hoc scripts, not tests. A
   guardrail in `test/` would stop a stale key reaching the built docs; today
   the only signal is a broken link in the rendered HTML.
4. **The dump is a general resource, not a bibliography tool.** It is equally
   the way to check a claim in a concept page without a network round-trip.
