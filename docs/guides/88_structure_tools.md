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

Positions tab with the HIV reverse-transcriptase example: the table, the selected position's dye settings, the
accessible-volume message.
```

| Tab | Controls |
|---|---|
| **Positions** | **Add Row** (a row becomes a position when it has a name, or a chain and residue: `A132`), **Delete Row**, **Browse PDB...**, **Compute AVs**, **Save AV MRC**. The table's Name, Structure, Chain, Res, Atom cells are typed; under it the form of the selected row: attachment lists from the structure, dye preset and model, colour, dye dimensions, Simulation and Advanced (folded). |
| **Distances** | **Add Row**, **Delete Row**, **Add / Remove Scoring Group**, the scoring-group filter; the form of the selected restraint: labels, type (dRDA, dRDAE, dRMP, pRDA), score set, R0, d, errors, **Load DA Distribution...** for pRDA. |
| **FlexFit** | Set choice with **+** / **-**, residue and bond tables with **Add** / **Remove selected**. |
| **JSON** | The file text; edit it and press **Update** in the toolbar. |
| **3D View** | Accessible volumes, mean positions, distance lines and the backbone. |

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
   the **Score** tab plots the trace per trial, the **Structure** tab the CA / P trace of the selected result.

## 3. QuEst

Simulates a tethered dye diffusing over a protein with PET quenching (and FRET): choose a structure (**Load PDB...**),
the dye, the simulation and quenching settings, **Simulate**; the plots, a 3D trace with the attachment sites, the
**Quenching Chemistry** table and the **Project JSON** are tabs. It needs the IMP.bff quenching tables; without them the
card says so and offers **Retry**. See also the [QuEst guide](80_quenching_estimator.md).
