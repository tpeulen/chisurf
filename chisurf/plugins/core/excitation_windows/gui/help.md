# Setup: Excitation Windows

Finds the excitation pulses of a measurement and proposes the windows a PIE or µs-ALEX analysis
needs -- and checks the windows a detector setup already has against the data.

## What it detects

* **PIE / nsALEX** (the lasers alternate within one sync period): every excitation pulse is a
  *rising edge* in the micro-time decays. Two pulses give the windows **prompt** (donor
  excitation) and **delayed** (acceptor excitation); the detectors tell which is which, because
  under the acceptor pulse the donor detector is dark. More pulses (a sync divider, three lasers)
  get one window per pulse.
* **µs-ALEX** (the lasers alternate over microseconds): the alternation period and phase from the
  macro times; the windows are phases of the period.
* **One pulse** -- a donor-only sample, or not a PIE measurement. Windows cannot be placed from
  it; the tool says so and changes nothing.
* **Unclear** -- too few photons, or a flat micro time (continuous-wave excitation).

## Controls

| Control | Does |
|---|---|
| **Setup to check** | A detector setup of the workspace. Its windows are converted to the data's channel width (its *Microtime res.*) and checked. |
| **Measurement** | A photon stream of the workspace; drop a TTTR file on ChiSurf to add one. |
| **Detect** | Detects the windows of the picked measurement and checks the setup's. |
| **Example** | A simulated PIE measurement whose answer is known. |
| **Use detected windows** | Saves the setup with the detected windows into the workspace. |
| **Keep current windows** | Changes nothing. |

## What the check reports

A window outside the data's channel range, a pulse no window holds, a window boundary inside a
pulse, a window holding two pulses, *prompt* and *delayed* swapped, a window without photons, and
windows defined at another channel width (converted, and said so).

The same check runs in the setup editor (*Auto-detect windows*), during a Record run, and before
burst selection on PIE data.

## Command line

```
csc windows detect run.ptu
csc windows check run.ptu --setup my.setup.json --write fixed.setup.json
```

## Further reading

* [Excitation windows: method](docs/concepts/excitation_windows.md)
* [Detecting and checking excitation windows](docs/guides/115_excitation_windows.md)
