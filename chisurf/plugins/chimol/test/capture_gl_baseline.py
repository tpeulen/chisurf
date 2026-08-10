"""The OpenGL renderer's output, feature by feature -- the migration's before-half.

**The capture is retired. The images are not.** ``renderer/qtgl.py`` has been
removed, so nothing here can photograph anything any more; what remains is the
*definition* of what was photographed -- the scene list, the reset preamble, and
the guard that keeps them in step -- beside 22 frozen PNGs and the camera each
was taken with in ``renders/gl_baseline/manifest.json``.

Why it is kept rather than deleted
----------------------------------
A migration is proven by a before/after pair, not by an after, and the
before-half of this one is now genuinely unrecoverable. Those images are the
only evidence of what chimol looked like under OpenGL, and
``test/compare_wgsl.py`` still replays each scene's commands and camera through
the WGSL renderer to put the two side by side. That makes them a **regression
reference**: the day a WGSL change makes one of those rows stop matching, the
question is whether the change was intended.

``SCENES`` and ``RESET`` stay live for the same reason -- ``missing_resets`` is
what caught five baselines being photographed with ambient occlusion switched
off, and the same class of leak can still contaminate a comparison run.

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
Nothing to run. To compare the WGSL renderer against these images::

    QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.compare_wgsl \
        cartoon sticks surface transparency
"""
from __future__ import annotations

import pathlib

_HERE = pathlib.Path(__file__).resolve().parent
_DATA = _HERE.parents[3] / "test" / "data" / "atomic_coordinates" / "pdb_files"
_OUT = _HERE / "renders" / "gl_baseline"

#: Undo everything any scene below changes, so a scene's appearance does not
#: depend on which scenes ran before it. Without this the images are only
#: reproducible by replaying the whole list in order -- the first run of this
#: script photographed a spectrum-coloured space-fill because ``spectrum count``
#: from an earlier scene was still in effect, which reads as a property of the
#: sphere representation and is not one.
#:
#: Every entry corresponds to something a scene perturbs, and keeping the two
#: lists in step is checked by :func:`missing_resets` rather than asked for in a
#: comment -- the comment was here and did not prevent ``occlusion.enabled`` from
#: being added to the scenes and not to this list. The cost of that gap was a
#: full day: ``occlusion_enabled_off`` runs immediately before ``bg_white``, so
#: five baselines were photographed with ambient occlusion switched off, and the
#: WebGPU renderer -- which had it on, correctly -- was read as "markedly too
#: dark against a white background" and hunted as a shading bug through the fog
#: term, the light rig and the environment reflection. A leaked setting does not
#: announce itself; it looks like whichever renderer you trust less.
RESET: list[str] = [
    "hide everything",
    "color grey80",
    "set transparency, 0",
    "set two_sided_lighting, off",
    "set depth_cue, off",
    "set fog, 1.0",
    "set silhouette, off",
    "set balls.impostor_min_atoms, 20000",
    "set occlusion.enabled, on",
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
    # `sticks.ambient_occlusion` had a scene here, to document that it was
    # registered and reachable and gated nothing. The setting is gone (schema
    # version 11 deletes it from existing configs too), so the scene went with
    # it: replaying it now raises "Unknown setting", which the error callback
    # reports on every comparison and is pure noise.
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


def _settings_in(lines) -> set[str]:
    """Names of the settings a list of commands assigns with ``set``."""
    names = set()
    for line in lines:
        text = line.strip()
        if not text.lower().startswith("set "):
            continue
        names.add(text[4:].split(",", 1)[0].strip().lower())
    return names


def missing_resets() -> set[str]:
    """Settings some scene assigns that :data:`RESET` does not put back.

    A scene that leaves a setting behind does not fail; the *next* scene renders
    with it and the difference is attributed to whatever that scene was meant to
    show. So this is checked rather than remembered -- see the note on
    :data:`RESET` for what one missing entry cost.

    Returns
    -------
    set of str
        Setting names to add to :data:`RESET`. Empty when the lists are in step.
    """
    perturbed: set[str] = set()
    for _name, _structure, script in SCENES:
        perturbed |= _settings_in(script)
    return perturbed - _settings_in(RESET)


if __name__ == "__main__":  # pragma: no cover - there is nothing left to run
    raise SystemExit(
        "the OpenGL renderer this captured no longer exists; these baselines "
        "are frozen. Use test/compare_wgsl.py to compare against them."
    )
