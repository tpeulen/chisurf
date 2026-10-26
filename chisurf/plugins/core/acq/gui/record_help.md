# Record

Measures single molecules and analyses every burst while the measurement runs: the histograms of
the measurement type build up as you measure (E–S for PIE), a quality panel says whether to go on,
and the run lands in the project with exactly the bursts you saw.

## Sources

| Source | What it is |
|---|---|
| **Simulator (smFRET)** | A simulated MultiHarp measuring tttrlib's photon simulator: molecules diffusing through a confocal focus, each carrying donor and acceptor — with **PIE** excited by a green and a red pulse per period, with **two colour** by the green laser only. Populations are set by E and S, so the answer is known; the records take the same path as a real device's. |
| **Replay a photon stream** | A photons dataset of the Datasets workspace played back at measurement speed (*Speed* 1) or faster. |
| **PicoQuant device (USB)** | A MultiHarp (or another PicoQuant device the driver supports) over USB, through CMC's pqusb: **Connect**, check the count rates, set the sync and input levels, then Start. |

## Measurement types

The **Experiment setup** reads the Instrument setup as one measurement type (by default the one the
setup describes):

| Type | Quantities | Histograms |
|---|---|---|
| Single colour | burst size and duration | photons, duration |
| Two colour | proximity ratio | proximity ratio |
| PIE / µs-ALEX | proximity ratio, stoichiometry (with γ, β, α, δ also FRET efficiency and corrected S) | proximity ratio vs stoichiometry |
| MFD | anisotropy per colour, proximity ratio | anisotropy; proximity ratio vs donor anisotropy |
| Three-colour PIE | proximity ratios BG, BR, GR; stoichiometries BG, GR | PR(GR) vs S(GR); PR(BG) vs PR(BR) |

**Histogram** above the plots picks which one is shown; a 2-D histogram comes with both marginals.

## What is computed, live

1. Every photon is counted in its streams: each detector, and each detector in each excitation window
   (PIE: prompt green = DD, prompt red = DA, delayed red = AA).
2. Bursts are found by the sliding-window rule — *window photons* within *window time*, at least
   *minimum photons* — exactly as [Burst Selection](docs/guides/index.md) searches offline: re-analysing
   the recording gives the same bursts.
3. The quantities of the type, as the batch analysis computes them — e.g. proximity ratio
   DA / (DD + DA) and stoichiometry (DD + DA) / (DD + DA + AA); with γ, β, α, δ in the setup also the
   accurate-FRET efficiency and stoichiometry ([Hellenkamp et al. 2018](https://doi.org/10.1038/s41592-018-0085-0)).
   Background per stream is the rate of its photons outside bursts.

## Quality lights

Every two seconds the FRET quality checker judges the bursts so far: green continue, amber read the
note, red act now (the note says what to do). Checks that do not apply to the type are grey —
stoichiometry without alternation is *not applicable*, the 2CDE filters are *not computed live* (run
the FRET checker on the recording). The verdict at stop is stored with the run.

## Where the run goes

The photons are written to `<name>.ptu` in the acquisition output folder while measuring. On stop the
file enters the Datasets workspace as a photons dataset — linked or embedded as **Read data › Add as**
says — and its bursts become a run in the project, shown below it, readable by ndXplorer and every
burst tool.

## Device session

**Device session…** opens the acquisition window of earlier versions (Becker-Hickl, PicoQuant and
BrickMic setup cards, routing, decay and correlation plots).
