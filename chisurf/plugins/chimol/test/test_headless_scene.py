"""The headless backend must build the same scene the Qt one does.

Why this test exists
--------------------
Scene assembly is being made usable without a display, so that it can be driven
from the CLI, from tests, and eventually from a browser. That is only worth
anything if the scene is the *same* scene: a headless path that quietly builds
different geometry is worse than no headless path, because everything downstream
-- the ray tracer, a second renderer, a saved session -- would be comparing
against a fiction.

So this compares arrays, not pixels. It needs no GPU, and it is the regression
net for the renderer split: if extracting the backend ever changes what the
viewer assembles, this fails on the array that changed.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault(
    "CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chimol_headless_test_")
)

_PDB = Path("test/data/atomic_coordinates/pdb_files/148l.pdb")

#: Command scripts to compare. Each exercises a different scene builder, because
#: they are separate code paths and a shared one passing proves little.
SCRIPTS = [
    ["hide everything", "show cartoon", "orient"],
    ["hide everything", "show sticks", "orient"],
    ["hide everything", "show spheres", "orient"],
    ["hide everything", "show lines", "color red", "orient"],
]


def _build_scene(renderer_factory, script, qapp):
    """Run ``script`` through a viewer using ``renderer_factory`` and return its Scene."""
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    from chisurf.plugins.chimol.chimol.io.structure import load_structure_payload

    viewer = MolView(renderer_factory=renderer_factory)
    # The one route from a file into the viewer, and the Qt-free one: the parser
    # falls back to the built-in PDB reader when the core Structure (and IMP
    # behind it) is unavailable, which is exactly the web build's situation.
    _structure, payload = load_structure_payload(_PDB)
    assert payload is not None, f"could not parse {_PDB}"
    viewer.apply_payload(payload)
    if qapp is not None:
        for _ in range(10):
            qapp.processEvents()

    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    cmd = Cmd(None)
    cmd.set_window(_WindowStub(viewer))
    for line in script:
        cmd.do(line)
        if qapp is not None:
            for _ in range(6):
                qapp.processEvents()
    return getattr(viewer, "_scene", None), viewer


class _WindowStub:
    """The handful of window attributes the command layer reaches for."""

    def __init__(self, viewer):
        self.viewer = viewer

    def __getattr__(self, name):  # pragma: no cover - defensive
        raise AttributeError(name)


def _scene_fingerprint(scene):
    """Reduce a Scene to a comparable structure of ids, shapes and arrays."""
    assert scene is not None, "no scene was assembled"
    out = []
    for obj in scene.objects:
        geom = obj.geometry
        arrays = {}
        for field in ("positions", "indices", "normals", "colors", "radii", "occlusion"):
            value = getattr(geom, field, None)
            arrays[field] = None if value is None else np.asarray(value)
        out.append((obj.id, obj.render_mode, geom.kind, arrays))
    return out


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda s: s[1].replace(" ", "_"))
def test_headless_scene_matches_qt_scene(qapp, script):
    """A SceneSink viewer and a Qt viewer must assemble identical geometry."""
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.renderer.headless import SceneSink
    from chisurf.plugins.chimol.chimol.renderer.qtgl import QtGLRenderer

    head_scene, head_viewer = _build_scene(SceneSink, script, qapp)
    qt_scene, qt_viewer = _build_scene(QtGLRenderer, script, qapp)

    head = _scene_fingerprint(head_scene)
    qt = _scene_fingerprint(qt_scene)

    assert [o[0] for o in head] == [o[0] for o in qt], (
        "the two backends assembled different scene objects: "
        f"{[o[0] for o in head]} vs {[o[0] for o in qt]}"
    )
    for (hid, hmode, hkind, harr), (_, qmode, qkind, qarr) in zip(head, qt):
        assert (hmode, hkind) == (qmode, qkind), f"{hid}: render mode or kind differs"
        for field, hvalue in harr.items():
            qvalue = qarr[field]
            assert (hvalue is None) == (qvalue is None), (
                f"{hid}.{field}: present in one backend and not the other"
            )
            if hvalue is None:
                continue
            assert hvalue.shape == qvalue.shape, f"{hid}.{field}: shape differs"
            assert np.array_equal(hvalue, qvalue), (
                f"{hid}.{field}: values differ (max |delta| "
                f"{np.abs(hvalue.astype(float) - qvalue.astype(float)).max()})"
            )


def test_view_state_survives_a_round_trip():
    """``set_view_state(get_view_state())`` must return the same camera.

    A view tuple that changes on the way through cannot reproduce a frame, and
    reproducing a frame is the only reason to record one. The Qt backend widens
    the far plane to protect depth precision; copying that here silently moved
    slot 16 from 166.78 to 1167.82.
    """
    import numpy as np

    from chisurf.plugins.chimol.chimol.renderer.headless import SceneSink

    sink = SceneSink()
    sink.fit_to_radius(25.0)
    sink.look_at(np.array([1.0, 2.0, 3.0]))
    before = np.asarray(sink.get_view_state(), dtype=float)
    sink.set_view_state(before)
    after = np.asarray(sink.get_view_state(), dtype=float)
    assert before.shape == (18,), f"expected an 18-float tuple, got {before.shape}"
    bad = np.nonzero(np.abs(before - after) > 1e-9)[0]
    assert bad.size == 0, (
        "view tuple changed on round trip at slots "
        f"{[(int(i), float(before[i]), float(after[i])) for i in bad]}"
    )


def test_scene_sink_builds_a_scene_without_a_widget(qapp):
    """The point of the exercise: geometry with no window involved."""
    from chisurf.plugins.chimol.chimol.renderer.headless import SceneSink

    scene, viewer = _build_scene(SceneSink, ["hide everything", "show cartoon"], qapp)
    assert viewer._renderer is not None, (
        "a windowless renderer was discarded as 'no renderer', so _update_view "
        "returned before assembling anything"
    )
    assert viewer._renderer.widget() is None, "SceneSink must not produce a widget"
    assert scene is not None and scene.objects, "no geometry was assembled"
    triangles = sum(
        int(np.asarray(o.geometry.indices).size // 3)
        for o in scene.objects
        if o.geometry.indices is not None
    )
    assert triangles > 0, "a cartoon with no triangles is not a cartoon"
