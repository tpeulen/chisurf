# Welcome to ChiSurf: the first-run wizard

A short, directed setup for a new ChiSurf installation. It looks after your **user settings folder**
(`~/.chisurf`), the list of fitting models, the optional Python packages, and the two kinds of
instrument definition most analyses need: a **detector setup** and, for FCS, **channel pairs**.
Nothing has to be completed in order: **Next** and **Back** only move between steps, and you can run
the wizard again at any time from the Plugin Manager.

## Walking the steps

The list on the left shows every step. A check mark means the step needs nothing more from you; a
step without one still has something to do. Click a step to go there, or use **Back** and **Next**.
**Finish** appears on the last step and closes the wizard.

| Step | What it does |
|---|---|
| **Welcome** | Says what the wizard is for. **Open settings folder** shows your settings in the file manager. |
| **Settings** | A table of the settings files and stores: **OK**, **MISSING**, the metadata store and how many detector and FCS setups exist. **Refresh** re-checks; **Open settings editor** opens the settings editor of the main window. |
| **Fix / Initialize** | **Create missing files** writes only files that do not exist yet. **Restore defaults (overwrite)** replaces your settings files by the packaged defaults and asks first, because settings you changed are lost. |
| **Experiments** | **Update experiments** copies the packaged `experiment_configs.yaml` over yours so new fitting models appear. Restart ChiSurf afterwards. |
| **Dependencies** | Which optional packages import (TTTR reading, plotting, Markdown, the 3D viewer). A missing one only disables the feature that needs it. |
| **Detector setup** | The editor of the Setup: Channel Definition tool: routing channels, PIE windows, timing, TAC corrections and the optical setup of your instrument. It is checked once a setup is saved. |
| **FCS channels** | The editor of the Setup: FCS Definitions tool: which logical channels, or channel pairs, a correlation uses. It is checked once a preset is saved. |
| **Finish** | Recommended next steps, with shortcuts to Help and the Plugin Manager. |

## Detector setup and FCS channels

These two steps host the same editors as the stand-alone tools, with the same stores: what you save
here is what the analysis tools list. The detector step has its own **Help** and **Guide** buttons;
so does the FCS step. In the FCS editor, **Close** leaves the editor and goes on to the last step.

## Notes

* **Open settings editor**, **Open Help** and **Open Plugin Manager** open windows of the ChiSurf main
  window. When the wizard runs on its own, they say where to find that window instead.
* The wizard writes only inside your settings folder.

## Further reading

* [Plugin catalogue](docs/reference/plugins/index.md)
