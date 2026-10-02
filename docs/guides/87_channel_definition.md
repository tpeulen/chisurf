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
| Detectors | table, **Add**, **Polarization resolved** | Name, routing channels, micro-time ranges, G factor, l1, l2, G-factor channels; **Calc G** calculates the G factor from the read decays, **Delete** removes the detector. |
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
