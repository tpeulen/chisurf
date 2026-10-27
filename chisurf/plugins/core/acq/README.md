# Acquisition plugin

Record single-molecule photon streams and watch the analysis build up live (decay,
correlation, count rate, bursts, E-S histogram). The window is the native Record tool
(`gui/record_app.py`, the manifest's `emtk` entrypoint).

## Sources

- **TCSPC hardware through phacq.** Devices are driven by the phacq library: native drivers
  for PicoQuant MultiHarp / PicoHarp 330 / HydraHarp 500, Becker & Hickl SPC cards and the
  PicoQuant Sepia II laser, with no vendor libraries. The vendor-library device session of
  earlier versions (BH SPCM-DLL, PicoQuant, BrickMic wrappers) has been removed.
- **The tttrlib photon simulator** (`tcspc_devices/simulation/`): diffusion through a confocal
  focus with N-state photophysics/FRET, anisotropy and pulsed excitation; also exposed as the
  `acq.simulation.run` RPC method and the headless CLI below.
- **Replay** of a workspace photon stream.

## Acquisition fit window

Inside ChiSurf the plugin can simulate a demo stream (`demo.py`), register it as an
`AcquisitionDataset` (`dataset.py`) and open a fit window with the `Acquisition`
model (`chisurf/core/models/acquisition`) whose pages (`chisurf/emtk/fit_pages/pages/acquisition.py`)
are the live decay, correlation, MCS and macro-time plots.

## Command line

### Unified module entry point

From the repository root:

```bash
# Start the Record window
python -m chisurf.plugins.core.acq

# Force standalone GUI window (without starting full chisurf)
python -m chisurf.plugins.core.acq --standalone
```

### Headless simulation CLI

The same entry point exposes the simulation CLI when you pass `--cli`.
This uses the tttrlib photon simulator and the same parameter structure as the
simulation setup dialog.

```bash
# 1) Generate a simple JSON config
python -m chisurf.plugins.core.acq --cli config \
  --output my_simulation.json \
  --n-species 1 \
  --n-ph-max 100000 \
  --spc-output-dir simulation_output

# 2) Run the simulation and write SPC-132 files
python -m chisurf.plugins.core.acq --cli run \
  my_simulation.json \
  --output-dir simulation_output \
  --n-ph-max 100000 \
  --batch-size 50000
```

For FRET/FCS examples, the CLI also provides a preset for an
**N-state FRET system** with a brightness gradient between low- and
high-FRET states plus dynamic nearest-neighbor exchange. For example,
with 2 FRET states (low/high):

```bash
python -m chisurf.plugins.core.acq --cli config \
  --output dynamic_fret_exchange_config.json \
  --fret-states 2 \
  --M 0.01 --M 0.01 \
  --D 3.0 --D 3.0 \
  --n-ph-max 200000 \
  --spc-output-dir simulation_output_dynamic_fret \
  --exchange-rate-ms 1.0
```

Then run the simulation as above with the `run` subcommand.

👉 See
`tcspc_devices/simulation/CLI_README.md` for detailed documentation of
all CLI options, JSON structure, and additional FRET/FCS presets.

### Typical CLI workflow (including JSON editing)

1. **Generate a base JSON configuration**

   Use the `config` subcommand to create a starting JSON file:

   ```bash
   python -m chisurf.plugins.core.acq --cli config \
     --output my_simulation.json \
     --n-species 1 \
     --n-ph-max 100000 \
     --spc-output-dir simulation_output
   ```

   or, for FRET/FCS:

   ```bash
   python -m chisurf.plugins.core.acq --cli config \
     --output dynamic_fret.json \
     --fret-states 2 \
     --M 0.01 --M 0.01 \
     --D 3.0 --D 3.0 \
     --n-ph-max 200000 \
     --spc-output-dir simulation_output_fret
   ```

2. **(Optional) Edit the JSON**

   Open the generated JSON (e.g. `my_simulation.json` or
   `dynamic_fret.json`) in a text editor if you want to fine-tune
   parameters beyond the CLI flags:

   - Adjust the number of molecules or diffusion coefficients in
     `M` and `D`.
   - For FRET systems, directly modify the per-state brightness in
     `q` or the kinetic exchange matrix `k_nrad`.
   - Change output paths, TAC/IRF parameters, or RNG seeds.

   Advanced users can also load the JSON into the GUI **simulation
   setup dialog**, adjust parameters interactively, and save it back
   out for use with the CLI `run` step.

3. **Run the simulation headless**

   Once the JSON reflects the desired settings, call the `run`
   subcommand to generate SPC files:

   ```bash
   python -m chisurf.plugins.core.acq --cli run \
     my_simulation.json \
     --output-dir simulation_output \
     --n-ph-max 100000 \
     --batch-size 50000
   ```

4. **Inspect and analyze the output**

   The CLI writes Becker & Hickl SPC-132 files (`m000.spc`, `m001.spc`,
   …) into the chosen output folder. These can be opened in downstream
   tools (e.g. FCS, burst analysis, or the GUI) for further analysis.

