---
type: Subsystem
title: Molecular surface quality and rendering verification
description: Meshed and screen-space molecular surfaces, their current ownership and the verification front preserved from the surface handover.
resource: modules/chimol/chimol/render/surface_quality.py
tags: [rendering, molecular-surface, webgpu, performance]
timestamp: '2026-10-07T00:00:00Z'
---

# Where to pick this up

1. Re-capture 148L at one fixed camera/settings state for `splat` and the meshed
   levels, with atoms/cartoon/sticks also visible. Read the PNGs and compare
   intersections, interior relief, silhouette and opacity. The historical claim
   that splats never write depth is obsolete: the current
   [resolve shader](../../modules/chimol/chimol/render/wgsl/gauss_resolve.wgsl)
   exports `frag_depth`. That source fact is not a substitute for a mixed-scene
   render or browser verification.
2. Audit molecular-surface-specific coverage separately from
   [the current splat picture tests](../../modules/chimol/tests/test_splat_picture.py),
   which cover chunk/SMLM depth entries and a splat profile. Verify quality
   routing/config-copy behavior, the actual molecular accumulation/resolve
   path and the browser's supported blendable formats. The old assertion of
   "no tests at all" is no longer accurate, but those existing tests do not
   establish all molecular-surface parity.
3. Profile current mesh builds before moving the density grid to another
   compute route. The handover measured roughly 253 ms for a 1,363-atom mesh
   (106 ms grid, 63 ms marching cubes, 65 ms occlusion); these are historical
   stage measurements, not current latency guarantees or values to add to a
   modern benchmark without re-measuring.

# Two deliverables, one quality selection

[Surface quality](../../modules/chimol/chimol/render/surface_quality.py) routes
`splat` to a screen-space field with no exported mesh; `fast`, `balanced` and
`fine` produce geometry at 0.9, 0.5 and 0.35 Å grid spacing. Mesh is the
appropriate deliverable for export, measurement or the ray tracer. Quality
application copies the live configuration and changes only the level's keys;
an unknown level does not silently replace the user's selected configuration.

The molecular scene builder is
[core/viewer/scene.py](../../modules/chimol/chimol/core/viewer/scene.py)
(`_build_surface_splat`), and accumulation/resolve belongs to
[render/wgpu_backend.py](../../modules/chimol/chimol/render/wgpu_backend.py).
The current path accumulates density-weighted normals, with an `rg16float`
companion channel carrying depth and weight information. Do not restore the
old handover's two-target packing or fixed uniform-float count: those no longer
match the current renderer.

# Provenance and rejected attempts

`HANDOVER_CHISURF_SURFACE.md` described the earlier unfinished surface path.
Its algorithm rationale and failure history already sit in
[the browser record](../plugins/chimol-web.md); this concept retains the live
verification front without repeating that history as a fresh implementation plan.

Density-gradient normals were rejected because a saturated interior becomes
flat despite a plausible lit rim. The depth-gradient correction in the old
handover was itself replaced by accumulated geometric normals in the current
resolve shader; smoothing that old gradient is not a current fix to repeat.
Blending an `r32float` accumulation target was rejected; depth-weight sums must
respect the selected blendable format and its range. Atom-centre depth was
rejected because it places the envelope inside the spheres; front-surface depth
and consistent per-draw uniforms matter. Use scratch display settings: a saved
quality level can make a capture correct for the wrong scene.
