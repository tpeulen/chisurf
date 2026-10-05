# Data Selection — the raw TTTR files

Step 1 of the Burst Analysis workflow. The files listed here are what every later
step reads: the burst search (step 2) gets them together with the detector setup
of step 0, and the IRF & Background and Background tools read the same photons.

- **Add files** / **Add folder** choose TTTR files; a folder adds the TTTR files
  directly inside it. Files can also be dropped on the window.
- **Database (MMFDB)** picks raw data already registered in MMFDB; it is resolved
  to a local file and added like any other.
- Each newly added local file is put into the MMFDB object store and registered
  as raw TTTR data, so the burst results written later can point at their source.
  **File details** shows the record; **Import again** repeats a failed one.
- **Remove** takes the selected file out of the list, **Clear** all of them.

Converting a vendor file to ChiSurf's `.pto` container is not offered on a drop
here; use *File tools › TTTR to PTO* first if you want the bursts kept inside
the measurement.
