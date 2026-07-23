# TTTR LUT Tools

Compute **TAC-linearization LUTs** for TTTR data and add them to your detector
setup. The two tabs are **not** equal partners:

| Tab | What it is | When you use it |
|-----|------------|-----------------|
| **① Compute LUT** | The main tool. Makes one LUT **per routing channel** and adds them all to your Detector setup. | Always. |
| **② settings.tttr.json** | Optional file interchange — save/load the correction as a portable file, or hand-assign LUT *files* to channels. | Only to share a correction, or import one you already have. |

**Normal workflow:** open this from the Detector setup's *Configure LUTs…*
button → in **① Compute LUT** load the flat-light file → **➡ Add all channels to
setup** (a LUT is computed for every routing channel) → close the window. That's
it — you never need tab ②, and saving a file is optional. The **Preview channel**
selector is only for checking/hand-tuning one channel before adding.

## ① Compute LUT — *make* per-channel LUTs

Build a linearization table from a **uniform-illumination** (uncorrelated-light /
scatter) measurement. Real TCSPC/TAC hardware has *differential non-linearity*
(DNL): the micro-time (TAC) bins are not exactly equal in width, so a flat-light
histogram — which *should* be flat — is not. The Felekyan et al. (Rev. Sci.
Instrum. 2005) construction turns that histogram into a cumulative table
(`NTAC_fract`) that remaps every photon's raw micro-time onto a corrected,
equal-width axis. **DNL is per routing channel**, so one LUT is computed per
channel.

Workflow: load the flat-light TTTR file(s) → **➡ Add all channels to setup** (a
LUT is computed for every routing channel, its region auto-detected, and assigned).
Use the **Preview channel** selector + the orange region only to check or
hand-tune a specific channel first. Optionally **Save LUT file…**.

## ② settings.tttr.json — *optional* file interchange

Only needed to share a correction between setups/machines, or to import a LUT you
already have as a file. It lets you assign LUT *files* to channels, set an
optional per-channel micro-time **shift**, and **Save**/**Load** the portable
`settings.tttr.json`. The normal ①-based workflow does not require this tab.

## How the LUT reaches a detector setup

The channel-definition editor's **LUT handling** box has a **"Configure LUTs…"**
button that opens this tool. **➡ Add to Detector setup** assigns each per-channel
LUT; when you close the window the editor pulls those `channel_luts` /
`channel_shifts` into the setup. From then on, any reader that selects that setup
(with **Apply TAC linearization** ticked) linearizes photons automatically at read
time through the single `staging.open_tttr` seam, so previews here and production
reads match.

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
