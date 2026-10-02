# Setup: Channel Definition

Describe how the photons of an instrument are routed: which routing channels belong to which
detector, which micro-time windows are the PIE excitation windows, how the TTTR files are read,
which TAC linearization tables apply, and what the optical path looks like. A saved **setup**
keeps all of it under one name, so the analysis tools only have to be told which setup to use.

## The Setup row

| Control | Does |
|---|---|
| **Setup** | Choose a saved setup. Its detectors, PIE windows, reading routine, LUTs and optical setup replace the working definition. *Unsaved* is the working definition with no name. The setup used last is opened when the tool starts. |
| **Save** | Asks for a name and stores the working definition. An existing name is overwritten. |
| **Rename** | Gives the selected saved setup another name; a name already in use asks before it overwrites. |
| **Delete** | Deletes the selected saved setup after asking. The tables keep showing the definition. |
| **Public** | Makes a saved setup visible to every user of the MMFDB when you press Save. Only the owner of a saved setup can change it. |
| **Calibration** | Applies a stored calibration snapshot of the selected setup (G factor, l1, l2) to the detectors. *Latest* leaves the factors as they are. |
| **?** (red) | Explains the page. |

## The page: one scroll, four sections

Click a section header to fold it; which sections are open is remembered. Drop a measurement on the
window to read it, a `.json` file to switch to that setups library.

* **TTTR Reading routine**: *File Type* (Auto detects the container; all formats of the reader
  are listed), *Read* (takes the timing from a measurement), *Macrotime res. (ns)*, *Microtime res.
  (ps)*, *Microtime binning* and the read-only *Eff. microtime (ps)*. *Plot* opens the decay of every
  routing channel with the PIE windows and detector gates on top; drag the lines to move them.
* **PIE Windows** (folded at first): the excitation windows in TAC channels, one row each; *Add*
  appends a window.
* **Detectors**: one row per detector with its routing channels, micro-time ranges, G factor, l1,
  l2 and the channel range the G factor is calculated from; *Calc G* calculates it from the loaded
  decays, *Delete* removes the detector, *Add* appends one. *Polarization resolved* says that
  paired routing channels are parallel and perpendicular. Double-click a cell, type, and press
  Enter (or click elsewhere) to change it. Ranges are `start:end`, several separated by `,` or
  `;` (`0:10;20:30`); a reversed range (`20:10`) is swapped.
* **LUT handling (TAC linearization)**: *Apply TAC linearization (LUT) when reading* switches the
  linearization on for every read (adding a LUT switches it on for you). The table lists each
  routing channel with its LUT and a micro-time shift. *Assign LUT...* assigns a file to the
  selected channel, *Configure LUTs...* computes, exports or removes one, *Adjust shifts...*
  aligns the channels on the decay.

*Optical Setup...* at the bottom right opens the light-path editor for lasers, filters,
fluorophores and detectors.

## Units of the micro-time ranges

PIE windows (*Start*, *End*) and detector *Micro-time ranges* are in **raw micro-time channels** of
the TTTR file, the same units as the plot. They are not divided by the micro-time binning. A range
such as 0:256 on data that spans 0:4095 selects almost no photons.

## Further reading

* [TTTR micro-time LUT](docs/guides/37_tttr_microtime_lut.md)
