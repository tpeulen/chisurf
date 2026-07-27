---
type: Reference
title: Use case — F-test (is the second lifetime justified?)
description: Fit one decay with one and then two exponentials, and use the F-test / chi2-max calculator to decide whether the extra component is statistically justified.
tags: [usecase, tcspc, fitting, statistics, ftest, calculators, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: F-test — is the second lifetime justified?

**Goal:** the question every lifetime fit raises. A one-exponential fit leaves
structure in the residuals; a two-exponential fit always fits better, because
more parameters always fit better. The user needs a number that says whether the
improvement is more than the extra freedom buys — and, for the accepted fit, the
χ² ceiling that bounds its parameter errors.

**Data:** `test/data/tcspc/ibh_sample/Decay_577D.txt` (decay) and
`test/data/tcspc/ibh_sample/Prompt.txt` (IRF), IBH text format, `dt = 0.0141`
ns/ch, 10 MHz. Same pair as the [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md)
use case — this workflow is its natural next step.

## Steps

1. Load decay and prompt and build the one-exponential fit exactly as in the
   [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) (steps 1–8): `TCSPC` /
   `TXT/CSV`, `Skiprows = 11`, `dt = 0.0141`, IRF assigned from the Convolve
   section, **Fit**. Note χ²ᵣ.
2. Select the same dataset again, pick `Lifetime ` and click **Add fit** a second
   time — a second fit window opens on the same data.
3. Assign the same IRF in the new fit's **Convolve** section.
4. Click the green **add** button in the **Lifetimes** section once (now two
   lifetimes), then **Fit**. Note the lower χ²ᵣ.
5. Open **Tools ▸ Calculators** on the ribbon and pick **📉 F-test / χ²-max**
   from the left-hand list.
6. Click **📊 From fit ▾** in the calculator's toolbar. It lists every open fit;
   open the submenu of the **one-exponential** fit and choose
   **→ F-test model 1 (χ²₁, n₁)**.
7. Open the submenu of the **two-exponential** fit and choose
   **→ F-test model 2 (χ²₂, n₂)**.
8. Read **confidence** in the F-test panel — the confidence that the extra
   component is justified.
9. For the accepted fit, choose **→ χ²-max (χ²min, params, ν)** from its submenu
   and read **χ² max** at 0.95 — the largest reduced χ² still compatible with the
   minimum, i.e. the support-plane threshold behind the parameter error bars.
10. Press **?** for the formulas behind both panels.

**Order matters and is not signposted — see RF-493.** Steps 6 and 7 must be done
in that order. Loading model 2 first and model 1 second silently discards the
measured χ²(2).

## Expected

- Step 1 gives χ²ᵣ ≈ 1.63 on ν = 3267 (3271 points, 4 free parameters).
- Step 4 gives χ²ᵣ ≈ 1.13 on ν = 3265 (6 free parameters).
- Step 8 gives a confidence of essentially 1 — the second lifetime is justified
  far beyond the 0.95 a user would quote.
- Step 9 gives χ² max ≈ 1.138 for χ²min = 1.134, p = 6, ν = 3265 at 0.95.
- Two models that fit equally well give exactly 0.5; a *worse* "complex" model
  gives 0.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, private RPC ports)
through the real main window and the real Calculators hub: experiment/reader
combo boxes, `macros.add_dataset`, the **Add fit** tool button, the Convolve
IRF picker (`irf_select.selected_curve_index` + `change_irf()`, i.e. the row
click), the green **add** button, `onRunFit`, then the hub's calculator list and
the tool's own **From fit** menu actions. Screenshots read at every step.

**The statistics are right and the answer is unambiguous.**

| fit | free params | ν | χ²ᵣ | parameters |
|---|---|---|---|---|
| 1 exponential | 4 | 3267 | 1.6259 | τ = 4.149 ns |
| 2 exponentials | 6 | 3265 | 1.1340 | τ₁ = 1.661 ns, τ₂ = 4.220 ns, x₂ = 0.941 |

`From fit ▾` pulled `n_points − n_free` and χ²ᵣ correctly for both, and the
F-test returned **confidence = 1.00000000**. The sanity checks hold: equal
reduced χ² on equal ν gives exactly 0.5, and a complex model that is *worse*
(1.0 → 1.2) gives 0. The χ²-max panel returned 1.13839 for the accepted fit,
matching `χ²min·(1 + p/ν·F.isf(0.05, p, ν))` by hand. The `?` help modal is
genuinely good — both formulas, the sign convention, and why the ratio is
*simpler over complex* (screenshot `15_help_modal.png`). Embedded in the
Calculators hub the toolbar survives and the **From fit** menu still works
(`31_hub_ftest.png`).

**But the order in which the two fits are loaded changes the answer, silently.**
Loading the *complex* fit into slot 2 first and the *simple* one into slot 1
second — an order nothing in the UI discourages — leaves the screen reading
χ²(1) = 1.6259, χ²(2) = **1.6353**, confidence **0.43411**. The measured
χ²(2) = 1.1340 was overwritten by a number no fit produced, and the confidence is
the one computed earlier against the *default* χ²(1) = 1.1. The same run, loaded
in the other order, reports 1.00000000. Nothing warns, and both screens look
equally authoritative (`43_ftest_reverse.png` vs `41_ftest_result.png`). RF-493.

**A NaN confidence is displayed as certainty.** χ²(2) = 0 is inside the spin
box's range; `f_test_confidence` then returns `nan` (scipy returns it rather than
raising, so the tool's `except (ZeroDivisionError, ValueError)` never fires), and
the value widget clamps `nan` to its maximum. The panel reads **confidence
1.00000** — the strongest possible claim — next to χ²(2) = 0.0000
(`21_degenerate_1p0_0p0.png`). RF-494.

**The χ²-max panel accepts inputs it does not use.** `params = 0`, `ν = 0` are
allowed by the view spec but replaced by `max(1, …)` in the computation, so the
panel shows χ² max = 162.44764 beside inputs that cannot produce it; confidence
= 1.0 (the spin box maximum) gives ∞, rendered as a 309-digit `1000000…`
overflowing the field (`22_chi2max_zero.png`, `23_conf_one.png`). RF-495.

Incidental, from the two fits driven here (not F-test defects): the
two-exponential fit settles on **bg = −1.93** counts/channel and **ts = −0.13**,
an unphysical negative background accepted without comment; and the fit windows
of two fits on the same dataset carry the same title apart from a `(1)` suffix.

## UX / UI suggestions

- **Say what the confidence means.** The whole tool exists to answer a yes/no
  question and it answers with a bare `1.00000`. One line under the field —
  *"the extra parameters are justified (≥ 0.95)"* / *"not justified"* — would be
  the actual deliverable. It would also cover the saturation problem: at 5
  decimals every strong result reads `1.00000`, so 0.999995 and certainty are
  indistinguishable.
- **Label the two slots by role, not by number.** `χ²(1)` / `χ²(2)` and
  `n₁` / `n₂` carry the whole convention (simpler = 1) only in the help text.
  *"simpler model"* / *"more complex model"* on the panel would make the load
  order self-evident and prevent RF-493 from being reachable at all.
- **Put the fit's own numbers in the *From fit* menu.** Both entries here read
  `Lifetime  - ./test/data/tcspc/ibh_sample/Decay_577D.txt`, distinguished only
  by a trailing `(1)` — the user comparing 1 vs 2 exponentials cannot tell which
  submenu is which. `Lifetime (2 exp) — χ²ᵣ 1.134, 6 par` would be readable, and
  the full path is not what identifies a fit.
- **Two fields labelled `confidence` in one form.** The F-test panel's confidence
  is an output-that-is-also-an-input; the χ²-max panel's is a pure input. Give
  them distinct labels (*"F-test confidence"* / *"limit at"*).
- **The read-only χ² max looks exactly like the editable fields** — same frame,
  same background, only the missing spin arrows hint at it. In the dark theme all
  value boxes read as disabled, which makes the distinction invisible.
- **The `?` button floats unanchored** at the top-right of the form, on its own
  row below the toolbar, closer to the F-test panel than to either. Put it in the
  toolbar next to *From fit*.
- **Window title says `F-Calculator`**, the ribbon and hub say *F-test / χ²-max*,
  the class says `F-Test`, the manifest says `Main:Tools:F-Test`. Pick one.
- **Nothing links back to the fits.** After loading, the panel is a snapshot: re-fit
  a model and the numbers silently go stale with no indication of which fits they
  came from. Showing the two fit names under the panel would fix both.
- **No unit/definition hints on `n₁`/`n₂`.** They are degrees of freedom
  (points − free parameters), which the tool computes for you when loading from a
  fit but never states; a user typing them by hand may enter the number of points.

## Bugs filed

- RF-493 — loading the simpler fit into *model 1* overwrites the χ²(2) already
  loaded from the complex fit and leaves a stale confidence; only one load order
  gives a correct answer.
- RF-494 — a NaN confidence (χ²(2) = 0) is displayed as `1.00000`, the maximum.
- RF-495 — the χ²-max panel accepts `params`/`ν` = 0 but computes with 1, and
  confidence = 1.0 renders ∞ as a 309-digit number.
