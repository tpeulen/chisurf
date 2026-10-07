# Detector setup: channels, PIE windows, timing and LUTs

**Tool:** *Setup → Channel Definition* (`setup_channel_definition`); the same editor is embedded in the
[image browser](86_image_browser.md), the burst tools, the count-rate and trace tools and the onboarding wizard.

Every analysis of photon streams has to know which **routing channel** is which **detector**, which part of the
micro-time axis is the **excitation window** (PIE window), how a file is **read** (container format, macro- and
micro-time tick) and whether a **TAC linearization table (LUT)** has to be applied. A **setup** stores all of it under one
name, so a tool only has to be told which setup to use. Micro-time ranges are in **raw micro-time channels** of the file
(not divided by the binning): a range `0:256` on data that spans `0:4095` selects almost no photons.

## 1. The page

```{figure} figures/channel_definition_page.png
:name: fig-channel-definition-page
:width: 100%

The editor with a BH SPC-132 measurement read: Setup row, TTTR Reading routine, Detectors (PIE Windows is folded), LUT handling and Optical Setup....
```

One page, four folding sections (click a header to fold it; which are open is remembered):

| Where | Control | What it does |
|---|---|---|
| Setup row | **Setup**, **Save**, **Rename**, **Delete** | Choose a saved setup (the one used last opens at start); Save, Rename and Delete ask in a small prompt. |
| | **Public** | Make the saved setup visible to all users of the MMFDB with the next Save; only its owner can. |
| | **Calibration** | Apply a stored G/l1/l2 snapshot of the selected setup to the detectors; *Latest* leaves them. |
| | **?** (red) | Explains the page. |
| TTTR Reading routine | **File Type** | *Auto* or a container (PTU, HT3, SPC-130, SPC-600, PHOTON-HDF5, CZ-RAW, SM, PHOTONS, SPC-QC, BRIGHTEYES-TTR, FLIMLABS, PTO). |
| | **Read** | Take the macro and micro time from a measurement and the decay of every routing channel. |
| | **Macrotime res. (ns)**, **Microtime res. (ps)**, **Microtime binning**, **Eff. microtime (ps)** | Type numbers; the effective tick is read-only. |
| | **Plot** | The decay of each routing channel with the PIE windows and detector gates; drag a line to move a range. |
| PIE Windows | table, **Add** | Window name, start, end; **Delete** removes a row. |
| Detectors | table, **Add**, **Polarization resolved** | Name, routing channels, micro-time ranges, G factor, l1, l2, G-factor channels; **Calc G** opens calibration from an independent TTTR reference, **Delete** removes the detector. |
| bottom actions | **Preview G** | Estimate G from the already loaded preview for the selected detector (the first detector if none is selected). This updates the working G without archival and clears its old calibration identifiers. |
| LUT handling | **Apply TAC linearization (LUT) when reading** | Switch the linearization on for every read (adding a LUT switches it on). |
| | table, **Assign LUT...**, **Configure LUTs...**, **Adjust shifts...** | A LUT file and a micro-time shift per routing channel. |
| bottom right | **Optical Setup...** | The light-path editor: lasers, filters, fluorophores, detectors. |

## 2. Typing into a table

Double-click a cell, type, and press **Enter** (or click elsewhere) to commit it; Escape cancels. Ranges are `start:end`
(`0:4095`), several separated by `,` or `;` (`0:10;20:30`); a reversed range (`20:10`) is swapped and a single number
`5` is the range `5:5`. Channels are integers separated by commas. An empty G factor is 1.0; text that is not a number
keeps the old value and says so in the status line.

```{figure} figures/channel_definition_plot.png
:name: fig-channel-definition-plot
:width: 100%

**Plot** opens the micro-time decay of the routing channels; the vertical lines are the PIE windows and detector gates and can be dragged.
```

## 3. Steps

1. Press **Read** and choose a measurement of your instrument; the timing and the decays appear.
2. Edit the **Detectors** (and, if the setup uses them, the **PIE Windows**) until **Plot** shows the gates on the
   intended part of the decay.
3. For SPC data with differential non-linearity, assign or compute a **LUT** per channel
   ([guide 37](37_tttr_microtime_lut.md)) and tick **Apply TAC linearization (LUT) when reading**.
4. **Save**, give the setup a name. Every tool that offers a **Setup** choice lists it.

A drop works too: drop a measurement on the window to read it, a `.json` file to switch to that setups library.

## 4. From Python

```python
from chisurf.core.setup_channel_definition import ChannelDefinition

setup = ChannelDefinition(file_path="my_setups.json")
setup.refresh_setups()
setup.select_setup("ALEX Suite (auto)")
settings = setup.get_settings()          # detectors, windows, tttr_reading, LUTs, optical setup
```


## 5. Edit the complete working definition

**Edit JSON...** opens the complete detector definition in the native editor.
The draft includes windows, detectors, timing, LUTs, optical settings and
additional metadata. **Apply** validates it before replacing the working
definition and refreshing the page. An invalid draft shows its error and
keeps the previous definition. **Cancel** discards the draft; read-only
definitions cannot be edited.

Apply does not save a named setup or write a calibration to MMFDB. Use
**Save** separately when you want to persist the valid working definition.
Metadata and calibration identifiers remain unless you explicitly change
or remove them in the complete draft.

```{figure} figures/channel_definition_json_editor.png
:name: fig-channel-definition-json
:width: 100%

The native complete-definition editor after reading the BH SPC-132 fixture.
Apply and Cancel act on the draft; saving the named setup remains separate.
```


## 6. Independent reference calibration

Press **Calc G** in the detector's row (**G** in a compact pane) and choose a
TTTR measurement of a fast-rotating reference. A timing-only `.set` header
is rejected because it contains no reference photons. This reference is read
on a private copy of the setup: the working definition's loaded measurement,
preview and timing stay in place. The setup's routing-channel order alternates
parallel and perpendicular channels; the reference combines entries 1, 3, …
into VV and entries 2, 4, … into VH, with the configured LUTs, shifts and
micro-time binning. The native [VV/VH calculator](91_vv_vh_g_factor.md) then
provides tail, background, fractional VH shift, channel flip, manual G,
slow-reference mixing and uncertainty controls.

If **G-Factor Channels** contains a valid saved tail, the prompt offers
**Run headlessly**, **Open calculator** and **Cancel**. Run headlessly uses the
prepared reference and saved tail, archives the result and applies it without
opening the calculator. Without a saved tail, the calculator opens for you to
choose and inspect one. **Apply calibration and close** queues closure even
while a field edit is committing and recomputation is pending; it publishes
the completed result after that computation finishes. Closing a nested Help
window or file chooser with Escape leaves the calculator open. Closing a
completed, valid calculator also publishes it. Use
**Discard calibration** to close without applying it. A cancelled read, busy
closure, invalid result, error or read-only definition leaves the working
detector calibration unchanged.

Changing the selected setup or reloading the fast input inside the calculator
invalidates the captured detector handoff. Start a new **Calc G** TTTR workflow
to establish its timing and raw-channel provenance. The calculator's own
file/export/archive controls remain available for its standalone decay workflow.

```{figure} figures/channel_definition_reference_calibration.png
:name: fig-channel-definition-reference
:width: 100%

The native calculator embedded in the detector editor, driven with the measured
BH SPC-132 photon fixture, binning 2 and the fixture's channel-0 shift of 2. The
shown tail 425–925 maps to raw channels 850–1850; its G 1.32776 and SD 0.456709
are workflow results for these inputs, not measured calibration ground truth.
The active setup's timing remains separate from the independent reference clock.
```

```{figure} figures/channel_definition_reference_mixing.png
:name: fig-channel-definition-reference-mixing
:width: 100%

Scrolling reveals the mixing controls and results. Manual 0.12 is an explicit
handoff example; no slow reference is loaded, so the automatic mixing result
correctly remains unavailable. It is not a measured mixing estimate.
```

The detector page stores tail endpoints in **raw TAC channels**. The calculator
plots and edits **binned histogram bins**: with binning B, raw endpoints are
divided by B on entry and the final calculator endpoints are multiplied by B
and stored as raw integer endpoints on application. For example, raw channels
850–1850 become calculator bins 425–925 when B = 2. Its slow-reference
**dt** is initialized from the reference's effective micro-time tick:
raw tick in ps × B × 0.001 gives ns per calculator bin.

Application archives the reference, corrected traces and calibration
parameters under the configured MMFDB calibration actor. The archive records
G, its calculated SD, background, shift, flip, mixing and source/provenance
information; the detector receives G, l1/l2, the raw tail,
`g_factor_decay_uuid` and `g_factor_calibration_id`. Missing or nonphysical
automatic mixing retains its prior l1/l2; an explicit manual zero replaces
them. Existing unrelated detector metadata is retained.

Archival must return both reference and calibration identifiers before the
working detector is updated. An already saved setup owned by the configured
actor is persisted as part of that handoff; otherwise use **Save** separately
to store the working definition. If a later named-setup save fails, the
working detector is restored, but the successful archive may already contain
the reference/calibration records. **Preview G** remains a separate, quick
loaded-decay estimate: it does not perform this reference archival.
