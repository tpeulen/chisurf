# Acquisition

The native acquisition window keeps the legacy physical workflow: choose a
source, explicitly **Initialize device**, configure at least one stop condition,
then use **Start** and **Stop**. Selecting a hardware label never imports or
contacts its wrapper. If the wrapper, driver, or card is unavailable, the
initialization status tells you whether no device was made or initialization
failed; the app never silently switches that choice to Simulation.

## Routing, output, and settings

The four routing controls are passed in order to `PipelineConfig.channels`.
Set them to the detector routing values used by the measurement before starting.
**Output folder** is merely passed to compatible Simulation and BrickMic
backends; it does not promise that every TCSPC backend writes a raw file.

**Save settings** and **Load settings** use a selected JSON file. They preserve
device choice, stop conditions, routing, output text, tab visibility, and the
full simulation dictionary. Loading validates the document but never initializes
hardware.

## Simulation and results

Simulation generates encoded SPC records and feeds them through the same
`AcquisitionPipeline` as a device FIFO. **Simulation setup** (also *Device Setup…* for
the Simulation source) edits the simulated sample: a species table (molecules M,
diffusion D, parallel/perpendicular brightness of each enabled colour, a background
row and a per-species decay), the radiative and non-radiative kinetics rate grids
(row to column, 1/ms), geometry, microtime and performance settings. **OK** validates
the result with the simulator engine and uses it for the next run. **Advanced
simulation parameters** is a
complete JSON editor: Apply constructs the real simulator engine before keeping
the text. Live plots (decay, correlation, count rate, MCS, macrotime) are drawn from
`AcquisitionPipeline.snapshot()` while the run is going; no values are fabricated
for the UI. Each tab has its own controls: channel pairs, binning, **Set to mean**,
bin width and update rate. Routing channels, correlation pairs and MCS bin width
apply when the next acquisition starts.

**Device Setup…** opens the setup card of the selected device: B&H SPC (Detect
Cards, the *Modules* table whose *Use* ticks form the active-card selection, the
CFD, Sync, TAC, Timing and Mode parameters, Read
values, Save/Load JSON, Apply), PicoQuant (firmware-owned mode and reference,
maximum photons, device status), BrickMic (counter window, acquisition rate,
buffer size, photons per SPC file). Apply writes to the device; OK / close and
Cancel never write edits that were not applied.

## Further reading

- [Acquisition plugin README](chisurf/plugins/core/acq/README.md)
