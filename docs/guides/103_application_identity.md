---
type: Guide
title: Application details for a support request
description: Read and copy the running ChiSurf version and contact information with the native About tool.
tags: [guides, application, identity]
---

# Application details for a support request

Open **Help → About ChiSurf**, or start the window on its own with `pixi run -e test python -m chisurf.emtk --plugin about`.

```{figure} figures/about_application_details.png
:width: 380px

About ChiSurf: logo, version, developer contact and repository, with **Help**,
**Copy details**, **Guide** and **Close**.
```

1. Open **Guide**, then press the highlighted **Help** yourself. Read the field
   meanings and close Help (Escape closes the foreground help window).
2. Advance and press **Copy details**. A success copies the displayed application
   fields; paste them into a support request yourself. If the clipboard is
   unavailable, the guide reports it and waits for a successful retry.
3. Advance and press **Close**. The final action acknowledges and ends the tour
   before the About window closes. The main application remains open.

Opening this window or guide does not copy anything, send email, open a website
or load analysis data. Include the actual steps and input/settings needed to
reproduce your issue separately. [Application identity](../concepts/application_identity.md)
explains the scope; [About reference](../reference/plugins/about.md) documents the controls.

For a headless Python inspection without writing the clipboard:

```python
from chisurf.plugins.core.about.gui.app import make_app

app = make_app()
print(app.details_text())
app.request_close()
```

Tool: About ChiSurf (`chisurf/plugins/core/about/`).
