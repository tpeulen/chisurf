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

## 5. Package Manager

**Package Manager** opens a window with four pages and an operation log. Every call reaches the same solver
(micromamba, mamba or conda) the updater uses; nothing runs before you press a button, and the destructive ones ask first.

```{figure} figures/updater_pm_installed.png
:name: fig-updater-pm-installed
:width: 100%

**Installed Packages**: the packages of the current environment (here a fake list). **Filter** keeps the names that contain the
text; click a header to sort. **Update Selected** needs a selected row, **Update All** and **Remove Selected** ask first.
```

1. **Installed Packages** - filter, sort, select a row, **Update Selected**, **Update All**, **Remove Selected**, **Refresh List**.
2. **Search & Install** - type a package name and press Enter (or **Search**); results are listed newest version first.
   Select a row and **Install Selected** (it asks first).

```{figure} figures/updater_pm_search_results.png
:name: fig-updater-pm-search
:width: 100%

**Search & Install** after a search for `numpy`: one row per version and channel, a row selected.
```

3. **Environments** - **Create New**, **Clone Selected** (they ask for a name), **Remove Selected** (asks first),
   **Export to File** (a save dialog; writes the selected or the current environment as YAML) and **Import from File**
   (pick a file, then an optional name).

```{figure} figures/updater_pm_envs.png
:name: fig-updater-pm-envs
:width: 100%

**Environments** with the name entry of **Create New** open.
```

4. **Channels** - **Add Channel** (a name or URL) and **Remove Selected**.

The **Operation Log** under the pages lists every step with its time; a failed operation also opens an error message with
the solver's reason. **Refresh All** reloads the three lists. One row can be selected at a time (the Qt dialog allowed several);
install or remove packages one after the other.

## Headless / Python

```python
from chisurf.plugins.core.updater import check_for_updates
available, latest, error = check_for_updates()
```

Package management is the **Package Manager** window above.
