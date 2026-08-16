"""Open and Save are the **system's** dialogs on every host that can have one.

The Qt window reaches a file dialog through Qt and the browser cannot have
one at all; the toolkit-free host used to have **neither** -- its File ▸
Open answered with a usage line and Save As wrote ``save {text}`` into the
command line for the user to finish typing, which lands a file wherever the
process happens to run. ``chimol.host.file_dialog`` asks the operating
system itself (``osascript`` on macOS, ``zenity``/``kdialog`` on Linux,
PowerShell on Windows) with no GUI toolkit, and ``ChimolApp`` wires it into
the two hooks every file choice flows through: ``load`` with no path, and a
menu entry carrying a ``file_prompt``.

What is pinned here, in the toolkit-free subprocess probe:

* both hooks are attached when the platform has a dialog, and neither is a
  Qt object (nothing may import Qt on this host);
* ``open`` with no path routes through the system dialog (patched -- a test
  that opened a real modal panel would hang waiting for a person) and loads
  what it returns. The assertion is on the *object*, not on a count: a
  fresh viewer keeps a placeholder object that the first real load
  replaces, so "one in, one out" is a count difference of zero and every
  arithmetic assertion on ``len(_objects)`` lies;
* a ``file_prompt`` entry substitutes the chosen path for ``{text}`` and
  runs the entry's command, quoted, and runs nothing on cancel;
* the script builders -- what would be asked of the OS -- without spawning
  any dialog;
* ``load`` strips one pair of surrounding quotes (the root fix that made
  quoted paths from a dialog loadable at all; before it,
  ``Path('"x.pdb"')`` was a filename starting with a quote).
"""

from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas", reason="the offscreen canvas host")

from toolkit_free import DATA, probe  # noqa: E402

_PDB = DATA / "atomic_coordinates" / "pdb_files" / "148l.pdb"


def _builders() -> "object":
    from chimol.host import file_dialog

    return file_dialog


def test_filter_sections_translate_to_clean_parts():
    """A Qt-style filter string parses; ``*`` never reaches a type list."""
    fd = _builders()
    pairs = fd._parse_filter(
        "Structures (*.pdb *.cif *.mmcif);;All files (*.*)"
    )
    assert pairs[0] == ("Structures", ["*.pdb", "*.cif", "*.mmcif"])
    assert fd._osascript_type_list(pairs) == ["cif", "mmcif", "pdb"], (
        "the 'All files' star must not become an of-type entry"
    )


def test_mac_scripts_are_single_and_multiple_choice():
    """The open script iterates only a list; the save script returns a path."""
    fd = _builders()
    single = fd._mac_open_script("Open it", False, "Structures (*.pdb)")
    assert "multiple selections" not in single
    assert 'choose file with prompt "Open it"' in single
    assert 'of type {"pdb"}' in single
    assert single.strip().endswith("return POSIX path of theChoice")

    multi = fd._mac_open_script("Open", True, "All files (*.*)")
    assert "with multiple selections allowed" in multi
    assert "of type" not in multi, "an unfiltered panel must not carry a type"
    assert "repeat with aChoice in theChoices" in multi

    save = fd._mac_save_script("Save molecule", "lyso.pdb")
    assert 'choose file name with prompt "Save molecule"' in save
    assert 'default name "lyso.pdb"' in save
    assert 'POSIX path of theChoice' in save


def test_windows_and_x11_builders_shape():
    """The Windows snippet composes one dialog with the filter in it."""
    fd = _builders()
    ps = fd._windows_ps("Save image", "Images (*.png)", save=True,
                        multiple=False, default_name="out.png")
    assert "SaveFileDialog" in ps and "OpenFileDialog" not in ps
    assert "Images (*.png)|*.png" in ps
    assert "$d.FileName = 'out.png'" in ps

    zen = fd._zenity_args("Open", "Images (*.png)", save=False,
                          multiple=True, default_name="")
    assert zen is None or (
        zen[0] == "zenity" and "--file-selection" in zen and "--multiple" in zen
    )


_DRIVE = '''
    import sys

    app = open_app(size=(900, 600))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)

    from chimol.host import file_dialog as fd
    emit("supported", str(fd.supported()))
    emit("qt_imported", str(any("qtpy" == m or m.startswith("PyQt")
                                or m.startswith("PySide") for m in sys.modules)))

    emit("open_hook", str(callable(getattr(app.host, "on_open_structure", None))))
    gui = app.renderer._internal_gui
    emit("prompt_hook", str(callable(getattr(gui, "on_file_prompt", None))))

    # The system dialog, patched: no panel may ever open from a test.
    fd.open_files = lambda **k: [{pdb!r}]
    app.cmd.do("open")
    sources = [str(getattr(e, "source_path", "") or "")
               for e in app.viewer._objects.values()]
    emit("open_loaded", str(any(s == {pdb!r} for s in sources)))

    # A file_prompt entry: open mode fills the placeholder from the dialog; a
    # cancelled save runs nothing at all.
    runs = []
    real_do = app.cmd.do
    app.cmd.do = lambda line: runs.append(line)
    app._on_file_prompt('load {{text}}', 'open', 'Open', 'All files (*.*)')
    fd.save_file = lambda **k: None
    app._on_file_prompt('png {{text}}', 'save', 'Save image', 'Images (*.png)')
    emit("cancelled_ran_nothing", str(len(runs) == 1))
    fd.save_file = lambda **k: "/tmp/out.png"
    app._on_file_prompt('png {{text}}', 'save', 'Save image', 'Images (*.png)')
    app.cmd.do = real_do
    emit("ran_open", runs[0] if runs else "none")
    emit("ran_save", runs[-1] if runs else "none")

    # The root fix: quotes around a typed path are an accident of the
    # keyboard or the dialog, not part of the filename.
    app.cmd.do(f'load "{pdb}"')
    sources = [str(getattr(e, "source_path", "") or "")
               for e in app.viewer._objects.values()]
    emit("quoted_loaded", str(sum(1 for s in sources if s == {pdb!r})))
    emit("errors", "; ".join(errors[:2]) or "none")
'''


def test_the_toolkit_free_host_opens_and_saves_through_the_system_dialog():
    """Both host hooks exist, work, with Qt unimportable in the child."""
    m = probe(_DRIVE.format(pdb=str(_PDB)), block_qt=True)
    assert m["supported"] == "True"
    assert m["qt_imported"] == "False", (
        "a Qt binding imported although the probe made it unimportable"
    )
    assert m["open_hook"] == "True", "load-with-no-path has no dialog on this host"
    assert m["prompt_hook"] == "True", "Save As entries have no dialog on this host"
    assert m["open_loaded"] == "True", (
        "File > Open did not load the file the system dialog returned"
    )
    assert m["ran_open"] == f'load "{_PDB}"'
    assert m["cancelled_ran_nothing"] == "True", (
        "a cancelled save dialog still ran a command"
    )
    assert m["ran_save"] == 'png "/tmp/out.png"'
    assert m["quoted_loaded"] == "2", (
        "a quoted typed path did not load as its own object"
    )
    assert m["errors"] == "none", m["errors"]
