# Structure Tools: FPS JSON editor, docking and QuEst

**Tool:** *Structure -> Structure Tools*. A list of structure-modelling tools on the left (with a search box and
**Back** / **Next**), the selected tool on the right. This page covers the three tools that are cards of the hub:
the **FPS JSON Editor**, **Docking & Screening** and **QuEst**. The other three (Kappa2 Distribution, HydroPro,
Trajectory Tools) have their own guides: [kappa2](61_kappa2_distribution.md), [HydroPro](79_hydropro.md),
[trajectory tools](81_trajectory_tools.md). Press **Guide** in any card for a step-by-step tour and **Help** for the
reference.

Theory of the accessible volumes behind the first two: [accessible volumes](../concepts/accessible_volume.md); the
[accessible-volume guide](23_accessible_volume.md) uses them for FRET analysis.

## 1. FPS JSON editor

An **fps.json** file lists the labelling *positions* (a dye attached to a chain, residue and atom of a structure) and the
measured *distances* between them. Open one with **Load** (or drop it on the window), or start from nothing.

```{figure} figures/88_fps_positions.png
:width: 100%

The HIV reverse-transcriptase example: the Positions table and the selected position's dye settings on the left,
the 3D View beside them with the selected position's accessible volume (red) in front and the others muted.
```

| Tab | Controls |
|---|---|
| **Positions** | **Add Row** (a row becomes a position when it has a name, or a chain and residue: `A132`), **Delete Row**, **Browse PDB...**, **Fetch PDB...** (download by a 4-character ID from the RCSB), **◀ Residue** / **Residue ▶** (walk the selected position along its chain), **Compute AVs**, **Save AV MRC**. The table's Name, Structure, Chain, Res, Atom cells are typed; under it the form of the selected row: attachment lists from the structure, dye preset and model, colour, dye dimensions, Simulation and Advanced (folded). |
| **Distances** | **Add Row**, **Delete Row**, **Add / Remove Scoring Group**, the scoring-group filter; the form of the selected restraint: labels, type (dRDA, dRDAE, dRMP, pRDA), score set, R0, d, errors, **Load DA Distribution...** for pRDA. |
| **FlexFit** | Set choice with **+** / **-**, residue and bond tables with **Add** / **Remove selected**. |
| **JSON** | The file text; edit it and press **Update** in the toolbar. |
| **3D View** | The ChiMOL viewer: the structures as cartoon, the accessible volumes as surfaces with their mean positions, the distance lines. The selected position's volume is in front, the others are muted, and picking a row brings the camera to it. Clicking an atom attaches the selected position to it (with none selected, it starts a new position; an atom of the other structure moves the position there); clicking a mean sphere selects that position. |

**Placing a dye.** Select a position (or none, to start one), then click an atom in the 3D View, or step with
**◀ Residue** / **Residue ▶**: the accessible volume is recomputed at once and drawn where the dye can now be, so a
labelling site can be chosen by looking at where its dye would sit.

The five views are dock windows: the tables tabbed on the left and the 3D View beside them. Drag a tab onto a side of
a view (the drop pads show where it lands) to see more at once, for example Distances beside Positions; drag it back
onto a tab strip to tab it again. The arrangement is kept for the next time the editor opens.

```{figure} figures/88_fps_split.png
:width: 100%

Distances dragged out beside Positions, the 3D View on the right: every view stays live, so a row picked in a table
and an atom clicked in the viewer act on the same position.
```

Toolbar: **Load**, **Save**, **Update**, **Clear** (asks first), **Guide**, **Help**. The accessible volume of a position is
computed in the background whenever its inputs change. Deleting a position asks, and removes the distances that use it;
renaming a position renames it in those distances.

## 2. Docking and screening

```{figure} figures/88_docking_results.png
:width: 100%

Three repeated docking runs of the HIV reverse transcriptase and its DNA: inputs left, the sorted results right.
```

1. **Add Files** (or drop .pdb files): one structure per rigid body; the row number is the body id.
2. **fps.json** chooses the restraints; **Output** the folder (default `dock_out` next to the fps.json). **Project** loads the
   example `docking_project.json` of the FRET plugin in one go.
3. **Op** (dock, refine, screen, score), **Method** (minimize, mc), **Runs** above 1 repeats from random starts.
4. **Run**; the bar shows progress and the best score, **Stop** ends it. Results are rows of the sortable **Results** table;
   the **Score** tab plots the trace per trial, the **Structure** tab the selected result in the ChiMOL viewer, as cartoon (**Previous** / **Next** step through several models).

## 3. QuEst

Simulates a tethered dye diffusing over a protein with PET quenching (and FRET): choose a structure (**Load PDB...**),
the dye, the simulation and quenching settings, **Simulate**; the plots, a 3D trace with the attachment sites, the
**Quenching Chemistry** table and the **Project JSON** are tabs. It needs the IMP.bff quenching tables; without them the
card says so and offers **Retry**. See also the [QuEst guide](80_quenching_estimator.md).
