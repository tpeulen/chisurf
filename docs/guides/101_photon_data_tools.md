---
type: Guide
title: The photon-data tools and count rates (Tools › Photon data)
description: 'Where the photon-level TTTR tools live (Tools › Photon data: ALEX Creator, Audifier, Count Rate Analysis, Microtime Shifter, Photon Table), which clock each one acts on, how each tool keeps its own detector setup, and a count-rate check across many files from the GUI, the CLI and Python.'
tags: [guides, tttr, photons, file-formats]
---

# The photon-data tools and count rates (Tools › Photon data)

**What you get:** the tools that act on a photon stream before an analysis interprets it, each a button of its own in
the **Tools** ribbon tab, group **Photon data**, and a per-detector count-rate check over many files.

```{figure} figures/photon_data_ribbon.png
:name: fig-photon-data-ribbon
:width: 100%

The **Tools** ribbon tab. The **Photon data** group holds ALEX Creator, Audifier, Count Rate Analysis, Microtime
Shifter and Photon Table. Each opens as its own dock; the **Tools** menu and the tool tree list the same entries.
```

## Which tool for which clock

A TTTR record holds the **macro time** (when the photon arrived on the free-running clock) and the **micro time** (how long
after the laser pulse). Bursts and correlations use the first, lifetimes and decays the second
([the two clocks](../concepts/tttr_stream_tools.md)).

| tool | acts on | guide |
|---|---|---|
| **ALEX Creator** | folds macro-time alternation into the micro time | [ALEX Creator](100_alex_creator.md) |
| **Microtime Shifter** | shifts the micro time per detector | [Micro-time shifter](88_microtime_shifter.md) |
| **Photon Table** | lists the records, changes nothing | [Photon Table](108_photon_table.md) |
| **Count Rate Analysis** | counts photons per detector over the macro time | below |
| **Audifier** | plays the stream, draws its micro-time waterfall | [Audifier](94_tttr_audifier.md) |

File-level operations (split and convert, header editing, `.pto` packing, time windows) are in **File › Data**.

## Detector setups

Count Rate Analysis and Audifier read photons per **detector**, so each carries the full detector editor (routing
channels, PIE windows, reading routine, LUTs). A setup saved there (**Save**, with a name) goes into the setup library
that every tool reads, so define it once and pick it by name in the next tool. **File › Setup › Settings** edits the same
library.

## Count rates over many files

1. **Tools › Photon data › Count Rate Analysis**.
2. In **Detector channels**, pick a saved **Setup** or define the detectors: set the **File Type**, add a detector and
   enter its routing channels.
3. **Add files** (or **Folder…**, or drop files on the list) to queue the measurements.
4. Press **Calculate**. **Count rate per file** plots one point per file and detector; **Results per channel** gives the
   mean, the standard deviation, the photon count and the measurement time. **Save** writes the table.

A detector that died mid-session, a sample that bleached or a file recorded with the shutter closed shows up here as an
outlier file.

```{figure} figures/photon_data_count_rate.png
:name: fig-photon-data-count-rate
:width: 100%

Count Rate Analysis on its own after **Calculate** on three SPC-132 dsDNA files (`m000.spc`–`m002.spc`). Detector `green`
reads routing channels 0 and 1 with the SPC-130 reading routine: 1.18 ± 0.07 kHz over 196.96 s, 231 669 photons.
```

Headless, the `count-rate` command does the same:

```bash
csc count-rate list-setups setups.json
csc count-rate analyze --setup-file setups.json --setup-name green -o rates.txt m000.spc m001.spc m002.spc
```

and in Python, through the tool itself:

```python
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

app = create_app()
tool = app.tool
tool.channel_editor.load_definition({
    "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0}},
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
})
tool.add_paths(["m000.spc", "m001.spc", "m002.spc"])
tool.calculate()
```

{src}`docs/guides/screenshots/photon_data_tools_shot.py` runs this on the bundled files and draws both figures.

## Rules of thumb

1. These tools write new files; keep the originals. A micro-time shift cannot be undone once its value is forgotten.
2. Check the count rates before an analysis.
3. After a micro-time shift, look at the IRF again.

Tools: ALEX Creator (`chisurf/plugins/tttr/ptu_alex_creator/`), Audifier (`chisurf/plugins/tttr/audifier/`),
Count Rate Analysis (`chisurf/plugins/tttr/tttr_count_rate_analysis/`), Microtime Shifter
(`chisurf/plugins/tttr/tttr_microtime_shifter/`) and Photon Table (`chisurf/plugins/tttr/photon_table/`).

## See also

- [Handling TTTR files](12_handling_tttr_files.md)
- [Plugin reference: Count Rate Analysis](../reference/plugins/tttr_count_rate_analysis.md)

## Theory

- [The two clocks of a photon record](../concepts/tttr_stream_tools.md)
- [The photon container](../concepts/photon_container.md): what a TTTR measurement stores, which the photon tools read and rewrite.
- [Micro-time shift](../concepts/microtime_shift.md): why the micro-time shifter exists and what it corrects.
