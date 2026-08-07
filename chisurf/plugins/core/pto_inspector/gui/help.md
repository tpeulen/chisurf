# PTO containers — what they are, and what this window shows

A `.pto` is **one measurement in one file**. The instrument file goes in
byte-for-byte and is never decoded into a second copy beside itself; every result
computed from it — a burst table, a decay, a correlation, a fit, a selected
sub-population — is written beside it as an *artifact*, together with the
operation and the settings that produced it.

That is what this window reads back. It writes nothing.

## The four questions a container gets asked

**What is in it.** The *Objects* list on the left, one row per object in the
order it was written. The columns are the container's own vocabulary, not this
tool's: *kind* is an `_mmfdb_artifact.artifact_kind` term, *operation* an
`_mmfdb_operation.operation_type` term, and *grain* says what one row **is**.

The grain is the load-bearing one. Nothing in a container is joined by position:
a dwell table is finer than the bursts it came from and a fused-burst table is
coarser, and a format that could only carry one row per burst would have nowhere
to put either. When two tables relate, the relation is a **declared key** (shown
in the details as `on First Photon = First Photon`), not an alignment of row
counts.

**How it got there.** The *Provenance* graph. The instrument file is on the left,
the last thing computed on the right, and every arrow is a recorded derivation
rather than an inference from file names. A node with two incoming arrows
genuinely has two parents — a lifetime fit uses the bursts *and* the background —
which is exactly the case an indented tree cannot draw without duplicating a node
or dropping an edge.

**What the numbers are.** The *Data* tab shows a tabular payload with the shared
table: sort, filter, hide columns, search, export. Column headers carry the unit
the column itself states, so a duration in milliseconds cannot be read as
seconds. A curve — a decay, a correlation, an anisotropy, an IRF, a model, a
residual — is drawn in *Curve* instead, with the axis units and the scale taken
from the stored columns.

**What exactly was recorded.** The *Details* tab, including the settings. Those
are not a label on the run: their hash **is** the identity of the run. Recomputing
with the same settings rewrites that artifact in place, and changing one produces
a new artifact — which is why nothing accumulates and why parameters never have
to be encoded in a file name.

## Opening the tool that made a result

A container records the *operation*, never the program: naming a ChiSurf plugin
in the file would have made it unreadable by anything else, which is the whole
point of taking every term from the dictionaries.

So the mapping runs the other way. Each tool declares in its manifest which
`operation_types` it performs, and **▶ Open tool** (or a double-click on a graph
node) looks the selected artifact's operation up in that index and opens the
matching window on this same file. A step no installed tool claims says so rather
than doing nothing — the container may well carry a result another program
computed, and the settings above it are still the whole recipe.

## Verifying

**🔍 Verify** re-hashes every payload and compares it against the checksum
recorded beside it. Worth doing before deleting an original: *restorable* without
verification is only *probably restorable*.

## Headless

Everything here is also `csg_pto_inspect`:

```bash
csg_pto_inspect list     measurement.pto
csg_pto_inspect show     measurement.pto bursts
csg_pto_inspect lineage  measurement.pto burst_lifetimes
csg_pto_inspect verify   measurement.pto
csg_pto_inspect export   measurement.pto bursts bursts.csv
```

## Further reading

- [The photon container: one measurement, one file](docs/concepts/photon_container.md)
- [Inspecting a container: what is in a .pto](docs/guides/63_pto_inspector.md)
- [mmCIF / PDBx dictionaries](https://mmcif.wwpdb.org/)
