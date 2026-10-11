# VV/VH detector calibration

Load the fast-rotating reference to determine G from tail matching. Tail/background bounds and fractional VH shifts use TAC-bin units. Core calculations remain the canonical VV/VH backend.

**Load example** loads simulated references whose answer is known: G = 1.2 and no polarisation mixing (a fast dye, a slow protein with ρ 16 ns and r0 0.38, τ 4 ns, and two batch decays). Tail matching should return G within its SD of 1.2 and a linked l1 = l2 near zero.

## Slow-reference mixing
A slow protein reference provides a first-moment lifetime and Perrin steady anisotropy estimate. Only linked l1 = l2 can be determined from one steady-state observable; invalid automatic estimates outside [0, 0.5] are shown but not applied. Manual G, lifetime, steady anisotropy and linked-mixing overrides are explicit controls.

## Outputs
Export calibration JSON or apply a frozen current calibration to a batch of VV/VH decays and save the resulting anisotropy table. Archive uses the existing MMFDB calibration/provenance RPC, preserving corrected traces and the reference source.

## Further reading

- [Time-resolved fluorescence anisotropy](docs/concepts/anisotropy.md)
- [Fluorescence lifetime and anisotropy decay fitting](docs/guides/10_lifetime_anisotropy_fitting.md)
- [The G-factor of a polarised setup](docs/guides/91_vv_vh_g_factor.md)
