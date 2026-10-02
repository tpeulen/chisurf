# FRET docking and screening

Moves rigid structures until the FRET distances their dye labels would give (from their accessible volumes) match the measured ones, with IMP and IMP.bff. The score is the restraint energy: lower is better.

If you have not used it before, press **Guide** for the walk-through.

## Inputs

| Input | Meaning |
|---|---|
| **PDB rigid bodies** | One structure per rigid body; the row number is the body id. The same file twice is a homodimer. |
| **fps.json** | Labelling positions and measured distances (see the FPS JSON editor), or an FPS LPs `.txt` file. |
| **Output** | Where the docked structures, the score file and the traces are written (`dock_out` next to the fps.json when left empty). |
| **Op** | `dock` rigid-body docking; `refine` conservative minimisation; `screen` ranks a library of structures; `score` scores one structure. |
| **Method** | `minimize` is fast conjugate-gradient minimisation; `mc` is replica-exchange Monte Carlo. |
| **Runs** | Above 1, the docking is repeated from random starts: the spread of the scores says how well the distances determine the result. |

The numeric fields (iterations, clash weight, refinement cycles, fixed body, distance width) and the Monte-Carlo options are described in their tooltips.

## Results

One row per result, best score first; runs accumulate until **Clear**. The **Score** tab plots the score against the step while the run goes on. The **Structure** tab draws the CA / P trace of the selected structure; with several docked models, **Previous** and **Next** step through them.

## Projects

**Project** and **Save** read and write a docking project: the structures, the fps.json, the output folder, the operation and the sampling parameters in one JSON file. A project that holds docked poses resumes from them (the **Resume** option).

## Limits

The Qt tool drew the structure with the ChiMol viewer; this window draws its backbone trace. IMP and IMP.bff must be installed; without them Run reports the error on the status line.

## Further reading

[Structure Tools guide](docs/guides/88_structure_tools.md) · [Accessible volumes](docs/concepts/accessible_volume.md)
