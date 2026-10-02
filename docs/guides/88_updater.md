---
type: Guide
title: Updating ChiSurf (Updater)
description: Checking whether a newer ChiSurf exists, reading what changed between versions, and installing a version with the package manager, in the window, with the startup switches.
tags: [guides, setup, updater]
---

# Updating ChiSurf (Updater)

**What you get:** the answer to "is there a newer ChiSurf, and what changed?", and a
button that installs it. ChiSurf is installed as a conda package; the updater asks the
update server which versions exist, compares the newest with the installed one, reads the
changes from the project's commit history, and runs the package manager (micromamba,
mamba or conda) to install the version you pick.

## 1. Open the tool

The updater is a panel of **Setup → Settings → Updates**. It opens with a check by itself.

```{figure} figures/updater_checked.png
:name: fig-updater-checked
:width: 100%

The updater after a check (on a fake release list): the installed version, the status line, the
solver that would run the update, the startup switches, the version list and the changelog.
```

## 2. Check, pick, read

1. Press **Check for Updates**. The status line says *Update available: version ...* or that
   ChiSurf is up to date; **Available versions** fills with what the server lists, newest first.
2. Choose a version in **Available versions**. The changelog shows the commits between the
   previous listed version and the chosen one (the oldest entry: since your installed version).
3. Links in the changelog open in your browser.

## 3. Update Now

**Update Now** asks first: the update closes all ChiSurf windows and continues in a separate
window, so unsaved work is lost; you start ChiSurf again yourself afterwards. Answer **No** to
stay as you are. It is greyed until a check has found a version.

## 4. Startup behavior

**Check for updates on startup** and **Ignore updates (do not prompt on startup)** are saved at
once to the `plugins.updater` section of your settings file. **Development** is on and fixed:
there is no stable release yet, so the changelog is read from the development branch.

## Headless / Python

```python
from chisurf.plugins.core.updater import check_for_updates
available, latest, error = check_for_updates()
```

Package management (installed packages, search, environments, channels) is the **Package
Manager** button; its native window follows with the next step of the port.
