---
type: Reference
title: Burst Variance Analysis (BVA) theory and chisurf mapping
description: The BVA statistic (per-burst std.dev. of sub-window FRET efficiency), the binomial shot-noise static line, and how the theory maps onto the chisurf/tttrlib implementation.
resource: chisurf/core/fluorescence/burst/bva.py
tags: [burst, smfret, dynamics, bva, proximity-ratio, shot-noise, tttrlib, torella]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

Internal knowledge-base note for **Burst Variance Analysis (BVA)**: the statistic,
its shot-noise reference, and the exact seams where it lives in this codebase.
The user-facing page is `docs/concepts/bva.md`; the workflow guide is
`docs/guides/08_burst_variance_analysis.md`. BVA is one of the burst-feature
methods alongside [FRET-2CDE](/references/crosstalk.md) and the burst-search
machinery.

# What BVA is

BVA (Torella et al. 2011) is a **model-free detector for sub-burst FRET
dynamics** in single-molecule confocal smFRET. It distinguishes a molecule whose
FRET efficiency is *constant* while it transits the confocal volume from one that
*interconverts* between states during the burst. The discriminating observable is
the variance of the apparent efficiency measured across short photon sub-windows
of a single burst: a static molecule varies only by shot noise, a dynamic one
adds excess variance.

# The statistic

Each burst (a photon stream while one molecule is in focus) is split into
consecutive **slices** of $n$ photons. For slice $i$ the proximity ratio /
apparent efficiency is

$$
E_i = \frac{n_A^{(i)}}{n_A^{(i)} + n_D^{(i)}} = \frac{n_A^{(i)}}{n}
$$

with $n_A^{(i)}$, $n_D^{(i)}$ the acceptor and donor counts in the slice. The
per-burst BVA statistic is the standard deviation over the $m$ slices,

$$
s_E = \sqrt{\frac{1}{m}\sum_{i=1}^{m}\bigl(E_i - \bar{E}\bigr)^2}.
$$

Each burst maps to a single 2-D point $(\bar{E}, s_E)$. The population is
visualized as a 2-D density with the static line overlaid.

# The shot-noise static line

For a static molecule every slice samples the same underlying efficiency $E$, so
$n_A \sim \mathrm{Binomial}(n, E)$ and $E_i = n_A/n$ has variance $E(1-E)/n$. The
expected standard deviation is

$$
\sigma_\text{sn}(E) = \sqrt{\frac{E(1-E)}{n}},
$$

a semicircle-like curve peaking at $E=\tfrac12$ and vanishing at $E\in\{0,1\}$,
lowering as $n$ grows. Bursts on the line are static; bursts sitting **above** it
carry excess (dynamic) variance. Dynamic two-state exchange produces an arch of
elevated $s_E$ at intermediate $\bar{E}$ bridging the two static sub-populations.

Implementation note: chisurf and tttrlib generate the static line by **Monte-Carlo
binomial sampling** (`compute_static_bva_line`) rather than the closed form. The
sampled line captures the discrete estimator's small bias at low $n$ and near the
$E\to 0,1$ edges; it converges to $\sqrt{E(1-E)/n}$ in the interior. The same $n$
must be used for the data and the line.

# Choosing n

Slice size $n$ trades statistical stability vs. time resolution: small $n$ →
more slices, sensitivity to fast exchange, noisier $s_E$, taller static line;
large $n$ → smoother $s_E$, lower line, blind to the fastest dynamics. Typical
$n \approx 5$–$10$ photons. chisurf also supports slicing by a fixed **time
window** (`minimum_window_length`, `number_of_photons_per_slice = -1`) instead of
a fixed photon count, for strongly varying count rates.

# Mapping to the chisurf implementation

- **Reference implementation** — `chisurf/core/fluorescence/burst/bva.py`:
  `compute_bva(df, tttrs, donor_channels, donor_micro_time_ranges,
  acceptor_channels, acceptor_micro_time_ranges, minimum_window_length,
  number_of_photons_per_slice)` iterates bursts (rows carry `First File`,
  `First Photon`, `Last Photon`), slices each by photon count or time window,
  counts donor/acceptor photons via routing-channel + micro-time masks, and writes
  `Proximity Ratio Mean` / `Proximity Ratio Std` columns. `compute_static_bva_line`
  there does the binomial Monte-Carlo line.
- **Fast engine** — `tttrlib.BVA` (C++, parallel over bursts; base class
  `tttrlib.BurstFeature`). The plugin's `core/computation.py::_compute_bva_tttrlib`
  groups burst rows by source file, builds one `tttrlib.BVA(tttr)` per file, calls
  `set_donor(channels, micro_time_ranges)` / `set_acceptor(...)`, then
  `compute(burst_pairs (n,2) int64, number_of_photons_per_slice,
  minimum_window_length)` and reads `get_proximity_ratio_mean()` /
  `get_proximity_ratio_std()`. `compute_bva` **requires** this path; a missing
  engine raises rather than degrading. The static-line helper is
  `tttrlib.BVA.compute_static_bva_line`.

  There used to be a vectorized NumPy (cumsum-based) fallback behind a
  `try`/`except`. It was deleted on 2026-08-31 after an A/B on a real file
  (`test/data/tttr/BH/132/BH_SPC132.spc`, 120 bursts of 400 photons) showed two
  defects that a silent fallback would have made invisible:

  - it sliced each burst `[first_photon:last_photon]`, **dropping the last
    photon of every burst**. Correcting the slice to `[first:last+1]` brought
    the two paths from `max|Δ| = 1.25e-2` to **3.3e-16** — so the arithmetic was
    the same and only the bounds were wrong;
  - with **empty** micro-time ranges it returned all-zero ratios, because
    `np.logical_or.reduce([])` is scalar `False` and the stream masks collapsed.
    The default is `((0, 4096),)`, so this only bit a caller that passed `[]`
    explicitly — the compiled engine reads empty as *no gating*.

  Both sat behind `except Exception: ... using numpy`, so a transient engine
  failure would have swapped correct results for quietly wrong ones.
- **Plugin** — `chisurf/plugins/burst/burst_bva/` follows the client-server burst
  standard: `backend/` + `server/` (RPC services, compute), `api/` (contract,
  models, serialization), `gui/` (database-free client/adapter/tool), `cli/main.py`,
  `wizard.py`. Results are written as `.bv4` companion files named after the burst
  `.bur` stem (`write_bv4_analysis`) so ndX and the burst browser join them
  by stem; `read_burst_analysis` skips `.json`/`.yaml` sidecars when merging tables.
- **Columns** — per-burst outputs surface as `Proximity Ratio Mean` and
  `Proximity Ratio Std`, visible in the Browser and ndX alongside the other
  per-burst burst-feature columns.

# Related concepts

- [FRET-2CDE / crosstalk](/references/crosstalk.md) — complementary photon
  kernel-density dynamics test on the same bursts.
- [H2MM theory](/references/h2mm-theory.md) — model-based hidden-Markov recovery
  of the states BVA only flags.

# Citation

J. P. Torella, S. J. Holden, Y. Santoso, J. Hohlbein, A. N. Kapanidis,
*Identifying molecular dynamics in single-molecule FRET experiments with burst
variance analysis*, **Biophys. J.** 100(6), 1568–1577 (2011).
doi:10.1016/j.bpj.2011.01.066
