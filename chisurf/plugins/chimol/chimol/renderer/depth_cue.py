"""PyMOL's depth cue, in one place for every backend.

Why this is its own module
--------------------------
The cue is not a decoration: it is the only thing that tells a viewer which end
of a helix is nearer, and it fogs towards the **background colour**, so its
presence or absence changes the whole image against a light background and
almost nothing against a dark one. That asymmetry is what made it worth
extracting -- the WGSL backend was drawing without the cue, matched the OpenGL
baseline on black, and read as "markedly too dark" on white. The shading was
never wrong; the cue was missing, and only the light background exposed it.

Keeping the planes here rather than in :mod:`.qtgl` means the rasteriser, the
WebGPU renderer and the ray tracer measure the cue over the same span. They did
not always: the tracer once normalised it over an unfitted far plane and fogged
every pixel of the molecule by 24-69 %, which reads as a dimmer rather than as a
depth cue.
"""
from __future__ import annotations

from typing import Optional

__all__ = ["FOG_OFF", "fog_planes"]

#: What :func:`fog_planes` returns when the cue is off. A scale of ``0`` is the
#: signal every shader tests, so "off" is a value rather than a branch.
FOG_OFF = (0.0, 0.0)


def fog_planes(
    distance: float,
    radius: float,
    config: Optional[dict] = None,
) -> tuple[float, float]:
    """Return ``(fog_end, fog_scale)`` for the depth cue, PyMOL's way.

    Transcribed from ``SceneSetFog`` (``layer1/Scene.cpp``)::

        FogStart = (back - front) * fog_start + front
        FogEnd   = fog in (0, 1) ? FogStart + (back - FogStart) / fog : back
        active   = depth_cue and fog != 0

    and the shader then reads a *visibility*, ``(FogEnd - depth) / (FogEnd -
    FogStart)``, which is 1 in front of the start plane and 0 behind the end
    plane.

    The planes are fitted **around the scene** -- the camera distance either side
    of the target radius -- and not taken from the camera's clipping planes. That
    distinction is the whole of the feature: a cue measured over a far plane that
    was widened for depth precision spreads itself over empty space and dims the
    molecule uniformly instead of separating its front from its back.

    Parameters
    ----------
    distance : float
        Camera-to-target distance, in scene units.
    radius : float
        Radius of what the camera is framed on, in the same units. The span the
        cue is measured over is ``distance +/- radius``.
    config : dict, optional
        The ``depth_cue`` display-config section: ``enabled``, ``intensity``
        (PyMOL's ``fog``) and ``start`` (``fog_start``). ``None`` reads the live
        display config, which is what a renderer wants; a caller that has already
        resolved the section passes it to avoid reading a global twice.

    Returns
    -------
    tuple of float
        ``fog_end`` in view units, and ``1 / (end - start)``. :data:`FOG_OFF`
        when the cue is off or the span is degenerate.
    """
    if config is None:
        from ..config import _DISPLAY_CONFIG

        config = _DISPLAY_CONFIG.get("depth_cue", {}) or {}

    # PyMOL's `depth_cue`, `fog` and `fog_start` are global: they govern the
    # viewport, and the tracer follows them unless `ray_trace_fog` overrides.
    if not bool(config.get("enabled", True)):
        return FOG_OFF
    density = float(config.get("intensity", 1.0))
    if density == 0.0:
        return FOG_OFF

    r = max(float(radius), 1e-6)
    front = max(float(distance) - r, 1e-6)
    back = float(distance) + r
    if back <= front:
        return FOG_OFF

    start = (back - front) * float(config.get("start", 0.45)) + front
    if 0.0 < density < 1.0:
        end = start + (back - start) / density
    else:
        end = back
    if end <= start:
        return FOG_OFF
    return end, 1.0 / (end - start)
