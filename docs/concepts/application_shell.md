---
type: Concept
title: 'The application shell: settings, interface, account, help and hubs'
description: What the shell around the analysis tools holds as state, which of it is per user and which per machine, and where calculators and wizards sit in the menus.
tags: [concepts, application, settings]
anchor: concept-application-shell
---

(concept-application-shell)=
# The application shell: settings, interface, account, help and hubs

The shell holds no measurement. It holds the state that decides how a measurement is analysed and shown, and it
separates that state by owner.

| State | Owner | Lives in | Changed by |
|---|---|---|---|
| Settings (language, paths, plots, styles, models) | the machine | `settings_chisurf.yaml` | Settings (`chisurf/plugins/core/setup/`) |
| Interface (menu bar or ribbon) | the machine | the same file, restored at start | Menu Switch (`chisurf/plugins/core/menu_switch/`) |
| Account | the MMFDB user | the `mmfdb` section; the password is never stored | Switch User (`chisurf/plugins/core/switch_user/`) |

A result computed under one setting is not comparable with one computed under another unless the setting is recorded;
that is why settings are typed fields of one file and not dialog state, and why every container records the complete
settings of the operation that wrote it ([photon container](photon_container.md)). The account decides which records
the database lets you change ([measurement database](measurement_database.md)); the interface changes nothing but the
window.

## Calculators and wizards

A calculator maps parameters to a number or a curve without data: $R_0$ and $E(R)$, a phasor, the PSF volume. A wizard
chains several tools with a fixed order of decisions. A tool is an entry in its menu group, not a page inside a
launcher; Calculators (`chisurf/plugins/calculator/hub/`) and Wizards (`chisurf/plugins/core/wizards/`) still list
their members in one window, and every member is also reachable from its own menu entry.

## Help

The documentation browser (`chisurf/plugins/core/help/`) shows these pages, routes a link to a page to itself and a URL
or DOI to the system browser, and answers questions from the same pages ([asking the documentation](../guides/70_ask_the_documentation.md)).

See the [workflow](../guides/105_application_shell.md); the identity of the running build is in
[application identity](application_identity.md).
