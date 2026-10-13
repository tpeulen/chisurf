# Trace Browser

Browse the PTU/TTTR point measurements of a folder: list them, rate (0-3) and annotate every file, show the binned
intensity trace of the selected file (one line per detector and their sum, plus the count histogram), and export,
report on, delete or hand off the selection.

* **Window**: an emtk app (`gui/app.py`, state and work in `gui/model.py`, form in `gui/trace_browser_emtk.view.json`);
  it is the only window (the Qt tool was retired). Help: `gui/help.md`, tour: `gui/guide.json`.
* **Input**: a detector setup (setup page) and a folder of TTTR files. Ratings and notes are stored beside the data in
  `.trace_browser_meta.json`; traces are cached in `.tttr_trace_cache`.
* **Output**: Export copies the selected files; CSV writes one `<stem>_trace.csv` per file (time, one column per
  series); DOCX writes `<folder>.docx` (needs `python-docx`); Delete moves files and their same-stem companions to
  `.trash` after a confirmation; HMM / TW / NDX hand the first selected file to Intensity Trace, TTTR Time Window and
  ndX (requests `open_intensity_trace`, `open_time_window`, `open_ndxplorer`). `gui/handoffs.py` turns each into a
  plugin hand-off (`chisurf.core.plugin.handoff`) to the payload kind the target declares in its manifest `accepts`
  (`tttr_trace`, `tttr_files`, `open_path`); the emtk shell opens the tool as a dock and hands it the payload once it is
  built. `make_app()` takes it when the shell is open (an explicit `make_app(on_request=...)` wins) and the three
  buttons are greyed without it.
* **Headless**: `trace-browser list|load|export-csv|contract` (see `cli/`), RPC methods in `manifest.json`.
* **Tests**: `pytest chisurf/plugins/tttr/trace_browser`. Guide: [Binned photon traces](../../../../docs/guides/22_binned_photon_traces.md).
