# Legacy export

The bridge out of the ``.pto`` world: the workflow tools read and write ``.pto`` containers, and this tool
writes the legacy formats colleagues still expect — the Seidel/Margarita burst files (``.bur``/``.bg4``) and
the classic burst-wise CSV tables — from a project or a burst-selection result.

## How it works
1. Open a ``.cs.pto`` project or a burst result (the tool lists what the running session holds).
2. Pick the target format: ``.bur``/``.bg4`` (binary Seidel/Margarita) or CSV burst table.
3. Press Export and choose where to write. The file is written directly — no round trip through the project
   container.

## Before trusting a result
The legacy formats carry fewer columns than the ``.pto`` container (no QC flags, no per-burst corrections);
export is a view, not a backup. Keep the ``.pto`` file as the record and re-export when a colleague needs the
old format.
