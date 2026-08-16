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

    before = len(app.viewer._objects)
    app.cmd.do(f"load {{p}}")

    av_count = sum(
        1 for e in app.viewer._objects.values()
        if getattr(getattr(e, "state", None), "av", None) is not None
    )
    emit("objects_added", str(len(app.viewer._objects) - before))
    emit("av_objects", str(av_count))
    emit("has_structure", str(any(
        getattr(e, "source_path", None) for e in app.viewer._objects.values()
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
        1 for e in app.viewer._objects.values()
        if getattr(getattr(e, "state", None), "av", None) is not None
    )))
'''


def test_a_plain_json_is_not_treated_as_a_labelling_document():
    """Only the compound suffix routes to ``fps_load``; a bare `.json` is not
    chimol's to interpret, and must not open the editor."""
    m = probe(_PLAIN_DRIVE.format(payload=_document()))
    assert m["hook_calls"] == "0", "a bare .json reached the fps editor hook"
    assert m["av_objects"] == "0", "a bare .json computed accessible volumes"
