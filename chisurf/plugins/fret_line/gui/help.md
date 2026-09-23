# FRET Line Generator

A FRET line is the curve a burst population should follow in the plane of
efficiency *E* against the fluorescence-averaged donor lifetime τ_F, under a
stated model. A static species sits on the **static line**. A molecule
exchanging between two states within the burst sits on the **dynamic line**
between them. Along every line E = 1 − τ_X/τ_D0, and the model sets how
τ_X and τ_F are related.

## Controls

* **Components**: the models whose lifetime spectra are mixed. *FD (Gaussian)*
  for distance distributions (w = linker width σ), *FD (Discrete)* for sharp
  distances, *FD (Worm-like chain)* for a chain, *Lifetime* for plain
  exponentials. **Weight** is the initial mixing weight.
* **Editor**: the model editor of the selected component. Only the donor, FRET
  parameters and distances matter. The IRF and background groups have no
  effect, because no decay is convolved.
* **Sweep**: **Vary** a parameter (`C<i> [model] · name`) or a mixing fraction
  (`fraction · C<i>`) from **Min** to **Max** over **Points** (optionally
  **log**). **τ_D0** is the reference lifetime. 0 takes it from the first FRET
  component's donor. A line made only of *Lifetime* components needs it set
  explicitly.
* **+ Add FRET line** computes the current sweep as a new, coloured line.
  Earlier lines stay.
* **FRET lines** tab: show, hide, remove or clear lines.
* **Save CSV** writes all lines. **Push to ndX** overlays them on the visible
  ndX overlay panels.

## Recipes

| Line | Components | Vary |
|---|---|---|
| static | one FD (Gaussian), w = 6 Å | RDA0, 20–120 Å |
| no-linker diagonal | one FD (Discrete) | RDA0 |
| dynamic | two FD (Gaussian) at the two state distances | fraction · C0, 0–1 |

With τ_D0 = 4 ns and R0 = 52 Å, the static line passes E = 0.559 at
τ_F = 2.0 ns, where the diagonal gives 0.500. The 40 ↔ 70 Å dynamic line reaches
τ_F = 2.96 ns at E = 0.493.

## Headless

```bash
python -m chisurf.plugins.fret_line --params spec.json
```

The spec holds the arguments of
`chisurf.plugins.fret_line.core.algorithms.compute_fret_line`, with parameters
given by canonical id (`distance.mean.0`, `distance.sigma.0`, …). The
closed-form lines are in `chisurf.core.fluorescence.fret.lines`
(`static_fret_line`, `dynamic_fret_line`).

## Further reading

* [Accurate FRET and FRET lines](docs/concepts/accurate_fret.md) — the static, dynamic and linker-corrected lines in closed form
* [FRET lines guide](docs/guides/82_fret_lines.md) — every control, the standard lines, headless use and known defects
* [Accurate FRET guide](docs/guides/41_accurate_fret.md) — the lifetime route to γ that uses the static line
- {cite}`barth2022` — theory of FRET lines
- {cite}`sisamakis2010` — E–τ diagrams in multiparameter detection
- {cite}`kalinin2010b` — excess width from acceptor photophysics, not dynamics
