"""Put the WGSL renderer beside the OpenGL baseline, scene by scene.

Why this exists
---------------
The remaining Phase 2 work is a list of features -- impostors, transparency,
two-sided lighting, depth cue, silhouettes, labels -- and each one is accepted or
rejected by looking at a GL|WGSL pair. Writing that comparison once means the
per-feature cost is a scene name rather than a script, and it means every pair is
cropped and coloured the same way.

Getting the comparison right mattered more than getting the renderer right. Two
conclusions reported from ad-hoc versions of this were wrong:

* an IoU of 0.362 read as "the camera is mirrored" and was a mis-guessed crop --
  the molecule occupies a *column* of the framebuffer, because the object panel
  and the sequence strip are drawn inside the GL widget. With ``scene_rect`` from
  the manifest it is 0.981 and the camera was never wrong;
* a colour difference read as "the renderer draws colours wrong" and was two
  commands refusing with "nothing is loaded" while the harness discarded the
  errors.

So this module does three things no ad-hoc script did: it crops by the recorded
``scene_rect``, it attaches the error callback and reports what came back, and it
reads the background from the scene instead of assuming black.

Use
---
    python -m chisurf.plugins.chimol.test.compare_wgsl cartoon sticks surface
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import numpy as np

os.environ.setdefault(
    "CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chimol_compare_")
)

_HERE = pathlib.Path(__file__).resolve().parent
_DATA = _HERE.parents[3] / "test" / "data" / "atomic_coordinates" / "pdb_files"
_BASELINE = _HERE / "renders" / "gl_baseline"
_OUT = _HERE / "renders" / "wgsl"

#: Background colours by chimol name, for the handful the scenes use. The scene
#: does not carry its own clear colour -- the renderer holds it -- so a comparison
#: that assumes black silently mismatches every scene that sets one.
_NAMED_BACKGROUNDS = {
    "black": (0.0, 0.0, 0.0),
    "k": (0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0),
    "w": (1.0, 1.0, 1.0),
    "grey20": (0.2, 0.2, 0.2),
    "gray20": (0.2, 0.2, 0.2),
}


def background_for(viewer) -> tuple[float, float, float]:
    """Best-effort clear colour for ``viewer``.

    Reads what the renderer was told rather than assuming black, so a scene that
    sets ``bg_color grey20`` is compared against a grey frame.
    """
    raw = getattr(getattr(viewer, "_renderer", None), "_background", None)
    if isinstance(raw, str):
        return _NAMED_BACKGROUNDS.get(raw.strip().lower(), (0.0, 0.0, 0.0))
    if isinstance(raw, (tuple, list)) and len(raw) >= 3:
        try:
            return tuple(float(c) for c in raw[:3])
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def build(scene_name: str, entry: dict):
    """Replay one baseline scene headlessly and return ``(viewer, errors)``."""
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd
    from chisurf.plugins.chimol.chimol.io.structure import load_structure_payload
    from chisurf.plugins.chimol.chimol.renderer.headless import SceneSink
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    viewer = MolView(renderer_factory=SceneSink)
    _structure, payload = load_structure_payload(_DATA / entry["structure"])
    viewer.apply_payload(payload)

    class _Window:
        def __init__(self, v):
            self.viewer = v

    cmd = Cmd(None)
    cmd.set_window(_Window(viewer))
    errors: list[str] = []
    # Attached, not omitted. A harness that drops these turns a refused command
    # into a rendering difference two layers away.
    cmd.set_error_callback(errors.append)
    for line in entry.get("reset", []) + entry["script"]:
        cmd.do(line)
    if entry.get("view"):
        cmd.do(entry["view"])
    return viewer, errors


def compare(scene_name: str):
    """Render ``scene_name`` both ways and return ``(pair_image, errors, iou)``."""
    from PIL import Image

    from chisurf.plugins.chimol.chimol.renderer.pack import pack_scene
    from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

    manifest = json.loads((_BASELINE / "manifest.json").read_text())
    entry = manifest[scene_name]
    rect = entry["scene_rect"]

    viewer, errors = build(scene_name, entry)
    packed = pack_scene(viewer._scene)
    background = background_for(viewer)

    gl_full = np.asarray(
        Image.open(_BASELINE / f"{scene_name}_view.png").convert("RGB")
    )
    gl = gl_full[
        rect["y"] : rect["y"] + rect["height"], rect["x"] : rect["x"] + rect["width"]
    ]
    wgsl = WgpuMeshRenderer(rect["width"], rect["height"]).render(
        packed, viewer._renderer.get_view_state(), background=background
    )

    h = min(gl.shape[0], wgsl.shape[0])
    w = min(gl.shape[1], wgsl.shape[1])
    gl, wgsl = gl[:h, :w], wgsl[:h, :w]
    a, b = gl.sum(2) > 25, wgsl.sum(2) > 25
    iou = float((a & b).sum() / max((a | b).sum(), 1))
    return np.concatenate([gl, wgsl], axis=1).astype(np.uint8), errors, iou


def main(names: list[str]) -> int:
    """Write one contact sheet with a row per scene."""
    from PIL import Image
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None  # bound: an unreferenced QApplication is collected

    rows, report = [], []
    for name in names:
        try:
            pair, errors, iou = compare(name)
        except Exception as exc:  # pragma: no cover - diagnostic
            report.append(f"  {name:22s} FAILED: {exc!r}")
            continue
        rows.append(pair)
        flag = f"  !! {errors}" if errors else ""
        report.append(f"  {name:22s} IoU {iou:.3f}{flag}")

    if not rows:
        print("nothing rendered")
        return 1
    height = min(r.shape[0] for r in rows)
    width = min(r.shape[1] for r in rows)
    sheet = np.concatenate([r[:height, :width] for r in rows], axis=0)
    _OUT.mkdir(parents=True, exist_ok=True)
    path = _OUT / "compare_sheet.png"
    Image.fromarray(sheet).save(path)
    print("\n".join(report))
    print(f"\nrows (GL | WGSL): {', '.join(names)}")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["cartoon", "sticks", "surface"]))
