# Detector setup: channels, PIE windows, timing and LUTs

**Tool:** *Setup → Channel Definition* (`setup_channel_definition`); the same editor is embedded in the
[image browser](86_image_browser.md), the burst tools, the count-rate and trace tools and the onboarding wizard.

Every analysis of photon streams has to know which **routing channel** is which **detector**, which part of the
micro-time axis is the **excitation window** (PIE window), how a file is **read** (container format, macro- and
micro-time tick) and whether a **TAC linearization table (LUT)** has to be applied. A **setup** stores all of it under one
name, so a tool only has to be told which setup to use. Micro-time ranges are in **raw micro-time channels** of the file
(not divided by the binning): a range `0:256` on data that spans `0:4095` selects almost no photons.

The [detector-setup concept](../concepts/detector_setup.md) explains the routing,
raw-channel gates, timing units and calibration assumptions. Existing ChiSurf
windows and wizard pages host the same native editor; their surrounding Qt
navigation does not provide a second detector-definition implementation.

## 1. The page

```{figure} figures/channel_definition_page.png
:name: fig-channel-definition-page
:width: 100%

The native page after reading the measured BH SPC-132 fixture, with an explicit
validation definition: green routes 0/1 and red routes 8/9, two detectors and
raw-channel PIE windows. The provider/header-derived 13.5 ns macro-time and
3.2958984375 ps micro-time values are not independently verified instrument
calibration. An identity LUT and channel-1 shift of +2 demonstrate preservation
of configured corrections, not a measured TAC calibration.
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

### Save a setup, export a definition or export a library

The Setup row's **Save** persists the working definition under a setup name.
**Save definition...**, where the hosting workflow exposes it, exports one
complete working definition as JSON, including its additional metadata.
**Import setups library...** and **Export setups library...** instead read or
write the named library and its last-used selection. A definition input file
and the named-library destination are separate.

In a wizard that starts with **Finish** disabled, only a successful complete
definition export enables Finish. Cancelling the file chooser, a write error,
or named Setup **Save** leaves that completion state unchanged. The definition
export may also update the selected saved setup when the current actor owns it;
if that follow-on save fails, the export file may already exist, but Finish is
not enabled. Existing embedded callers retain their own initial completion
policy.

```{figure} figures/channel_definition_wizard_after_export.png
:name: fig-channel-definition-wizard-export
:width: 100%

The real enclosing wizard after **Save definition...** exports the complete
working JSON: the status confirms success and **Finish** is enabled. Its native
page area is 1396×898, with the same two-detector BH validation definition,
provider-derived timing and +2 channel shift. No named setup was saved here;
the Setup row still says Unsaved. Definition export and named Setup Save are
distinct operations.
```

## 4. From Python

```python
from chisurf.core.setup_channel_definition import ChannelDefinition

setup = ChannelDefinition(file_path="my_setups.json")
setup.refresh_setups()
setup.select_setup("ALEX Suite (auto)")
settings = setup.get_settings()          # detectors, windows, tttr_reading, LUTs, optical setup
```

`ChannelDefinition.export_definition(path, update_named=False)` writes a
complete portable definition; updating a named setup is an explicit separate
option. `save_setup(name, public=False)` uses the existing named store and
ownership rules. These operations retain unknown metadata rather than
reconstructing a reduced detector-only object.

### Developer API for an embedded native page

The public `DetectorWizardPage` is a thin wizard-page host around the actual
native app and portable model. Consumers use `get_settings()`, `set_settings()`,
`channels()`, `detectors`, `windows`, `tttr_reading`, `update_detector(name,
values)`, `available_setups()` and `select_setup(name)`. Read a measurement with
`read_tttr(path)` and observe its asynchronous state through `read_running` and
`poll_read()`. A real definition edit emits `detectorsChanged`; micro-time
binning has its separate `micro_time_binningChanged` signal. Identical detector
updates are no-ops. Consumers should not reach into Qt table/combo-box fields.

The eight constructor visibility flags control existing native actions:

| Flag | Exposed controls |
| --- | --- |
| `show_edit_json` | Complete working-definition JSON editor |
| `show_save` | **Save definition...** export action |
| `show_setups_file` | Named-library import/export actions |
| `show_setup_selection` | Setup selection and named Save/Rename/Delete/Public/Calibration toolbar |
| `show_help` | Page help |
| `show_tttr_reading` | Reading routine, timing and preview controls |
| `show_tables` | PIE-window and detector sections and related table-toolbar controls |
| `show_add_inputs` | Add-window and add-detector inputs/actions |

These flags change visibility, not stored definitions or analysis defaults.
`model`, `settings`, `json_file` and `setups_file` choose the injected working
model/definition or library source; `allow_finish=False` requests the
successful-export completion policy described above.

The semantic `effective_micro_time_resolution` getter is in **picoseconds**,
including micro-time binning; `excitation_period` is in **nanoseconds**. A
consumer requiring ns converts that ps value once by multiplying by 0.001;
a provider/header path that already returns ns must not be converted again.
Acquisition provenance remains separate from an unsaved timing initializer.
See the [microtime workflow](89_microtime_histogram.md) for qualified provider
timing and [Burst MLE](21_lifetime_from_bursts.md) for its analysis workflow.


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

The native FCS channel-preset editor starts at 1100×720. Saved custom geometry
takes precedence. Detector definitions, correlation pairs and exported preset
bytes are independent of the window size.
