# FPS JSON editor

Builds and edits the **fps.json** labelling files that the FRET docking and screening tools read: the positions where dyes are attached, the distances measured between them, and optional scoring groups and FlexFit sets. The window mirrors the file: whatever is in the tables is what **Save** writes, and the **JSON** tab shows it.

If you have not used it before, press **Guide** for the walk-through.

## Toolbar

| Button | What it does |
|---|---|
| **Load** | Opens an fps.json file (a .json file dropped on the window does the same). |
| **Save** | Writes the document. |
| **Update** | Reads the text of the JSON tab back into the tables. |
| **Clear** | Removes everything, after asking. |

## Positions

One row per labelling position. **Add Row** adds an empty row; it becomes a position as soon as it has a name, or a chain and residue (it is then called, for example, `A132`). Select a row to see its dye and simulation settings under the table: linker length and width, up to three dye radii, the model (AV1, AV0, AV3, ROTAMER), the grid resolution and the advanced options. **Browse PDB...** chooses the structure; a four-character ID is downloaded. The accessible volume of a position is computed in the background whenever its inputs change; **Compute AVs** recomputes all of them, **Save AV MRC** writes the selected one (or every one) as an MRC density map.

Deleting a position also deletes the distances that use it. Renaming it renames the labels in those distances.

## Distances

A restraint joins two positions and is named `label1_label2`. The type is **dRDA** (mean R_DA), **dRDAE** (mean FRET-averaged distance), **dRMP** (distance of the mean positions) or **pRDA** (a distribution you load from a two-column file). **Add Scoring Group** adds a chi-squared group; the filter above the table shows one group.

## FlexFit

Sets of flexible residues and bonds for FlexFit simulations.

## 3D View

The computed accessible volumes (points), their mean positions, the distance lines between them, and the backbone of the structure.

## Limits

The Qt editor drew the structure with the ChiMol viewer; this window draws the volumes and the backbone as a 3D plot. Several rows cannot be selected at once; delete them one by one.

## Further reading

[FPS JSON editor guide](docs/guides/88_structure_tools.md) · [Accessible volumes](docs/concepts/accessible_volume.md)
