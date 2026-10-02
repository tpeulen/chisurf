# Light Path Simulator

The simulator follows light from the excitation source through the sample, the dichroics and filters, to the detectors, and
reports the detected signal of every fluorophore, the crosstalk between laser lines, dyes and detector channels, and the Förster
radius of every donor and acceptor pair. The spectra come from the MMFDB catalogue.

## Windows

* **Optical Path**: the graph. Drag nodes, drag from a pin to connect, scroll to zoom, right-click a node (rename, duplicate,
  delete) or the background (add a component, arrange, fit). The toolbar above it saves and loads graphs.
* **Optical Components**: the list of components to add, Reset to Default, the graph view buttons, the backend settings and a
  numeric form to connect two ports.
* **Easy Mode**: the same path as a form (lasers, excitation dichroic, dyes, splitters, detectors). It edits the graph.
* **Emission Probability**: Calculate Emission Intensity and the result tables.

## Simulating

Press Calculate Emission Intensity. With Auto update on (Backend), every edit queues a new simulation. Stop appears while a
backend call runs. The tables are Signals (detected intensity per laser, detector and dye), Excitation, Emission, Detected and
the Förster radius.

## Files

Save Graph and Load Graph use JSON files (a dropped `.json` file loads too). Save Preset stores the graph under a name for Easy
Mode. Save to MMFDB and Load from MMFDB keep simulations in the database. Export Instrument writes the simulated instrument
setting once a simulation exists.

## Further reading

* [Light path crosstalk and R0](okf/usecases/lightpath-crosstalk-r0.md)
