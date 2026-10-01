# Trace Browser

Browse the PTU/TTTR point measurements of a folder: list them, rate (0-3) and annotate every file, show the binned
intensity trace of the selected file (one line per detector and their sum, plus the count histogram), and export,
report on, delete or hand off the selection.

* **Window**: an emtk app (`gui/app.py`, state and work in `gui/model.py`, form in `gui/trace_browser_emtk.view.json`);
  the Qt tool (`gui/tool.py`, `widget.py`) is kept as the fallback. Help: `gui/help.md`, tour: `gui/guide.json`.
* **Input**: a detector setup (setup page) and a folder of TTTR files. Ratings and notes are stored beside the data in
  `.trace_browser_meta.json`; traces are cached in `.tttr_trace_cache`.
* **Output**: Export copies the selected files; CSV writes one `<stem>_trace.csv` per file (time, one column per
  series); DOCX writes `<folder>.docx` (needs `python-docx`); Delete moves files and their same-stem companions to
  `.trash` after a confirmation; HMM / TW / NDX hand the first selected file to Intensity Trace, TTTR Time Window and
  ndX (requests `open_intensity_trace`, `open_time_window`, `open_ndxplorer`). `gui/host.py` fulfils them by opening an
  Intensity Trace window, the Time Window tool and ChiSurf's ndX window; `make_app()` finds it when a Qt application runs
  (an explicit `make_app(on_request=...)` wins) and the three buttons are greyed without one.
* **Headless**: `trace-browser list|load|export-csv|contract` (see `cli/`), RPC methods in `manifest.json`.
* **Tests**: `pytest chisurf/plugins/tttr/trace_browser`. Guide: [Binned photon traces](../../../../docs/guides/22_binned_photon_traces.md).
