# Record

Measures single molecules with **pulsed interleaved excitation (PIE)** and analyses every burst while
the measurement runs: the E–S histogram builds up as you measure, and the run lands in the project
with exactly the bursts you saw.

## Sources

| Source | What it is |
|---|---|
| **Simulator (PIE smFRET)** | tttrlib's photon simulator: molecules diffusing through a confocal focus, each carrying donor and acceptor, excited alternately by both lasers. Populations are set by E and S, so the answer is known. |
| **Replay a photon stream** | A photons dataset of the Datasets workspace played back at measurement speed (*Speed* 1) or faster. |
| **Device** | Not available yet. The MultiHarp source arrives with its driver and plugs into the same place. |

## What is computed, live

1. Every photon is classed **DD** (donor detector, prompt window), **DA** (acceptor detector, prompt) or
   **AA** (acceptor detector, delay) from the **Instrument setup**.
2. Bursts are found by the sliding-window rule — *window photons* within *window time*, at least
   *minimum photons* — exactly as [Burst Selection](docs/guides/index.md) searches offline: re-analysing
   the recording gives the same bursts.
3. Background per class is the rate of photons outside bursts. Then

   E = F<sub>DA</sub> / (F<sub>DD</sub> + F<sub>DA</sub>), S = (F<sub>DD</sub> + F<sub>DA</sub>) / (F<sub>DD</sub> + F<sub>DA</sub> + F<sub>AA</sub>)

   with background-corrected counts F, or the fully corrected form when the setup carries γ, β, α, δ
   ([Lee et al. 2005](https://doi.org/10.1529/biophysj.104.054114)).

The histogram shows E and S with the background known when each burst closed; the stored run uses the
final background of the whole measurement.

## Where the run goes

The photons are written to `<name>.ptu` in the acquisition output folder while measuring. On stop the
file enters the Datasets workspace as a photons dataset — linked or embedded as **Read data › Add as**
says — and its bursts become a run in the project, shown below it, readable by ndXplorer and every
burst tool.

## Device session

**Device session…** opens the acquisition window of earlier versions (Becker-Hickl, PicoQuant and
BrickMic setup cards, routing, decay and correlation plots).
