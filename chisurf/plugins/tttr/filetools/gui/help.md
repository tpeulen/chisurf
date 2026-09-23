# File Tools

The hub for everything that acts on a *file* rather than on a measurement: a
single window with a navigation list on the left and one lazily-loaded panel
per tool on the right.

Six tools live here, and they belong together because they are the same *kind*
of operation — none of them measures anything. They move a measurement between
containers, read one back, cut it into windows, or correct what a vendor wrote
into a header:

1. **TTTR Split / Convert** — split a recording into files of N photons and
   convert between container formats.
2. **⇄ .pto** — pack vendor files into a `.pto` container and unpack one back.
3. **PTO Inspector** — read what a `.pto` actually contains before using it.
4. **TTTR header** — view and correct the tags a vendor wrote into a TTTR
   header; the edited header is saved as a new PTU.
5. **TTTR → Time Windows** — cut each recording into fixed-duration windows,
   written as a burst-ID (`.bst`) file with one row per window.
6. **BID → Analysis** — turn a BID/`.bst` file into a burst table in the
   measurement's `.pto`.

## Why a hub

Each sub-tool already exists on its own; the hub embeds them **unchanged**.
What the hub adds is the company: header corrections sit beside the converters
because they are all file surgery, and a broken sub-tool breaks only its own
panel — the rest of the window still opens.

## Adding a panel

Panels are declared in `panels.json` beside the tool module and translated by
the shared panel loader; adding one is a JSON entry, not Python.

Press **Guide** for the walk-through.

## Further reading

- [Intensity traces and file tools](docs/guides/74_intensity_traces_and_file_tools.md)
- [Handling TTTR files (and Photon-HDF5)](docs/guides/12_handling_tttr_files.md)
- [Inspecting a container: what is in a .pto](docs/guides/63_pto_inspector.md)
- [The photon container: one measurement, one file](docs/concepts/photon_container.md)
