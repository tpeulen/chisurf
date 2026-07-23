# TTTR LUT Tools

Compute and assign **TAC-linearization LUTs** for TTTR data. The tool has two
stages, run in order:

## ① Compute Microtime LUT — *make* a LUT

Build a linearization table from a **uniform-illumination** (uncorrelated-light /
scatter) measurement. Real TCSPC/TAC hardware has *differential non-linearity*
(DNL): the micro-time (TAC) bins are not exactly equal in width, so a flat-light
histogram — which *should* be flat — is not. The Felekyan et al. (Rev. Sci.
Instrum. 2005) construction turns that histogram into a cumulative table
(`NTAC_fract`) that remaps every photon's raw micro-time onto a corrected,
equal-width axis.

Workflow: load the flat-light TTTR file(s) → the app builds the TAC histogram →
drag the orange region to mark the flat **linear plateau** (or use auto-detect) →
adjust NTAC / Noffset → **Save LUT** as `.npy` / `.npz` / `.txt` / `.csv`, or hand
it straight to stage ② with **"→ Use in Assign"**.

## ② Create LUT Settings — *apply* LUTs to channels

Assign the computed LUT(s) to **routing channels**, set an optional per-channel
micro-time **shift**, preview corrected-vs-raw histograms, and export the portable
`settings.tttr.json`.

Workflow: add your measurement TTTR file(s) → the app detects the used channels →
load / receive a LUT → select a channel → **Assign** → optionally set a shift →
**Save JSON**.

## How the LUT reaches a detector setup

The channel-definition editor's **LUT handling** box has a **"Configure LUTs…"**
button that opens this tool. When you close it, the editor pulls the assigned
`channel_luts` / `channel_shifts` from stage ② into the setup. From then on, any
reader that selects that setup (with **Apply TAC linearization** ticked)
linearizes photons automatically at read time — the correction is applied through
the single `staging.open_tttr` seam, so previews here and production reads match.

`settings.tttr.json` remains an interchange format: you can **Save**/**Load** it to
share a correction between setups or machines.

## Output format (`settings.tttr.json`)

```json
{
  "description": "TTTR microtime correction settings",
  "version": "1.0",
  "reading_routine": null,
  "channel_luts": {"0": [0.0, 1.0, 2.5, ...], "1": [...]},
  "channel_shifts": {"0": 5, "1": -2},
  "metadata": {"created": "...", "used_channels": [0, 1], "notes": "..."}
}
```

## Layers (first-class plugin)

- **`api/`** — pure, Qt-free logic: `lut` (Felekyan math), `io` (file/tttrlib IO),
  `compute` (orchestration), `settings` (`settings.tttr.json` + apply), `contract`.
- **`backend/services.py`** — RPC handlers (`lut.compute`, `lut.apply_preview`,
  `lut.settings_build`, `lut.settings_load`, `lut.autodetect_region`).
- **`cli/main.py`** — `chisurf lut-tools {compute,apply,settings}`.
- **`gui/`** — the two-stage AutoForm workspace.

## Reference

Felekyan et al., *Rev. Sci. Instrum.* 76.8 (2005) 083104.
