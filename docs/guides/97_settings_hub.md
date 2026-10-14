---
type: Guide
title: 'The Settings window: one list, every settings panel'
description: 'Tool: Setup → Settings (setup). One window holds the Getting Started assistant and fifteen settings destinations.'
tags: [guides, settings]
---

# The Settings window: one list, every settings panel

**Tool:** *Setup → Settings* (`setup`). One window holds the **Getting Started** assistant and fifteen settings
destinations. Each destination is the dedicated panel of its own tool, hosted inside the window; nothing is a generic
file editor except the destination that edits `settings_chisurf.yaml` itself.

## 1. The window

```{figure} figures/97_settings_getting_started.png
:name: fig-settings-hub
:width: 100%

The Settings window on its first destination, Getting Started. Search box and list on the left, the hosted panel on the
right, **Guide** and **?** at the top right, the status line and **Back / >> / Next** at the bottom.
```

| Where | Control | What it does |
|---|---|---|
| Left | **Search...** | Type part of a destination's name: the list keeps the destinations whose name contains it. **Enter** opens the first match. The open destination stays open when it is filtered out. |
| Left | list | Getting Started, ChiSurf Settings, Fonts, Acquisition, Styles, Plots, Models, User Editor, AI Settings, Plugins, Updates, Packages, Channel Definition, FCS Definitions, TTTR LUT Tools, Plugin Check. The mouse wheel scrolls it when the window is too short for all of them. |
| Top right | **Guide** | A walkthrough that waits for you to type in the search box, pick a destination and press **Next**. |
| Top right | **?** | Explains the window. Every hosted panel has its own **Help** and **Guide** buttons as well. |
| Bottom left | status line | `Ready`, an error that stopped a panel from opening, or the progress of the fast-forward. |
| Bottom right | **< Back**, **Next >** | Previous / next destination in list order; greyed at the ends. |
| Bottom right | **>>** | Fast-forward: visit every remaining destination in order (the status line counts them, `Fast-forward n/m`); press again (now **||**), press **Back** or pick a destination to stop. |

The window opens on Getting Started and remembers the destination you left it on, and the state of every panel you
opened (an unsaved edit, a selected row, which sections are folded) while you look at another.

## 2. The destinations

| Destination | Panel | Figure |
|---|---|---|
| Getting Started | the eight-step onboarding assistant (settings, fix, experiments, dependencies, detector setup, FCS channels) | {numref}`fig-settings-hub` |
| ChiSurf Settings | the typed editor of `settings_chisurf.yaml`: **Language**, **Open file**, **Reload**, **Validate**, **Help**, **Save**, **Save as**, **Edit source**, **Find a setting**, typed fields | {numref}`fig-settings-chisurf` |
| Fonts | interface, editor and documentation fonts; magnification of the window | |
| Acquisition | output folder (**Browse...**), chunk size, real-time simulation, device type and the simulator's parameters; every change is stored at once | {numref}`fig-settings-acquisition` |
| Styles | the style-sheet editor ([Styles](../reference/plugins/style_manager.md)) | |
| Plots | curve colours and width, fit-range band, global fits, axes and grid, beside a live preview laid out like a fit window ([Plot settings](../reference/plugins/plot_settings.md)); a change applies at once and is saved; the wheel zooms the preview, a drag pans it | |
| Models | the model table with its search and detail pane | |
| User Editor | accounts of the MMFDB | |
| AI Settings | provider, models and generation settings ([AI settings](../reference/plugins/ai_settings.md)) | |
| Plugins | the plugin manager | |
| Updates | [Updating ChiSurf](90_updater.md) | |
| Packages | the conda package manager of the same tool | |
| Channel Definition | [the detector setup](87_channel_definition.md) | |
| FCS Definitions | channel pairs per detector setup | |
| TTTR LUT Tools | TAC linearization tables; photon files can be dropped on the panel | |
| Plugin Check | [plugin contracts](96_plugin_check.md) | |

```{figure} figures/97_settings_chisurf.png
:name: fig-settings-chisurf
:width: 100%

ChiSurf Settings with the language selector and the typed fields of the settings file.
```

The fields scroll below the fixed header (language, buttons, search) with the wheel or the scrollbar. Number fields
take typed text: Enter, a click elsewhere in the panel or **Save** commits it; a fraction typed into a whole-number
setting is refused and named in the status line.

```{figure} figures/97_settings_acquisition.png
:name: fig-settings-acquisition
:width: 100%

Acquisition. The simulator's per-species table, kinetics matrices and decay spectra stay in the Acquisition tool (**Tools → Views → Acquisition**)
and keep their stored values; the other simulator parameters are edited here.
```

## 3. Keyboard, wheel and files

The wheel scrolls the list under the pointer and the panel under the pointer (tables, forms) and zooms plots. Typed keys
go to the search box until you click into a panel, and to that panel afterwards. Files dropped on the window reach the
open panel (TTTR LUT Tools and Channel Definition read photon files).

## Theory

- [Detector setups](../concepts/detector_setup.md): the theory behind the Channel Definition panel.
- [Application identity](../concepts/application_identity.md): what the version and support details in the settings establish.

Tool: Settings (`chisurf/plugins/core/setup/`).

Tools: AI Settings (`chisurf/plugins/ai_settings/`), Plots (`chisurf/plugins/core/plot_settings/`), Styles (`chisurf/plugins/core/style_manager/`), Models (`chisurf/plugins/core/model_manager/`), User Editor (`chisurf/plugins/core/user_editor/`), Plugins (`chisurf/plugins/core/plugin_manager/`), Boarding Wizard (Getting Started) (`chisurf/plugins/core/boarding/`), Channel Definition (`chisurf/plugins/core/setup_channel_definition/`), FCS Definitions (`chisurf/plugins/fcs/fcs_channel_preset/`), LUT Tools (`chisurf/plugins/tttr/tttr_lut_tools/`), Updates & Packages (`chisurf/plugins/core/updater/`), Plugin Check (`chisurf/plugins/core/plugin_check/`).
