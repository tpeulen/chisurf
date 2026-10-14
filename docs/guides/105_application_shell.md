---
type: Guide
title: 'Working in the shell: interface, account and the two hubs'
description: Switch between menu bar and ribbon, sign in as another MMFDB user, and use the Calculators and Wizards hubs.
tags: [guides, database, mmfdb]
---

# Working in the shell: interface, account and the two hubs

**Tools:** Menu Switch (`chisurf/plugins/core/menu_switch/`), Switch User (`chisurf/plugins/core/switch_user/`),
Calculators (`chisurf/plugins/calculator/hub/`), Wizards (`chisurf/plugins/core/wizards/`). Theory:
[the application shell](../concepts/application_shell.md).

## 1. Menu bar or ribbon

*Setup → Menu Switch* toggles the open main window and opens no window of its own. The choice is saved and restored at
the next start. Without a main window (a headless run) it reports that nothing changed and why.

## 2. Another account

*Setup → Switch User* is the login form of the MMFDB.

1. Enter **Server** and **Port** (for a remote MMFDB its http or https **MMFDB URL**), pick **User**, type **Password**.
2. Press **Login**. A refusal shows **Login Failed** and changes nothing.
3. **Save selected user** makes the account the default; **Log in automatically when allowed** keeps a session token in
   the operating system's credential store. The password is never stored.

What the account may change is decided by the database ([MMFDB Admin](102_mmfdb_admin.md)).

## 3. Calculators and Wizards

*Tools → Calculators* has two entries.

- **Calculators**: pick FRET / homoFRET, FRET line, RICS precision, Phasor plot, κ² distribution, F-test / χ²-max, FCS
  Saturation or PSF calculator on the left; it appears on the right. See [FRET lines](82_fret_lines.md) and
  [the phasor calculator](77_phasor_calculator.md).
- **Wizards**: Anisotropy builds a linked VV/VH global fit ([lifetime and anisotropy](10_lifetime_anisotropy_fitting.md));
  Batch analysis applies one template fit to many files.

Settings are in [the Settings window](97_settings_hub.md); version details in
[application details](103_application_identity.md).
