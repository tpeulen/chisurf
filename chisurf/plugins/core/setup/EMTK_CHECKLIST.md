# Settings hub: emtk checklist

- The hub opens on Getting Started and lists the 15 Qt destinations (same names, same order, name search, Back / Next / fast-forward, Guide and ?, status line).
- Every destination hosts the dedicated accepted emtk app of its tool (Getting Started, Styles, Plots, Models, User Editor, AI Settings, Plugins, Updates, Packages, Channel Definition, FCS Definitions, TTTR LUT Tools, Plugin Check); Acquisition and ChiSurf Settings are panels of this plugin (`gui/acq_app.py`, `ConfigurationApp`). The generic file editor serves only ChiSurf Settings.
- Hosting forwards pointer, wheel, keys, key release, focus loss and file drops to the open panel; panels keep their state while others are shown; the open destination is remembered.
- Evidence, checklist, deliberate differences and gaps: `okf/plugins/emtk-ports/setup/REPORT.md`.
