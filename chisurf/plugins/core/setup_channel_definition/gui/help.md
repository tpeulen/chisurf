# Setup: Channel Definition

Describe how the photons of an instrument are routed: which routing channels belong to which
detector, which micro-time windows are the PIE excitation windows, how the TTTR files are read,
which TAC linearization tables apply, and what the optical path looks like. A saved **setup**
keeps all of it under one name, so the analysis tools only have to be told which setup to use.

## The toolbar

| Control | Does |
|---|---|
| **Setup** | Choose a saved setup. Its detectors, PIE windows, reading routine, LUTs and optical setup replace the working definition. *Unsaved* is the working definition with no name. |
| **Save** | Asks for a name and stores the working definition. An existing name is overwritten. |
| **Rename** | Gives the selected saved setup another name; a name already in use asks before it overwrites. |
| **Delete** | Deletes the selected saved setup after asking. The tables keep showing the definition. |
| **Public** | Makes a saved setup visible to every user of the MMFDB when you press Save. Only the owner of a saved setup can change it. |
| **Calibration** | Applies a stored calibration snapshot of the selected setup (G factor, l1, l2) to the detectors. *Latest* leaves the factors as they are. |

The same actions are also on the **Setups** tab, together with *Load setups file* and
*Export setups file*, which switch to, or write, a JSON library instead of the MMFDB.

## The six tabs

* **Setups** manages the named setups and the calibration history.
* **TTTR reading** sets the file type, the macro-time and micro-time ticks and the micro-time
  binning. *Read TTTR header and decay* takes the timing from a measurement and plots the decay of
  every routing channel with the PIE windows and detector gates on top; drag the lines to move them.
* **Detectors** lists each detector with its routing channels, micro-time ranges, G factor, l1, l2
  and the channel range the G factor is calculated from. *Polarization resolved* says that paired
  routing channels are parallel and perpendicular.
* **PIE windows** defines the excitation windows in TAC channels.
* **TAC corrections** assigns, computes and exports a linearization table (LUT) per routing channel
  and sets a micro-time shift. *Apply TAC LUTs and shifts* switches them on for every read; adding a
  LUT switches it on for you.
* **Optical setup** describes lasers, filters, fluorophores and detectors for the light-path
  simulation.

## Units of the micro-time ranges

PIE windows (*Start*, *End*) and detector *Micro-time ranges* are in **raw micro-time channels** of
the TTTR file, the same units as the plot. They are not divided by the micro-time binning. A range
such as 0:256 on data that spans 0:4095 selects almost no photons.

## Further reading

* [TTTR micro-time LUT](docs/guides/37_tttr_microtime_lut.md)
