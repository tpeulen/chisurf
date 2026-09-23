# QuEst — quenching estimated from a structure

QuEst predicts the donor decay of a dye tethered to a protein. The dye diffuses
inside its accessible volume (AV) around the structure, and it is quenched
whenever it comes within a critical distance of a quenching residue — **Trp,
Tyr, His, Met** (and Pro), by photoinduced electron transfer. Integrating the
quenching along the diffusion trajectory gives a decay histogram, and with an
acceptor placed, the transient FRET decay.

The result is a **non-exponential decay computed from a structure**: a
multi-exponential donor-only decay need not mean conformational states — it can
be one dye sampling distances to a fixed set of quenchers.

## Order of work

1. **Load PDB…**, then the attachment chain, residue and atom of the dye.
2. **Dye** — linker length, linker width and dye radius; they define the AV.
3. **Quenching** — the quencher table; **FRET** — the acceptor, if any.
4. **Simulate**, and read the decay and the dye trajectory in *Results*.

## Caution

- **Quenching is a step in distance.** A quencher inside the critical distance
  quenches at its full rate, one outside not at all; the rates and distances are
  a table, not a fit to your data.
- **The AV and the sticking define the answer.** A wrong linker length or
  slowing radius (the surface sticking) changes which quenchers the dye
  reaches, and with it the predicted quantum yield.
- **A prediction, not a measurement.** Compare with a measured donor-only
  lifetime; a mismatch is evidence about the structure or the linker.

## Current state

QuEst needs the `quest` package and IMP.bff. The installed IMP.bff no longer
has the `IMP.bff.quenching` Python module that `quest` imports, and until
`quest` is ported to the C++ functions now in `IMP.bff`, this panel shows
that import error instead of the form. The guide
[QuEst — the workflow](docs/guides/80_quenching_estimator.md) has the details.

## Further reading

- [Dye quenching by amino acids](docs/concepts/dye_quenching.md) — the
  contact model, the rate table and what quenching does to lifetimes, FCS and
  FRET.
- [QuEst — the workflow](docs/guides/80_quenching_estimator.md) — every
  setting, the outputs and the command line.
- [Quenching mechanisms](docs/fundamentals/quenching_mechanisms.md) — PET, the
  quenching residues, and how QuEst turns them into a decay.
- {cite}`peulen2017` — the diffusion-simulation approach QuEst implements for
  analysing time-resolved FRET of labelled macromolecules.
