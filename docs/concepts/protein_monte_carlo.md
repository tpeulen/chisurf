---
type: Concept
title: 'Protein Monte Carlo: torsion-angle sampling under distance restraints'
description: How ProteinMC moves a protein through backbone and side-chain torsions, accepts or rejects each move by the Metropolis rule, and scores the structure with FRET distance restraints and structural potentials.
tags: [concepts, structure, fret, sampling]
anchor: concept-protein-monte-carlo
---

(concept-protein-monte-carlo)=
# Protein Monte Carlo: torsion-angle sampling under distance restraints

A set of FRET distances rarely fixes a structure. ProteinMC samples conformations that satisfy the distances and
stay protein-like, so that the spread of the samples shows what the restraints leave open. It is a Metropolis walk
in torsion space started from a given structure.

## Moves

The coordinates are internal: backbone angles $\varphi_i$, $\psi_i$, $\omega_i$ and side-chain angles $\chi$.
Changing one torsion keeps bond lengths and bond angles fixed, so the move stays sterically sensible ({cite}`ramachandran1963` is the map of which $(\varphi,\psi)$ pairs exist). One trial:

1. Draw a residue $i$ with probability proportional to the move map $m_i$. A residue with $m_i = 0$ never moves.
2. Draw each torsion type independently with probabilities $p_\varphi$, $p_\psi$, $p_\omega$, $p_\chi$
   (defaults 0.7, 0.3, 0, 0.01).
3. Add $\delta = (u - \tfrac12)\,s$ to the chosen torsion of residue $i$, $u \sim U(0,1)$, $s$ the step `scale`
   (default 0.0025, in the angle unit of the internal-coordinate table).

## Acceptance

The trial structure has energy $E_1$, the current one $E_0$. With $k_BT$ in the units of $E$ (`kt`, default 1.5),

$$
P_\text{accept} = \min\!\bigl(1,\; e^{-(E_1 - E_0)/k_BT}\bigr),
$$

the rule of {cite}`metropolis1953`: a move that lowers $E$ is always kept, one that raises it is kept with the
Boltzmann factor. The walk therefore samples $p(\text{structure}) \propto e^{-E/k_BT}$, a posterior over the
structure when $E$ is a $\chi^2$ and $k_BT$ is 1. At the default $k_BT = 1.5$ it is a tempered version of that.

## Energy

The energy is the weighted sum of the potentials configured for the run, $E = \sum_k w_k E_k$.

**Restraint potential** (name `dye`, or `fps`). It reads an FPS labeling file (`Positions`, `Distances`; the format
of the [FPS JSON editor](../guides/44_molecular_viewer.md)) and scores the model distance $d_j$ between the two
positions of each distance $j$ against its target $\bar d_j$,

$$
E_\text{restr} = \sum_j \left(\frac{d_j - \bar d_j}{\sigma_j^\pm}\right)^2,
\qquad
\sigma_j^\pm = \sigma_j^- \;\text{for}\; d_j < \bar d_j,
\qquad
\sigma_j^\pm = \sigma_j^+ \;\text{for}\; d_j \ge \bar d_j
$$

with the asymmetric errors `error_neg` and `error_pos` of the file. A position is resolved by chain, residue and
atom name (CA when that atom is missing) and else by its attachment-atom index. **The distance is measured between
the attachment atoms, not between dye centres**: the linker and dye are not simulated here. The distance targets
should therefore be the mean attachment-to-attachment distances implied by the FRET measurement, which is what the
accessible-volume model computes ([accessible volume](accessible_volume.md)). A `χ²` entry in the file selects a
subset of the distances (`score_set`).

**Structural potentials**, each a name in the run settings:

| Name | Term |
|---|---|
| `default` (Clash potential) | steric clashes |
| `hbond` (H-Potential) | statistical backbone hydrogen bonds |
| `mj` (Miyazawa-Jernigan) | residue-residue contacts, {cite}`miyazawa1996` |
| `unres` (Iso-UNRES) | coarse-grained contact energy |
| `go` (Go-Potential) | contacts of the start structure (native-centred) |
| `rama` (Ramachandran) | backbone torsion preferences |
| `asa` (ASA-Calpha) | solvent accessibility of C-alpha atoms |
| `rg` (Radius of Gyration) | compactness |

## Which residues move

By default every residue moves with equal probability. With a labeling file that carries a `FlexFit` section, the
residues of one flexible set get $m_i = 1$ and all others 0, so that the rigid core stays put and only the declared
linkers and loops are sampled. An explicit `move_map` in the settings takes precedence.

## Assumptions and limits

- Sampling is local. Steps are small and moves are accepted one at a time, so the walk explores the neighbourhood
  of the start structure, not the whole conformational space. Large rearrangements need a different start or the
  [FRET docking](../guides/88_fret_docking.md) tool.
- Two successive written frames are correlated. A frame is written every `n_out` accepted moves; the effective
  number of independent structures is smaller than the number of frames.
- A $\chi^2$ near 1 per distance means the restraints are met within their errors; it does not mean the structure
  is right. Unrestrained regions keep whatever the start structure and the potentials give them.
- Only standard amino acids with complete backbone are used; hetero groups and incomplete residues are dropped at
  load, and the backbone amide hydrogen is added.

## See also

- Guide: [Sampling a protein under FRET distance restraints](../guides/106_protein_monte_carlo.md).
- Code: `chisurf/plugins/modelling/proteinmc/` (runner `ProteinMCRunner`, CLI `csc proteinmc`); the Metropolis rule
  is `chisurf.core.math.rand.mc`.
- Key literature: {cite}`metropolis1953` for the acceptance rule; {cite}`kalinin2012` for FRET-restrained
  structural modelling and the distance network; {cite}`sindbert2011` for the accessible volume that turns a
  measured distance into an attachment-atom target.
