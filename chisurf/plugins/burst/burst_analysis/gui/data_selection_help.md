# Data Selection — the raw TTTR files

Step 1 of the Burst Analysis workflow. The files listed here are what every later
step reads: the burst search (step 2) gets them together with the detector setup
of step 0, and the IRF & Background and Background tools read the same photons.

- **Drop photon files** (`.ptu`, `.spc`, `.ht3`, …) on this step: they are linked
  into the Datasets workspace, as any drop on ChiSurf is, and listed here as soon
  as they are linked.
- **Input** lists the photon streams already in the workspace: **Use selected**,
  drag a row down into the file list, or right-click it › *Add to this tool*.
- Each newly added local file is put into the MMFDB object store and registered
  as raw TTTR data, so the burst results written later can point at their source.
  **File details** shows the record; **Import again** repeats a failed one.
- **Remove** takes the selected file out of the list, **Clear** all of them.

Converting a vendor file to ChiSurf's `.pto` container is not offered on a drop
here; use *File › Data › ⇄ .pto* first if you want the bursts kept inside
the measurement.
