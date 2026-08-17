"""``load <file>.fps.json``: label the structure, open the editor.

The wiring this pins (user request 2026-08-16: "just wire via load cmd --
if load *.fps.json open edit and label struct"):

    load x.fps.json  →  fps_load  →  structure from the document's own
    ``pdb_path`` when the scene is empty  →  every position's accessible
    volume computed and added  →  the document's distances drawn between
    the AV mean positions  →  the finished document offered to the host's
    editor through the window's ``on_open_fps_editor`` hook.

The hook is the same host-hook shape ``load`` uses for
``on_open_structure``: chimol names no editor (standalone chimol has no
such attribute and the load stays a load), and the chisurf plugin answers
it by opening the FPS JSON Editor populated -- see
``chisurf/plugins/chimol/__init__.py:_open_fps_editor``.

Everything here runs in the toolkit-free subprocess probe: no Qt can be
imported in the child, which is the rule for any test of chimol's
behaviour.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("rendercanvas", reason="the offscreen canvas host")

from toolkit_free import DATA, probe  # noqa: E402

_PDB = DATA / "atomic_coordinates" / "pdb_files" / "148l.pdb"


def _document() -> dict:
    """A two-position, one-distance fps.json naming its own structure.

    148l's chain is ``E`` -- the segid column reads ``A`` and the chain
    column reads ``E``, and the AV backends resolve by *chain*.
    """
    position = {
        "pdb_path": str(_PDB),
        "chain_identifier": "E",
        "residue_seq_number": 119,
        "atom_name": "CB",
        "simulation_type": "AV1",
        "linker_length": 20.0,
        "linker_width": 0.5,
        "radius1": 3.5,
        "radius2": 0.0,
        "radius3": 0.0,
        "simulation_grid_resolution": 1.5,
    }
    second = dict(position, residue_seq_number=44)
    return {
        "FormatVersion": "1.0",
        "Positions": {"119CB": position, "44CB": second},
        "Distances": {
            "119CB_44CB": {
                "position1_name": "119CB",
                "position2_name": "44CB",
                "distance_type": "RDAMean",
                "Forster_radius": 52.0,
                "distance": 50.0,
                "error_neg": 5.0,
                "error_pos": 5.0,
            }
        },
    }


_DRIVE = '''
    import json, pathlib

    app = open_app(size=(900, 600))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)

    p = pathlib.Path("build/test-load.fps.json")
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({payload}))

    opened = []
    app.cmd.window.on_open_fps_editor = opened.append

    before = len(app.viewer.objects)
    app.cmd.do(f"load {{p}}")

    av_count = sum(
        1 for e in app.viewer.objects.values()
        if getattr(getattr(e, "state", None), "av", None) is not None
    )
    emit("objects_added", str(len(app.viewer.objects) - before))
    emit("av_objects", str(av_count))
    emit("has_structure", str(any(
        getattr(e, "source_path", None) for e in app.viewer.objects.values()
    )))
    emit("measurements", str(len(app.viewer.measurements)))
    emit("hook_calls", str(len(opened)))
    emit("hook_positions", str(len((opened[0] or {{}}).get("Positions", {{}}))
                                if opened else -1))
    emit("errors", "; ".join(errors[:3]) or "none")
'''


def test_load_fps_json_labels_and_offers_the_document():
    """One command: structure, AVs, the distance, and the editor payload."""
    m = probe(_DRIVE.format(payload=_document()))
    assert m["objects_added"] == "4", "structure + two AVs + a mean marker"
    assert m["av_objects"] == "2"
    assert m["has_structure"] == "True", "the document's pdb_path was not loaded"
    assert m["measurements"] == "1", "the declared distance was not drawn"
    assert m["hook_calls"] == "1", "the editor hook was not called once"
    assert m["hook_positions"] == "2", "the hook did not carry both positions"
    assert m["errors"] == "none", m["errors"]


_PLAIN_DRIVE = '''
    import json, pathlib

    app = open_app(size=(900, 600))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)

    p = pathlib.Path("build/test-plain.json")
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({payload}))

    opened = []
    app.cmd.window.on_open_fps_editor = opened.append
    try:
        app.cmd.do(f"load {{p}}")
    except Exception:
        pass

    emit("hook_calls", str(len(opened)))
    emit("av_objects", str(sum(
        1 for e in app.viewer.objects.values()
        if getattr(getattr(e, "state", None), "av", None) is not None
    )))
'''


def test_a_plain_json_is_not_treated_as_a_labelling_document():
    """Only the compound suffix routes to ``fps_load``; a bare `.json` is not
    chimol's to interpret, and must not open the editor."""
    m = probe(_PLAIN_DRIVE.format(payload=_document()))
    assert m["hook_calls"] == "0", "a bare .json reached the fps editor hook"
    assert m["av_objects"] == "0", "a bare .json computed accessible volumes"


_PORTABLE_DRIVE = '''
    import json, pathlib

    # The example shape, assembled in a directory that is *not* the working
    # directory: a pml that loads the document by bare name, a document whose
    # pdb_path is relative -- relative to the *document*, not to the cwd.
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="chimol-example-")
    struct = pathlib.Path(tmp) / "struct"
    struct.mkdir()
    shutil.copy({pdb!r}, struct / "148l.pdb")

    doc = json.loads({payload!r})
    for fields in doc["Positions"].values():
        fields["pdb_path"] = "struct/148l.pdb"
    (pathlib.Path(tmp) / "net.fps.json").write_text(json.dumps(doc))
    (pathlib.Path(tmp) / "run.pml").write_text("load net.fps.json\\n")

    app = open_app(size=(900, 600))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)
    opened = []
    app.cmd.window.on_open_fps_editor = opened.append

    # The @script, by absolute path, from this (alien) working directory.
    app.cmd.do(f"@{{tmp}}/run.pml")
    n_av = 0
    for e in app.viewer.objects.values():
        if getattr(getattr(e, "state", None), "av", None) is not None:
            n_av += 1
    emit("script_av", n_av)
    emit("script_meas", len(app.viewer.measurements))
    emit("script_hook", len(opened))
    emit("script_dirs", len(app.cmd._script_dirs))

    # And the document alone, empty scene, same alien cwd -- the pdb_path must
    # resolve beside the document, not beside the process.
    app2 = open_app(size=(900, 600))
    app2.cmd.set_message_callback(lambda _m: None)
    app2.cmd.set_error_callback(errors.append)
    app2.cmd.do(f"load {{tmp}}/net.fps.json")
    m_av = 0
    for e in app2.viewer.objects.values():
        if getattr(getattr(e, "state", None), "av", None) is not None:
            m_av += 1
    emit("doc_alone_av", m_av)
    emit("doc_alone_meas", len(app2.viewer.measurements))
    emit("errors", "; ".join(errors[:3]) or "none")
'''


def test_the_shipped_example_shape_is_portable():
    """A shipped example opens from any working directory.

    This is the shape of ``chimol/examples/`` (a pml beside an fps.json whose
    ``pdb_path`` is relative), assembled here in a tempdir outside the repo so
    the test owns every file it asserts about: the ``@``-script resolves its
    bare ``load`` against the script's own directory, and the document's
    relative ``pdb_path`` resolves beside the document -- neither against the
    process cwd, which is the chisurf repo root and holds neither file.
    """
    m = probe(_PORTABLE_DRIVE.format(payload=json.dumps(_document()), pdb=str(_PDB)))
    assert m["script_av"] == "2", "the script's bare load did not find the document"
    assert m["script_meas"] == "1"
    assert m["script_hook"] == "1", "the script load did not reach the editor hook"
    assert m["script_dirs"] == "0", "the script-dir stack did not unwind"
    assert m["doc_alone_av"] == "2", "the document's relative pdb_path did not resolve"
    assert m["doc_alone_meas"] == "1"
    assert m["errors"] == "none", m["errors"]
