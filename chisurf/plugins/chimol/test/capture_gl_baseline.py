"""Capture the OpenGL renderer's output, feature by feature, before it is replaced.

Why this exists
---------------
The desktop renderer is moving from OpenGL to WebGPU/WGSL so that the desktop and
the browser can share one shader source (see
[chimol-web](okf/plugins/chimol-web.md)). A migration is proven by a before/after
pair, not by an after -- and the before-half of *this* migration is unrecoverable:
once ``renderer/qtgl.py`` is replaced there is no way to re-photograph what the
OpenGL renderer looked like, and nobody can review the port afterwards.

So this script photographs every render feature through the current GL renderer
and, next to each image, records the exact camera it was taken with. The 18-float
PyMOL view tuple is Qt-free and shared by every backend, so the replacement can
replay ``set_view`` and produce a directly comparable frame.

What is judged
--------------
Not pixels. A WGSL renderer will never be pixel-identical to a GLSL one -- and two
of these scenes change *deliberately* (sphere impostors gain per-fragment depth;
tessellated sticks become analytic capsules). Parity is judged on **feature
inventory**: every element visible in the before-image must be present and
recognisable in the after-image, with deliberate differences written down.

Both sphere paths are captured on purpose. ``impostor_min_atoms`` (default 20000)
selects between tessellated spheres and point-sprite impostors, and the WGSL
renderer collapses the two into one instanced-impostor path, so both halves of
what it replaces have to exist as a baseline.

Use
---
    # needs a logged-in window server -- NOT QT_QPA_PLATFORM=offscreen, which
    # cannot create a GL context and yields black
    python -m chisurf.plugins.chimol.test.capture_gl_baseline
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import traceback

# Must be set before anything builds a QSettings: the main window persists its
# dock layout, and a restored one hands the 3-D view a strip (see
# assert_view_usable in screenshot.py). This also keeps a QA run from writing the
# user's real preferences.
os.environ.setdefault(
    "CHISURF_SETTINGS_DIR",
    tempfile.mkdtemp(prefix="chimol_baseline_settings_"),
)

_HERE = pathlib.Path(__file__).resolve().parent
_DATA = _HERE.parents[3] / "test" / "data" / "atomic_coordinates" / "pdb_files"
_OUT = _HERE / "renders" / "gl_baseline"

#: Undo everything any scene below changes, so a scene's appearance does not
#: depend on which scenes ran before it. Without this the images are only
#: reproducible by replaying the whole list in order -- the first run of this
#: script photographed a spectrum-coloured space-fill because ``spectrum count``
#: from an earlier scene was still in effect, which reads as a property of the
#: sphere representation and is not one. Every entry here corresponds to
#: something a scene perturbs; keep the two lists in step.
RESET: list[str] = [
    "hide everything",
    "color grey80",
    "set transparency, 0",
    "set two_sided_lighting, off",
    "set depth_cue, off",
    "set silhouette, off",
    "set balls.impostor_min_atoms, 20000",
    "set sticks.ambient_occlusion, off",
    "bg_color black",
    "cartoon automatic",
    'label all, ""',
]

#: Each entry is (name, structure, setup commands). Kept deliberately small and
#: single-purpose: a scene that exercises three features at once cannot tell you
#: which one regressed.
SCENES: list[tuple[str, str, list[str]]] = [
    # --- geometry / representation -----------------------------------------
    ("cartoon", "148l.pdb", ["hide everything", "show cartoon", "spectrum count", "orient"]),
    ("cartoon_putty", "148l.pdb", ["hide everything", "show cartoon", "cartoon putty", "orient"]),
    ("sticks", "148l.pdb", ["hide everything", "show sticks", "orient"]),
    ("lines", "148l.pdb", ["hide everything", "show lines", "orient"]),
    ("ribbon", "148l.pdb", ["hide everything", "show ribbon", "orient"]),
    ("dots", "148l.pdb", ["hide everything", "show dots", "orient"]),
    # Both sphere paths. `impostor_min_atoms` has no PyMOL name, so it is reached
    # by its dotted config path -- `set impostor_min_atoms` answers "Unknown
    # setting", which is the difference between a setting being *registered* and
    # being *reachable*.
    ("spheres_mesh", "148l.pdb",
     ["hide everything", "set balls.impostor_min_atoms, 100000", "show spheres", "orient"]),
    ("spheres_impostor", "148l.pdb",
     ["hide everything", "set balls.impostor_min_atoms, 10", "show spheres", "orient"]),
    ("surface", "148l.pdb", ["hide everything", "show surface", "orient"]),
    ("mesh", "148l.pdb", ["hide everything", "show mesh", "orient"]),
    # --- shading / materials ------------------------------------------------
    ("transparency", "148l.pdb",
     ["hide everything", "show surface", "set transparency, 0.5", "orient"]),
    ("two_sided_on", "148l.pdb",
     ["hide everything", "show surface", "set transparency, 0.5",
      "set two_sided_lighting, on", "orient"]),
    ("depth_cue_fog", "148l.pdb",
     ["hide everything", "show spheres", "set depth_cue, on", "set fog, 1.0", "orient"]),
    # A settings scene is only readable next to a control that differs by the
    # setting alone. Diffing `silhouette` against `cartoon` compares colour --
    # `cartoon` carries `spectrum count` -- and reports 11.5% of pixels changed,
    # which reads as a working silhouette and is not one.
    ("silhouette_off", "148l.pdb",
     ["hide everything", "show cartoon", "set silhouette, off", "orient"]),
    ("silhouette", "148l.pdb",
     ["hide everything", "show cartoon", "set silhouette, on", "orient"]),
    # `sticks.ambient_occlusion` is registered and reachable but gates nothing --
    # kept as a baseline so the port is not blamed for its having no effect.
    ("ambient_occlusion", "148l.pdb",
     ["hide everything", "show sticks", "set sticks.ambient_occlusion, on", "orient"]),
    # The gate that AO *actually* reads is `occlusion.enabled`, and only for
    # cartoon. Captured as a matched pair because the sense of that gate is
    # inverted in the current renderer (see known-issues): AO appears when
    # occlusion is switched OFF.
    ("occlusion_enabled_on", "148l.pdb",
     ["hide everything", "show cartoon", "set occlusion.enabled, on", "orient"]),
    ("occlusion_enabled_off", "148l.pdb",
     ["hide everything", "show cartoon", "set occlusion.enabled, off", "orient"]),
    # --- colour / background ------------------------------------------------
    ("bg_white", "148l.pdb", ["hide everything", "show cartoon", "bg_color white", "orient"]),
    ("bg_grey_spectrum", "148l.pdb",
     ["hide everything", "show cartoon", "bg_color grey20", "spectrum b", "orient"]),
    # --- text ---------------------------------------------------------------
    ("labels", "148l.pdb",
     ["hide everything", "show sticks, resi 1-8", "label resi 1-8 and name CA, resi",
      "orient resi 1-8"]),
    # --- nucleic + a larger system -----------------------------------------
    ("nucleic_cartoon", "1rtd.pdb", ["hide everything", "show cartoon", "orient"]),
    ("large_spheres", "1rtd.pdb", ["hide everything", "show spheres", "orient"]),
]


def main() -> int:
    # refuses the offscreen platform, where GL has no context and yields black
    from .screenshot import assert_view_usable, ensure_app, shoot

    app = ensure_app()
    from chisurf.plugins.chimol.chimol.app.molview_main_window import MolViewPluginWindow
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    _OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    loaded: str | None = None
    win = None

    for name, structure, script in SCENES:
        try:
            if win is None or structure != loaded:
                if win is not None:
                    win.close()
                win = MolViewPluginWindow()
                win.resize(1280, 860)
                win.show()
                for _ in range(12):
                    app.processEvents()
                # a Path, not a str: _make_object_name() calls .stem on it
                win._load_structure_from_path(_DATA / structure)
                for _ in range(25):
                    app.processEvents()
                shared.set_window(win)
                loaded = structure

                # Loading redistributes the docks, and the 3-D view can be left
                # a strip for several event cycles before the layout settles --
                # long enough that a single settle pass photographs the strip.
                # Re-assert the window size and pump until the viewport is sane.
                for _ in range(40):
                    try:
                        vw, vh = assert_view_usable(win)
                        break
                    except RuntimeError:
                        win.resize(1280, 860)
                        for _ in range(10):
                            app.processEvents()
                else:
                    # Still wrong after settling: refuse. A baseline taken from a
                    # strip is worse than a missing one, because it looks real.
                    vw, vh = assert_view_usable(win)
                print(f"     viewport {vw}x{vh}")

            errors: list[str] = []
            messages: list[str] = []
            shared.set_message_callback(messages.append)
            shared.set_error_callback(errors.append)

            # Reset first, then the scene. Errors from the reset are collected
            # too -- a reset line that silently fails leaves state behind and
            # the leak reappears as an unexplained difference in one image.
            for line in RESET + script:
                shared.do(line)
                for _ in range(12):
                    app.processEvents()

            view = ""
            try:
                view = shared.get_view() or ""
            except Exception as exc:  # pragma: no cover - diagnostic only
                errors.append(f"get_view failed: {exc!r}")

            paths = shoot(win, name, directory=_OUT, size=(1280, 860), area="all")

            # Where the molecule actually is inside the `_view` grab. The panel
            # is a right-hand *column* and the sequence viewer a top *band*, both
            # drawn inside the GL widget, so the framebuffer is wider and taller
            # than the scene. Without this a diff against the PNG measures the
            # crop rather than the shading -- two silhouette overlaps taken that
            # way came out 0.362 and 0.277 and meant nothing.
            scene_rect = None
            try:
                r = win.viewer._renderer
                fb_w, fb_h = r.width(), r.height()
                sw, sh = r.scene_width(), r.scene_height()
                # device pixels, since that is what grabFramebuffer returns
                ratio = float(getattr(win, "devicePixelRatioF", lambda: 1.0)())
                scene_rect = {
                    "x": 0,
                    "y": int(round((fb_h - sh) * ratio)),
                    "width": int(round(sw * ratio)),
                    "height": int(round(sh * ratio)),
                    "framebuffer": [int(round(fb_w * ratio)), int(round(fb_h * ratio))],
                    "device_pixel_ratio": ratio,
                }
            except Exception as exc:  # pragma: no cover - diagnostic only
                errors.append(f"scene_rect unavailable: {exc!r}")

            manifest[name] = {
                "structure": structure,
                # the molecule's rectangle within <name>_view.png
                "scene_rect": scene_rect,
                # the full sequence, so the after-half replays exactly this
                "reset": RESET,
                "script": script,
                # replay with `set_view <view>` to reproduce this exact frame
                "view": view,
                "errors": errors,
                "files": {k: v.name for k, v in paths.items()},
            }
            flag = f"  !! {len(errors)} error(s)" if errors else ""
            print(f"[ok] {name:20s} {structure:12s}{flag}")
            for e in errors:
                print(f"        {e}")
        except Exception:
            manifest[name] = {"structure": structure, "script": script,
                              "failed": traceback.format_exc(limit=3)}
            print(f"[FAIL] {name}")
            traceback.print_exc(limit=3)

    if win is not None:
        win.close()
    (_OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    n_ok = sum(1 for v in manifest.values() if "failed" not in v)
    n_err = sum(1 for v in manifest.values() if v.get("errors"))
    print(f"\n{n_ok}/{len(SCENES)} scenes captured, {n_err} with command errors")
    print(f"-> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
