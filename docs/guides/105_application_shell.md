---
type: Guide
title: 'Working in the shell: interface, account, calculators and wizards'
description: Show or hide the ribbon, sign in as another MMFDB user, and find the calculators and wizards in the Tools tab.
tags: [guides, database, mmfdb]
---

# Working in the shell: interface, account, calculators and wizards

**Tools:** Menu Switch (`chisurf/plugins/core/menu_switch/`), Switch User (`chisurf/plugins/core/switch_user/`),
the calculators (`chisurf/plugins/calculator/`, `chisurf/plugins/fret_line/`, `chisurf/plugins/core/f_test/`) and wizards
(`chisurf/plugins/fluorescence_decay/tr_anisotropy/`, `chisurf/plugins/core/batch_analysis/`). Theory:
[the application shell](../concepts/application_shell.md).

## 1. Menu bar or ribbon

*Setup → Menu Switch* shows or hides the ribbon of the open main window and opens no window of its own;
the menu bar stays either way. The choice is saved and restored at
the next start. Without a main window (a headless run) it reports that nothing changed and why.

## 2. Another account

*Setup → Switch User* is the login form of the MMFDB.

1. Enter **Server** and **Port** (for a remote MMFDB its http or https **MMFDB URL**), pick **User**, type **Password**.
2. Press **Login**. A refusal shows **Login Failed** and changes nothing.
3. **Save selected user** makes the account the default; **Log in automatically when allowed** keeps a session token in
   the operating system's credential store. The password is never stored.

What the account may change is decided by the database ([MMFDB Admin](102_mmfdb_admin.md)).

## 3. Calculators and Wizards

Each calculator and each wizard is a button of the *Tools* tab and opens as a tab beside the Workspace.

- *Tools → Calculators*: F-Test, FCS Saturation, FRET Calculator (hetero- and homoFRET), FRET Line Generator, Kappa2
  Distribution, Light Path Simulator, PSF Calculator, Phasor Calculator, RICS Precision, Spectra Downloader. See
  [FRET lines](82_fret_lines.md) and [the phasor calculator](77_phasor_calculator.md).
- *Tools → Wizards*: **Anisotropy Wizard** builds a linked VV/VH global fit
  ([lifetime and anisotropy](10_lifetime_anisotropy_fitting.md)); **Batch Analysis** applies one template fit to many
  files.

Where the ribbon is too narrow a group collapses into one button whose menu lists its tools.

Settings are in [the Settings window](97_settings_hub.md); version details in
[application details](103_application_identity.md).
