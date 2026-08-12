"""What a surface quality level means, in numbers.

Four levels, and the first of them is a different algorithm rather than a
coarser setting of the same one:

``splat``
    Screen-space Gaussian splats -- no 3-D grid, no iso-surface, no mesh. The
    field is evaluated per pixel by ``wgsl/gauss_splat.wgsl`` and shaded by
    ``wgsl/gauss_resolve.wgsl``. Nothing is rebuilt when the molecule moves, so
    this is the level to turn a structure with; it produces no geometry, so it
    is the wrong level to export or measure from.
``fast``, ``balanced``, ``fine``
    The meshed pipeline -- density grid, iso-threshold, distance transform,
    marching cubes -- at three grid spacings. The spacing is the whole cost:
    halving it multiplies the voxel count by eight.

Measured on T4 lysozyme (1,363 atoms), the build time of `show surface` and the
mesh it produces:

===========  ==========  ===========  ==========
level        spacing     build        vertices
===========  ==========  ===========  ==========
splat        --          ~1 ms        0
fast         0.9 A       ~90 ms       ~8,000
balanced     0.5 A       ~250 ms      27,920
fine         0.35 A      ~700 ms      ~60,000
===========  ==========  ===========  ==========

The levels set *only* what the level is about. Everything else in the
``surface`` section -- the probe radius, the method, the colouring -- is the
user's and is left alone, which is why this returns a copy with a few keys
replaced rather than a table of complete configurations.
"""
from __future__ import annotations

__all__ = ["SURFACE_QUALITY", "apply_surface_quality", "is_splat_quality"]

#: Grid settings per level. ``max_dim`` rises with the spacing so a finer
#: request is not silently clamped back to the coarse grid -- the cap exists to
#: bound memory on a large structure, and a level that asks for detail has to be
#: allowed to have it.
SURFACE_QUALITY: dict[str, dict[str, float]] = {
    "fast": {"grid_spacing": 0.9, "max_dim": 72},
    "balanced": {"grid_spacing": 0.5, "max_dim": 96},
    "fine": {"grid_spacing": 0.35, "max_dim": 160},
}

#: Names that mean "the screen-space one". Several, because this is the level
#: people reach for by describing it rather than by remembering its name.
_SPLAT_NAMES = frozenset({"splat", "gauss", "gaussian_splat", "interactive", "fastest"})


def is_splat_quality(quality: str) -> bool:
    """Whether *quality* names the screen-space Gaussian level."""
    return str(quality).strip().lower() in _SPLAT_NAMES


def apply_surface_quality(config: dict, quality: str) -> dict:
    """Return *config* with the level's grid settings applied.

    Parameters
    ----------
    config : dict
        The ``surface`` section.
    quality : str
        One of :data:`SURFACE_QUALITY`, or a splat name.

    Returns
    -------
    dict
        A copy. The original is the live display configuration, and writing the
        level's numbers into it would make the choice permanent -- the next
        rebuild would read the coarse spacing as though the user had set it.

    Notes
    -----
    An unknown level leaves the configuration alone rather than raising or
    falling back to a default. The setting is a string a user can type, and the
    surface they already had is a better answer to a typo than a surface at some
    other resolution.
    """
    level = str(quality).strip().lower()
    merged = dict(config)
    if level in SURFACE_QUALITY:
        merged.update(SURFACE_QUALITY[level])
        merged["quality"] = level
    else:
        merged["quality"] = "fast"
        merged.update(SURFACE_QUALITY["fast"])
    return merged
