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

## The licence boundary — settled 2026-08-24

**`docs/` is now CC BY-SA 4.0** (the code stays GPL-3.0-or-later; see
`docs/licensing.md`). That was done *because* of this mining effort, and it
changes the answer this concept originally gave.

- **Wikipedia prose may now be used**, with attribution and a note of changes,
  because CC BY-SA 4.0 into CC BY-SA 4.0 is exactly what share-alike is for. The
  page records the source in a `sources:` front-matter block — per page, since a
  blanket note in `licensing.md` does not discharge attribution.
- **Bibliographic data was never the problem.** Authors, title, journal, year,
  DOI are facts; harvesting them needed no licence change and remains the main
  use of the dump.
- **A harvested DOI is still verified against Crossref before it lands.**
  Wikipedia citation templates carry typos and mismatched identifiers, and
  `bibliography.yaml` says outright that a wrong DOI is worse than no DOI. This
  has nothing to do with licensing and did not change.
- **What is still forbidden** is unchanged and worth restating, because the
  relicence makes it easy to assume everything is now open: CC NC/ND material,
  GPL-only prose, and copyrighted journal text are all still out. A compatible
  *code* licence does not make prose usable here.

**The editorial rule outlived the legal one.** Importing is now permitted and is
still usually wrong. These pages are terse, use the symbols the code uses, carry
no glossaries, and tie each claim to something ChiSurf computes; Wikipedia's
prose has none of those properties, and a page assembled from it reads like it.
The first pass wrote everything fresh while believing it had to, and the result
was better than an import would have been — the gaps it found (see below) were
found precisely because writing a section forces you to notice what is missing
from it. Treat the licence as removing an obstacle to *derivation*, not as an
invitation to paste.

## The corpus

| Item | Value |
|---|---|
| Dump | `enwiki-20260801-pages-articles-multistream.xml.bz2` (26.67 GB) |
| Index | `…-multistream-index.txt.bz2` (284 MB) → 25,792,234 articles |
| Location | `/Volumes/SD1TB/wikipedia/enwiki-20260801/` |
| State | **complete** — 26,668,484,995 bytes, size-exact; tail and mid-file extraction verified |
| Tools | `/Volumes/SD1TB/wikipedia/tools/` |

**Multistream is the format that matters.** The dump is a concatenation of
~258,000 independent bz2 blocks of ~100 articles each, and the index gives the
byte offset of the block holding any page. One article therefore costs one
range read plus one small decompression — and because the offsets are absolute,
`extract.py` serves them over HTTP `Range` when the local file is still
downloading. The extraction did not wait for the 26.67 GB to land.

**The dump is complete, and acquiring it was not a free action.** It took
about fourteen hours across nine interrupted runs, saturated a domestic uplink,
and contributed to the machine becoming unusable for its owner — another session
swept the tree and asked for it to stop, correctly. It was finished only after
being throttled to `--limit-rate=1m` at `nice -n 19`, which cost little in wall
time and should be the default for any future bulk fetch here. **Do not
re-download it to get a newer dump while anyone is working on the machine**, and
prefer a targeted range-read over a full refresh: `extract.py` can pull single
articles from a *remote* dump without downloading it at all.

Verified on completion by size (exact) plus decompression of the **final block
in the file** — bz2 blocks are CRC-checked, so extracting the last article
(`Draft:Gertrude Massey`, offset 26668473302) proves the tail survived the
interruptions. A full SHA-1 over 26.67 GB was deliberately *not* run: it is
~26 GB of reads on a machine that had just been complained about, and the size
match plus a tail CRC is strong evidence for a `wget -c` resume. Run
`shasum -a 1` against the published checksum in `dumpstatus.json` if certainty
is ever needed.

`fetch_dump.sh` was rewritten after that incident and is now safe for anyone to
stop: it runs `nice -n 19` under `--limit-rate=1m` (about a quarter of the
uplink), writes its pid to `fetch.pid`, and logs `stop me with: kill <pid>` as
its first line. Killing *either* process ends the run.

The bug worth remembering, because it is easy to write again in any supervisor
loop: the original could not distinguish **"the mirror stalled"** from **"a
human killed my child"**, and restarted `wget` in both cases — so sweeping the
machine could not put it down, and it looked like it was evading the sweep. The
discriminator is the exit status: `wget` exits `>=128` only when a signal killed
it, so signal means stop and an error code means retry. Traps on TERM/INT/HUP
kill the child and exit.

This does not block mining: `extract.py` range-reads any article whose bytes
have not landed, which is how the first pass ran with 4 GB on disk.

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

## Second pass (2026-08-25) — what folding prose in is actually worth

The relicence made importing legal, so the obvious next step was to fold
Wikipedia's fluorescence content into the pages. **The yield is much lower than
that premise assumes, and the reason is worth recording so nobody repeats the
exercise hoping for more.**

On the topics ChiSurf documents, *these pages are already deeper than the
articles*. Measured, not guessed:

- `Solvatochromism` has **no section headings at all** — no structure to derive
  from — while `solvent_and_environment.md` already derives Lippert-Mataga,
  treats specific effects, and handles relaxation on the lifetime timescale.
- `Excimer` is mostly excimer *lasers* and arene photochemistry; one short
  section touches fluorescence.
- `Fluorescence anisotropy` has four sections against a page here with nine.

Two traps in judging a gap:

1. **A vocabulary miss is not a content gap.** Grepping the docs for "exciplex"
   returned zero and looked like a hole. The physics was fully covered under
   *stacking* and *excimer* — static quenching from ground-state stacking,
   intermittent stacking blinks, NADH and FAD — and `absorption_and_emission.md`
   already names excimer emission as a cause of a broad structureless shifted
   band. Adding an "exciplex" section would have been a glossary entry, which
   the docs' style rejects. Check the *phenomenon*, not the word.
2. **The article's citations outvalue its prose.** The one genuine gap found
   this pass came from a reference list, not from body text: the empirical
   polarity scales. The page taught the continuum model and called its
   deviations "the interesting part" without giving the framework that
   quantifies them — Kamlet-Taft's pi*/alpha/beta and Reichardt's E_T(30).

So the working method is unchanged from the first pass and is not a licence
question at all: **mine the citations, follow them to the primary literature,
write the page here.** Import prose only where an article is genuinely stronger
than what exists, which on this subject matter has not yet happened once.

## Re-running it

```bash
python3 tools/harvest_cites.py          # articles/*.wiki -> tools/works.json
# then rank against the existing bibliography, verify via Crossref, and insert
```

`extract.py` needs `offsets.bin` (built once from `index.txt`); `build_offsets()`
regenerates it. The seed list is `tools/seeds.txt` — extend it rather than
widening the regex.

## Second tranche (2026-08-25) — recorded late, third pass (2026-08-31) — the harvest saturates

The seeds went from 107 to 143 titles (super-resolution, microscopy, detector
and statistics families), 33 more articles were extracted (128 on disk; the
misses are redirects), and the harvest was re-run at the lower threshold:
347 candidates → **113 Crossref-verified works**. Sixteen resolution-family
entries landed with a super-resolution concept page the same morning, and with
them the two guardrails items 3 and 4 below asked for: a renderer for the
`sources:` front-matter block (`docs/_ext/source_attribution.py`, tested in
`test/test_docs_sources.py`) and `test/test_docs_links.py`, which fails on any
`{cite}` key that does not resolve. None of that was written down here until
now — the session that did it stopped before updating this page, which is the
same failure mode the fetch incident above records: **the state file is not
optional**.

The third pass read the 97 verified works the resolution tranche had left, and
the finding is the headline: **the fluorescence-adjacent harvest is
saturated.** One family still carried content value — two-photon excitation,
which these docs covered in exactly one sentence — and it is now a subsection
of `docs/fundamentals/instrumentation.md` (Göppert-Mayer's prediction, the
Denk/Strickler/Webb instrument, Xu's 690–1050 nm cross-section tables in GM
units, Helmchen–Denk on penetration as a scattering budget), citing four newly
landed entries. It is also the **first page to carry a `sources:` block**,
crediting the two Wikipedia articles it derives from — the convention from the
relicence now has a user, a renderer, and a passing test. Separately,
`kondo2019` landed (verified outside the dump pool): the LHCSR1 single-molecule
application the `flc_2d` plugin's original MATLAB code was written for, cited
from the 2D-FLCS page.

The rest of the 97 is real bibliography for some other project: the EM
algorithm's variants, Fisher 1922 and Schottky 1918, condensate and quantum-well
physics, speech-recognition HMM engineering. No page here needs them. Future
bibliography growth should be **page-driven** — a page needs a source, the dump
fetches it — not dump-driven: re-running the ranker again would not find
anything a page wants. The dump's standing use is the last item below.

## Where to pick this up

**Latest (2026-09-23, round 3) — every guide has a real screenshot; citing corrects.**
1. **Measure coverage again before writing**: guides without a screenshot
   (compare `figures/*.png` referenced by a guide against the grab modules in
   `docs/guides/screenshots/` + `make_screenshots.py`), concept pages by
   `{cite}` count. After round 3 the lowest pages carry ≥2 citations; the next
   thin tier (3–5) is the front.
2. **Citing a page is an audit of it**: 12 of 14 pages had a wrong claim,
   found only because each citation forced re-reading against the code.
3. **Screenshot agents stall on hung GUI scripts**: run every grab as a
   subprocess with a hard timeout (macOS has no `timeout`); the three that
   stalled all resumed from their `progress.md`.
4. **Grab traps**: never let an agent run the acquisition tool against the
   default output folder (it wrote m000–m043.spc into ~/chisurf/acquisition);
   the flow grab would overwrite the intended-result figure.

**Earlier (2026-09-23, round 2) — guides 72–82 done; ports lose help silently.**
Guides 76–82 + concepts `hydrodynamics`, `dye_quenching`, `structure_trajectories`
added 45 entries (312 total). Open, in order:

1. **A help file that nothing draws is invisible to the seam test.**
   `test_plugin_help_guide_seam` passes when `help.md`/`guide.json` exist;
   eight tools had both and no `?`/Guide button because the tool never called
   `ensure_help_toolbar` / `attach_help_and_guide`. Check by constructing the
   widget and looking for the buttons (`findChildren(QAbstractButton)` texts
   "Guide", "?"), not by the file. A guard for this would pay.
2. **Ports drop references.** The sweep (all deleted `.ui` + GUI diffs,
   2026-09-23) is complete for citations and cautions; long uncited help prose
   in Python was not searched exhaustively.
3. **Undocumented plugins left** are admin/core tools and `menu_hidden` ones
   with no hub (Synthetic Decay Generator is documented but unreachable).
4. **QuEst import blocker** and LLTF's mis-specified component test are the
   highest-value code fixes the docs exposed (known-issues, second 09-23 section).

**Earlier (2026-09-23) — page-driven harvest works; plugin coverage is the front.**
Guides 72–75 + concepts `point_spread_function`, `intensity_traces` drew 40
Crossref-verified entries from dump citations (commit `226b7f845`). Open, in order:

1. **Undocumented plugins.** Re-measure with the loop that found them: for each
   `chisurf/plugins/**/manifest.json`, grep its directory name in
   `docs/guides docs/concepts` — 0 hits = no page. *Trap:* the name test misses
   pages that use the menu label only, so check `display_name` too before writing.
   Menu-visible and still undocumented: none of the five taken; the rest
   (`traj/*`, `spot_finder`, `proteinmc`, `mfd_prepare`, core admin tools) are
   `menu_hidden` — document only if they are reachable from a hub.
2. **Writing a page measures the tool.** All four passes found real defects
   (~30, in known-issues 2026-09-23). The highest-value ones are blockers, not
   cosmetics: FCS Channel Definitions → correlator disconnected; TTTR Correlate
   error bars inverted; PSF calculator does not open on the emtk backend;
   tttrlib radial PSF E_z 2× (fix upstream). Fix these before more docs.
3. **Docs that quote numbers must re-derive them.** The PSF help's widths were
   5–40 % off because they were typed, not measured; `PSFModel` scripts in the
   guide reproduce the table.

Done since this page was written, in order: the seed extension and second
harvest (item 1, item 2), the `sources:` renderer and its test (item 3), the
cross-reference guardrail (item 4). What remains:

1. **The dump is a general resource, not a bibliography tool.** It is equally
   the way to check a claim in a concept page without a network round-trip.
   `extract.py` + `offsets.bin` serve any of the 25.8 M articles in one range
   read; extend `tools/seeds.txt` and re-extract when a new page needs its
   sources.

## Hunt mode (2026-08-31) — FRAP

One more mode the saturation finding does not cover: hunt for *implementations
without pages*, then take the method's article from the dump. `test_frap.py`
gave FRAP away — a real rFRAP implementation in
`chisurf/core/fluorescence/imaging/frap.py` and not one mention anywhere in
`docs/`. New page `docs/concepts/frap.md` (the first `sources:`-carrying
concept page), three verified entries (Axelrod 1976, Soumpasis 1983, Sprague
2004 — pulled from the dump's article and Crossref-checked), toctree entry.
More leads in the same vein, unexamined: whether every plugin tool has a page.

**Fourth tranche (2026-08-31) — saturation confirmed, enrichment pass.**

The 'every plugin tool has a page' lead was examined exhaustively. Every
remaining implementation without a concept page falls into one of two
categories: (a) it is a tool or utility, not a concept (spot_finder,
clsm_generator, img_calibration, img_pixel_intensity, trajectory tools),
or (b) it is already covered within an existing concept page (N&B in
pch_fida.md, VV/VH and G-factor in anisotropy.md, Region MLE in
tcspc_lifetime.md, FLCS and 2D-FLCS in filtered_fcs.md). No more FRAP-scale
gaps exist in the plugin-to-concept-page mapping for core fluorescence
methods.

Two enrichment entries landed from already-extracted articles:

| Entry | Source article | Verified | Landed in |
|---|---|---|---|
| sheppard1977 (confocal image formation theory) | Confocal microscopy | Crossref | fcs_correlation.md |
| shaw1991 (PSF measurement from beads for 3D deconvolution) | Point spread function | Crossref | deconvolution.md |

The fluorescence-adjacent dump harvest remains saturated. Future
bibliography growth continues to be page-driven: a page needs a source,
the dump fetches it.

**Fifth tranche (2026-08-31) — MD trajectory domain, saturation confirmed.**

The recorded lead — molecular dynamics trajectory methods from the traj/
plugin family — was examined. Seven Wikipedia articles were extracted
(Molecular dynamics, Kabsch algorithm, Root-mean-square deviation of atomic
positions, Distance geometry, Protein dynamics, Rotational diffusion,
Time-resolved fluorescence spectroscopy), yielding 173 distinct works (145
with DOIs). After strict filtering for relevance to ChiSurf's trajectory
and superposition code, **2 entries landed**, both Crossref-verified:

| Entry | Source article | Verified | Landed in |
|---|---|---|---|
| kabsch1976 (SVD-based rigid superposition) | Kabsch algorithm, RMSD | Crossref | 44_molecular_viewer.md |
| kabsch1978 (handedness correction for reflections) | Kabsch algorithm | Crossref | 44_molecular_viewer.md |

The Wikipedia Molecular dynamics article carries 103 cited works, but nearly
all are general computational chemistry and biophysics — force fields,
integrators, enhanced sampling — with no connection to fluorescence methods.
The two Kabsch papers are the only entries the trajectory domain has to offer
that ChiSurf's documentation needs. The finding is definitive: the dump has
no more fluorescence-relevant citations to give, even in adjacent domains.

One Wikipedia DOI typo was caught and corrected: the Molecular dynamics
article lists `10.1002/jcc.20077` for Coutsias et al. 2004 ("Using
quaternions to calculate RMSD"), but Crossref resolves that to a CHARMM
force-field paper. The correct DOI is `10.1002/jcc.20110`.

**Where to pick this up.** The dump harvest is exhausted. No domain tranche
will yield new fluorescence-relevant entries — the MD domain was the last
candidate and returned 2/173. All future bibliography growth is page-driven:
a page needs a source, the dump fetches it. The next useful step is a re-index
against a newer dump if one is acquired, or extending `tools/seeds.txt` for
one-off page-driven lookups.

**Sixth tranche (2026-08-31) — idle, saturation confirmed.** Examined all
seven uncited concept pages, checked for implementation-without-page gaps
(beyond the FRAP/pda2c/mfd_fitting etc. already covered), verified that all
already-extracted articles' remaining citations are non-fluorescence (EM
algorithm variants, Fisher/Schottky historical, quantum-well physics), and
checked whether general-statistics pages (least squares, bootstrap, MLE)
have uncited mentions in docs — they don't, or the mentions are in pages that
already carry citations. The dump has nothing left to give. No commit.

**Seventh tranche (2026-08-31) — page-driven: global analysis had a
hand-rolled reference list and one wrong DOI.**

Saturation of the *dump* does not mean saturation of the *docs*. The lead came
from counting `{cite}` roles per page: seven concept pages have none, and
`docs/concepts/global_analysis.md` — the page for what ChiSurf is actually
built around — had a plain `## References` list of three works that the
bibliography had never heard of. A reference list a page keeps to itself is
invisible to the Literature index, to the help browser, and to the guardrail
that checks whether a cited work exists.

Crossref-verifying those three caught a defect: the page gave
`10.1080/10739148508543581` for Beechem, Ameloot & Brand (1985), which resolves
to *Time Correlated Single-Photon Counting Using Laser Excitation* by Phillips
et al. — a different paper in the same journal. The correct DOI is
`10.1080/10739148508543585` (last digit 5). This is the "the DOI is bad, not
the paper" case, found in our own prose rather than in Wikipedia's.

Four entries landed, all Crossref-verified, under a new
`# ── Global and target analysis ──` section:

| Entry | Verified | Cited from |
|---|---|---|
| knutson1983 (the original global fit of a decay surface) | Crossref | global_analysis.md |
| beechem1985 (global *vs* target analysis; DOI corrected) | Crossref | global_analysis.md |
| ameloot1986 (identifiability of rate constants from a decay surface) | Crossref | global_analysis.md |
| beechem1992 (the method review — what to link and what not to) | Crossref | global_analysis.md |

The page also gained a *Linking is not target analysis either* subsection —
linking shares a fitted number, target analysis fits the mechanism that
produces it — and a house-style **See also** block (concepts, guide,
`{src}` implementation links, literature) replacing the hand-rolled list.

Also repaired here: `docs/references/index.md` was stale. The fifth tranche
committed `kabsch1976`/`kabsch1978` into `bibliography.yaml` without
regenerating the index, so those two works existed in the source of truth and
appeared nowhere in the Literature page. The regeneration in this tranche went
212 → 218 works: four mine, two owed.

**Where to pick this up.** The dump is still saturated; the *pages* are not.
The lead that worked here generalises and is cheap to re-run:

    for f in docs/concepts/*.md docs/fundamentals/*.md; do
      echo "$(grep -o '{cite}' "$f" | wc -l) $f"; done | sort -n

Six uncited concept pages remain: `drift_correction`, `live_streaming_analysis`
(which has its own hand-rolled *Further reading* with two DOIs — the same
pattern, ready to wire up), `mfd_fitting`, `pda2c`, `photon_container`,
`region_properties`. Take `live_streaming_analysis` next: its two DOIs are
already written down, so the tranche is verify-and-wire rather than hunt. Note
that some of the six are genuinely citation-free by nature (`photon_container`
describes a file format, `region_properties` a geometry API) — check that a
page *wants* literature before manufacturing some for it.

**Eighth tranche (2026-08-31) — the dump is not only a citation source.**

The saturation finding above is about *citations*: no fluorescence-adjacent
article had verified DOIs left that a page wanted. It was read too broadly. The
dump is also a **knowledge** source, and that pool is not saturated at all,
because ChiSurf's own methods sit on general mathematics whose articles nobody
had touched.

`docs/concepts/factor_graphs.md` was written from the module docstring of
`chisurf/core/fitting/factorgraph.py` and was correct but thin: it used
"moralise", "triangulate", "junction tree" and "treewidth" as terms without
defining any of them. Eleven articles were extracted (Factor graph, Graphical
model, Belief propagation, Junction tree algorithm, Treewidth, Tree
decomposition, Bayesian network, Markov random field, Chordal graph, Variable
elimination, Conditional independence) yielding 107 distinct DOIs; five landed,
all Crossref-verified: `loeliger2004`, `halin1976`, `robertson1984`,
`bodlaender1996`, `arnborg1989`.

Three facts changed what the page says rather than merely decorating it:

- **treewidth 1 means the graph is a tree or forest, exactly.** The page's
  worked example measures treewidth 1 and previously just noted it was small.
  It is small *because* the moralised graph of a global fit is a star, verified
  directly: 4 variables, 3 edges, one component, every maximal clique an edge.
  That is the structural reason global analysis scales with dataset count.
- **chordality is what makes clique enumeration cheap** — polynomial on a
  chordal graph, NP-complete in general. That is why the triangulation step
  exists at all, which the page could not previously explain.
- **bounded treewidth is why the number is worth reporting**, not just an
  implementation statistic.

**Where to pick this up.** The lead is *general mathematics under a ChiSurf
method*, and it is the first one in several tranches that was not exhausted on
contact. Candidates: the samplers (`ensemble samplers`, slice sampling,
Rao-Blackwellisation — `parameter_uncertainty.md` uses "collapsed" and
"Rao-Blackwellised" undefined), maximum entropy (`maximum_entropy.md`), the
hidden-Markov pages (forward-backward, Baum-Welch, Viterbi), and the graph layer
in `chisurf/core/graph`. The test is the same one that worked here: find a term
the docs *use* but never *define*, and check whether Wikipedia defines it in a
way that changes what the page can say.

Note the earlier per-page citation count is still the right first measurement,
but it is the wrong *only* measurement: `factor_graphs.md` already had three
citations and was still the thinnest page in the docs on its own subject.
