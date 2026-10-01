# PTO containers

A .pto is one measurement in one file. The instrument file goes in byte for byte and is never decoded into a second copy beside itself; every result computed from it (a burst table, a decay, a correlation, a fit) is written beside it as an artifact, together with the operation and the settings that produced it. This window reads that back. It writes nothing.

## Open a container
Open chooses a .pto. Database picks one from the MMFDB database. You can also drop a .pto on the window. A vendor photon file (.ptu, .spc, .ht3, ...) dropped here is offered for packing into a new container in a folder you choose; the source file is kept and an existing container is never overwritten. Reload reads the file again, picking up anything written since.

## What is in it
The Objects list has one row per object, in the order it was written. Kind is an artifact kind from the dictionary, Operation the operation that produced it (empty means carried, not computed), Grain says what one row is. Nothing in a container is joined by position: when two tables relate, the relation is a declared key, shown in the details.

## How it got there
The Provenance graph shows the instrument file on the left and the last result on the right; every arrow is a recorded derivation. A node with two incoming arrows has two parents. Alt-drag pans, the wheel zooms, Fit graph frames everything.

## What the numbers are
Data shows a table payload with the unit each column states. A curve (decay, correlation, anisotropy, IRF, model, residual) is drawn in Curve with the axis units and scale taken from the stored columns.

## What exactly was recorded
Details lists everything recorded about the selected object, including the settings: their hash is the identity of the run. Lineage is the path back to the primary data, Parameters the settings alone, Text a README or metadata payload.

## Open tool and Export
Open tool (or a double-click on a graph node or a row) looks the selected object's operation up in the installed tools and opens the matching window on this file. A step no installed tool claims says so. Export writes a table as CSV, or extracts any other payload as it is.

## Verify
Verify re-hashes every payload and compares it with the checksum recorded beside it. Worth doing before deleting an original.

## Further reading
- [The photon container: one measurement, one file](docs/concepts/photon_container.md)
- [Inspecting a container: what is in a .pto](docs/guides/63_pto_inspector.md)
