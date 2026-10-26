---
type: Guide
title: Linked data in a project — find moved files, make a project self-contained
description: The Project data window lists the files a project links, finds moved originals by name and checksum, and stores every linked file inside the project before it is shared or deposited.
tags: [guides, project, links, data]
---

# Linked data in a project — find moved files, make a project self-contained

**File › Data › Project data** ({src}`chisurf/plugins/core/project_data/gui/app.py`); it also opens by
itself when a project opens with links that do not resolve. Theory: {ref}`concept-container-address`
in {doc}`../concepts/photon_container`.

A project **links** its large data files — photon streams, images, burst containers — instead of
copying them: it records each file's path (relative to the project), size and SHA-256 checksum. The
project stays small and never duplicates a measurement. **Add as** on the Read data page decides
whether new data is linked (the default) or embedded; a dataset's context menu in Datasets switches
one dataset later (**Embed in project** / **Link to file**).

## 1. See what is linked

The table lists every linked dataset of the open project: **found**, **embedded**, **missing**,
**size changed** or **content changed**, with where its file is or was. Opening a project compares
sizes only; **Check checksums** reads every file and compares checksums too. **Load example** opens a
demonstration project whose third file was moved to a backup folder, with a decoy of the same name.

## 2. Find a moved file

```{figure} figures/114_project_data_located.png
:width: 100%

The demonstration project: `a` and `b` found, `c` missing. *Search in folder…* on the backup folder
lists both files named `c.tif`, the one with the recorded size first.
```

Select the missing dataset and press **Search in folder…**: every file of that name below the chosen
folder is listed, those with the recorded size first. **Use candidate** checks the candidate's
checksum and links the dataset to it. **Search MMFDB** looks for the same checksum in the MMFDB
object store; **Replace with…** points at a file directly (a renamed original). A file whose size or
checksum differs is refused; **Use anyway** accepts it and records its checksum — only for data you
know is right although the file changed.

## 3. Make the project self-contained

```{figure} figures/114_project_data_self_contained.png
:width: 100%

After *Use candidate*, *Make self-contained* and *Save project*: all three datasets are stored in the
project, which now needs no other file.
```

**Make self-contained** stores every linked file inside the project at its next save (missing files
must be located first). Do this before sharing or archiving a project: a Zenodo deposit refuses a
project that is not self-contained unless you override it explicitly, and the override is recorded.

## Headless

The same operations run from Python on a project file:

```python
from chisurf.core.project.link_repair import LinkRepairModel, ProjectFileSource

model = LinkRepairModel(ProjectFileSource("study/demo.cs.pto"))
model.refresh()
print([row["name"] for row in model.unresolved])   # datasets whose file is missing or changed
```

## See also

- {doc}`../concepts/photon_container` — addresses and links inside PTO files
- {doc}`109_zenodo_deposit` — the deposit that checks a project is self-contained
- Plugin package: `chisurf/plugins/core/project_data/`
