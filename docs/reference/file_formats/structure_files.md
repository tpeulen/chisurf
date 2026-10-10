---
type: File Format
title: Single-file structure reader
description: Select and import one PDB structure with native settings and source-free project restoration.
tags: [reference, file-formats, structure, settings]
---

# Single-file structure reader

Select the **Structure** experiment, then type a PDB filename or use **Browse**.
The reader imports one file. **Internal coordinates** controls computation
of the molecular internal coordinates; the original structure-loading method
and explicit `read(filename=...)` override are retained.

![Loaded 148L structure in native settings](figures/structure_reader_native.png)

Press **+ Data** to import using the selected source and original reader.
The atom/residue counters describe the last successfully imported structure;
changing the source clears them until that file is imported. The shipped 148L
example contains 1,300 atoms and 164 residues.

```python
from chisurf.core.experiments.modelling.reader import StructureReader

reader = StructureReader(filename="test/data/atomic_coordinates/pdb_files/148l.pdb",
                         compute_internal_coordinates=True,
                         record_provenance=False)
structures = reader.get_data()
```

Construction and restoration retain the source without opening it. A saved
project restores its embedded atoms when the original file is unavailable.
Displayed reader counts are derived from that restored structure only when
its recorded source matches the selected source; an unimported selection
remains empty. The uncalled folder-loading helper is retired.
