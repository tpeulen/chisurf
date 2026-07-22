"""TTTR Header Editor plugin.

This plugin provides a tool for viewing and editing header tags of any
time-tagged time-resolved (TTTR) file that :mod:`tttrlib` can read — PicoQuant
PTU and HT3, Becker&Hickl SPC, and Photon-HDF5. ``tttrlib`` normalises every
container into the same tag list, so the editor is format-agnostic on read. It
allows users to:
1. Open and inspect any supported TTTR file (auto-detected container)
2. View all header tags and their values in a tabular format
3. Edit existing tag values
4. Add new custom tags to the header
5. Remove unwanted tags
6. Save the edited header to a new PTU file

The plugin features an intuitive table-based interface that displays tag names,
types, values, and indices. Users can modify any field and see the changes in
real-time. A JSON view is also available to see the complete header structure.

This tool is particularly useful for:
- Correcting metadata in experimental TTTR files
- Adding missing information to headers
- Preparing files for specialized analysis
- Troubleshooting issues with file metadata
- Educational purposes to understand TTTR file structure

The photon events of the source file are copied verbatim into the saved file.
Output is always a PTU container, because it is the only ``tttrlib`` container
that persists arbitrary edited header tags without loss.
"""

name = "TTTR:Editor:TTTR Header editor"

# Aggregated into the TTTR Tools toolbox (tttr_toolbox); hidden as a top-level
# menu entry but still importable and standalone-launchable.
menu_hidden = True

__all__ = ["TagsEditor"]


def __getattr__(attr_name: str):
    """Lazy Qt import gate (no Qt import as a package side effect)."""
    if attr_name == "TagsEditor":
        from .gui.tool import TagsEditor as _cls

        globals()["TagsEditor"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


if __name__ == "plugin":
    from .gui.tool import TagsEditor

    window = TagsEditor()
    window.show()
