# QuEst Analysis: quenching chemistry from measured lifetimes

The *Forward model* page predicts the lifetime of a dye at one site from the structure. This page runs the other way. It takes the lifetimes measured on many labelled sites, together with the free-dye titrations against amino acids, and fits what the dye's quenching chemistry must be: how strongly contact with each residue quenches it (the *quench scale*, relative to the titrations), how long it lingers near each group of residues (*stickiness* per group), the contact distance, and the extra lifetime of a dye position shielded by protein.

If you have not used it before, press **Guide**. **Load example** loads the shipped MalE data set: nine sites, the dyes AF488, Cy3B and Atto655, apo and holo, in normal and heavy water.

## What you enter

| Control | Meaning |
|---|---|
| **Load example** / **Data folder…** | A folder with the three measurement tables: `tcspc_fit_results.csv` (lifetimes per site and D₂O fraction), `amino_acid_quenching_flt.csv` (titration points) and `titration_summary.csv` (free-dye lifetimes). `examples/male` has this layout. |
| **Preset** | *Quick* runs 8 searches with short iterations: about 20 minutes on a desktop, and its numbers are less reliable. *Full* runs 64 searches, as the stored analysis did, and takes hours on a desktop (the stored run took 24 minutes on 44 cores). |
| **Stages** | *all*, or one stage plus whatever it needs. |
| **Workers** | Worker processes for the searches. 0 means every CPU. The numbers do not depend on it. |
| **Profile likelihood** | Also refit the data set at fixed quench-scale values. This costs about one joint fit per point. |

**Run** first builds the site table of every measured site: the accessible volume of the dye, the residues and quenchers around each position, and its water exposure. They are cached, so only the first run pays for them (about ten seconds per table). Then it runs the stages in the background. **Cancel** stops at the next checkpoint. **Write results…** writes every table as CSV, plus `summary.json` and `report.md`.

## The stages

- **A**: AF488 and Cy3B in normal water.
- **B**: Atto655 in heavy water alone.
- **Naive H₂O test**: B's parameters predict normal water with no water term. This test is expected to fail, because water quenches Atto655 on the protein as well.
- **C**: Atto655 in heavy and normal water together. The water term is the free dye's rate times the exposure, with no new parameter.
- **Summary**: one line per dye.

A and C are two views of one joint graph, because every dye reads the reference dye's titration slopes. Running A therefore solves C as well.

## Reading the results

| Tab | What it shows |
|---|---|
| **Data** | Stern–Volmer points and posterior slopes, the shared day-to-day error, the K_SV/kq table, the site lifetimes with their errors, the free-dye τ₀, and water quenching per site. |
| **kQ per dye** | Contact rate per residue for each dye, scaled from the reference chemistry by the titrations. |
| **Site tables** | One row per site table; select a row to see its exposure histogram. |
| **Fit** | For one stage and data set: the text, predicted vs measured lifetime (outliers ringed, free-dye τ₀ dashed), estimates with 68 % intervals, leave-one-site-out \|z\| with the outlier line at 3, the quench-scale profile, and the titration slopes before and after the fit. |
| **Water** | Stage C: water access per site (model vs measured), the time-weighted exposure of the visible dye, and the quench scale from B against C. |
| **Summary** | Quench scale and stickiness per dye, on log axes. |

A note such as *not determined* or *at the edge of its range* means that the data do not fix that parameter. Read the interval, not the value.

## Limits

- **Quick is a first look.** Its searches can stop before the best fit. Use *Full* for numbers you report.
- **The structures decide the answer.** The site tables come from the crystal structures (PDB 1OMP apo, 1ANF holo) at each dye's stretched linker length. A site whose label changes the protein locally is outside the model.
- **Error bars are Laplace.** They come from the curvature at the best fit. The profile likelihood shows where that curvature description is too narrow.

## Further reading

- [Quenching inference](docs/concepts/quenching_inference.md): the titration posterior, the site model, the graph, the stages, and the stored MalE numbers.
- [Dye quenching by amino acids](docs/concepts/dye_quenching.md): the contact model behind the forward simulator.
- [QuEst: the workflow](docs/guides/80_quenching_estimator.md): the forward model, the command line and the Python API.
- Peulen, Opanasyuk and Seidel 2017, [10.1021/acs.jpcb.7b03441](https://doi.org/10.1021/acs.jpcb.7b03441).
