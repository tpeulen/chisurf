"""The PyMOL-compatible settings layer.

Chimol's tunables live in the nested :data:`~chimol.config._DISPLAY_CONFIG`
dictionary, grouped by the subsystem that reads them (``cartoon``, ``ray``,
``camera``, ...). PyMOL instead exposes one flat namespace of named settings —
``cartoon_loop_radius``, ``ray_shadow``, ``field_of_view`` — and its ``set`` /
``get`` / ``unset`` commands accept nothing else. This module is the bridge: a
table mapping each PyMOL setting name onto the place in the nested config that
the renderer actually reads, so a PyMOL script can drive chimol unchanged.

Two rules keep the table honest:

* **Every entry is live.** A setting is listed only if some part of chimol reads
  the path it points at. Names PyMOL supports but chimol does not honour are
  absent, so ``set`` reports them as unknown rather than silently doing nothing.
* **The config is the storage.** Nothing is cached here; a setting is read and
  written straight through to :data:`_DISPLAY_CONFIG`, which is what an already
  open viewer consults on its next redraw.

Beyond the PyMOL names, ``set``/``get`` also accept a dotted path
(``cartoon.spline_tension``) to reach any config entry, including the ones with
no PyMOL equivalent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from .config import _DISPLAY_CONFIG

__all__ = [
    "SettingSpec",
    "UnknownSettingError",
    "SettingValueError",
    "SETTINGS",
    "coerce",
    "get_setting",
    "set_setting",
    "unset_setting",
    "toggle_setting",
    "resolve",
    "iter_settings",
    "setting_names",
]

_TRUE = {"on", "yes", "true", "1", "t", "y"}
_FALSE = {"off", "no", "false", "0", "f", "n"}

#: What a user types to clear a per-representation colour override. ``-1`` is
#: PyMOL's own spelling and works here for scripts that carry it; the words are
#: for people.
_DEFAULT_COLOR_TOKENS = {"-1", "default", "none", "off", "atom"}


class UnknownSettingError(KeyError):
    """Raised for a setting name that is neither registered nor a config path."""


class SettingValueError(ValueError):
    """Raised when a value cannot be coerced to a setting's declared type."""


@dataclass(frozen=True)
class SettingSpec:
    """One PyMOL setting and the config entry it drives.

    Attributes
    ----------
    name : str
        The PyMOL setting name, e.g. ``"cartoon_loop_radius"``.
    path : tuple of str
        Where the value lives in :data:`_DISPLAY_CONFIG`. A one-element path is
        a top-level key; longer paths index nested sections.
    kind : str
        ``"bool"``, ``"int"``, ``"float"``, ``"str"``, ``"vector"`` or
        ``"color"`` — see :func:`coerce`.
    default : object
        Value restored by ``unset``.
    doc : str
        One-line description, shown by ``help_setting``.
    stored : callable or None
        Maps the value a user gives onto the value the config stores, for the
        settings where PyMOL's name is not what chimol keeps. ``transparency``
        is the case that forced this: PyMOL counts 0 as fully opaque while the
        renderer reads an *alpha* where 1 is. Expressing that here keeps one
        storage -- the alternative, storing both, is two numbers that must agree
        and eventually will not.
    shown : callable or None
        The inverse, applied on read so ``get`` answers in the user's units.
    """

    name: str
    path: tuple[str, ...]
    kind: str
    default: Any
    doc: str = ""
    stored: Callable[[Any], Any] | None = None
    shown: Callable[[Any], Any] | None = None

    def to_config(self, value: Any) -> Any:
        """The value to write, given what the user asked for."""
        return self.stored(value) if self.stored is not None else value

    def from_config(self, value: Any) -> Any:
        """The value to report, given what the config holds."""
        return self.shown(value) if self.shown is not None else value


def _spec(
    name: str, path: str, kind: str, default: Any, doc: str,
    *, stored: Callable[[Any], Any] | None = None,
    shown: Callable[[Any], Any] | None = None,
) -> SettingSpec:
    return SettingSpec(
        name, tuple(path.split(".")), kind, default, doc, stored, shown
    )


def _complement(value: Any) -> float:
    """``1 - x``, clamped -- its own inverse, so one function does both ways."""
    return min(1.0, max(0.0, 1.0 - float(value)))


#: ``surface_quality`` level -> point separation in Angstrom, transcribed from
#: ``RepSurfaceSetSettings`` (``layer2/RepSurface.cpp``). PyMOL's own comments
#: for the levels are kept, because they are the only documentation of what the
#: numbers are *for*.
#:
#: This looked like a units mismatch and is not: PyMOL's level and chimol's grid
#: spacing are the **same quantity**, one naming the other. The level indexes
#: into four base separations, which are settings in their own right -- so they
#: are registered too, and this table is what reads them.
_QUALITY_BASE = {
    "best": 0.25, "normal": 0.5, "poor": 0.85, "miserable": 2.0,
}


def _quality_spacing(level: Any) -> float:
    """Point separation for a ``surface_quality`` level; smaller is finer."""
    cfg = _DISPLAY_CONFIG.get("surface", {}) or {}

    def base(name: str) -> float:
        return float(cfg.get(name, _QUALITY_BASE[name]))

    try:
        lvl = int(round(float(level)))
    except (TypeError, ValueError):
        lvl = 0
    if lvl >= 4:                      # "totally impractical", says PyMOL
        return base("best") / 4.0
    return {
        3: base("best") / 3.0,        # nearly impractical
        2: base("best") / 2.0,        # nearly perfect
        1: base("best"),              # good
        0: base("normal"),            # normal -- PyMOL's default
        -1: base("poor"),
        -2: base("poor") * 1.5,       # god awful
        -3: base("miserable"),        # miserable
    }.get(lvl, base("miserable") * 1.18)


def _spacing_quality(spacing: Any) -> int:
    """The level whose separation is nearest ``spacing``.

    A spacing set directly (``set surface.grid_spacing, 0.4``) need not be one
    of the eight the levels name, so ``get surface_quality`` answers with the
    closest rather than refusing. Reporting the nearest level is what makes the
    round trip exact on the level's own domain, which is all an integer setting
    can promise.
    """
    try:
        value = float(spacing)
    except (TypeError, ValueError):
        return 0
    levels = range(-4, 5)
    return min(levels, key=lambda lvl: abs(_quality_spacing(lvl) - value))


# --------------------------------------------------------------------------- #
# The table
# --------------------------------------------------------------------------- #
# Grouped the way PyMOL's setting browser groups them. The `path` column is the
# authority for where a value takes effect; when a name and a path disagree it
# is the path that was verified against the reading code.
_SPECS: tuple[SettingSpec, ...] = (
    # -- Camera / viewport --------------------------------------------------
    _spec("field_of_view", "camera.field_of_view", "float", 20.0,
          "Vertical field of view in degrees."),
    _spec("orthoscopic", "camera.orthoscopic", "bool", False,
          "Use an orthoscopic (parallel) projection instead of perspective."),
    _spec("mouse_mode", "camera.mouse_mode", "str", "pymol",
          "Drag behaviour: 'pymol' moves the object, 'chimol' moves the camera."),
    _spec("movie_recenter", "camera.recenter_on_frame", "bool", True,
          "Re-centre the camera on each frame as a trajectory plays. Keeps a "
          "molecule that wanders across the box in view; turn it off for a "
          "structure that grows, where following the centroid slides the scene "
          "out from under it."),

    # -- Per-representation colour overrides --------------------------------
    # PyMOL's rule, one line in each of its representations:
    # `c != cColorDefault ? c : ai->color`. `default` (or PyMOL's own -1) clears
    # the override and the representation goes back to the atoms' colours.
    _spec("stick_color", "colors.stick_color", "color_or_default", None,
          "Draw sticks in this colour whatever the atoms are; 'default' to "
          "follow the atom colours again."),
    _spec("cartoon_color", "colors.cartoon_color", "color_or_default", None,
          "Draw the cartoon in this colour whatever the residues are; "
          "'default' to follow the residue colours again."),
    _spec("surface_color", "colors.surface_color", "color_or_default", None,
          "Draw the surface in this colour whatever the atoms are; 'default' "
          "to follow the atom colours again."),

    # -- Silhouettes --------------------------------------------------------
    # ChimeraX's, not PyMOL's: PyMOL has no depth-buffer outline outside its ray
    # tracer. `lighting` sets the same values under the same names.
    _spec("silhouette", "silhouette.enabled", "bool", False,
          "Draw an outline where the depth buffer steps, as ChimeraX does."),
    _spec("silhouette_thickness", "silhouette.thickness", "float", 1.0,
          "Outline width in pixels."),
    _spec("depth_jump", "silhouette.depth_jump", "float", 0.03,
          "Depth difference, as a fraction of the scene depth, that counts as "
          "an edge. Smaller finds more edges."),
    _spec("silhouette_color", "silhouette.color", "color", [0.0, 0.0, 0.0, 1.0],
          "Outline colour."),

    # -- Background ---------------------------------------------------------
    _spec("bg_rgb", "background", "color", "k",
          "Background colour, as a colour name or an RGB triplet."),

    # -- Cartoon ------------------------------------------------------------
    _spec("cartoon_sampling", "cartoon.cartoon_sampling", "int", 7,
          "Spline points generated per residue along the cartoon path."),
    _spec("cartoon_loop_radius", "cartoon.loop_radius", "float", 0.2,
          "Radius of the tube drawn through loops."),
    _spec("cartoon_loop_quality", "cartoon.loop_quality", "int", 14,
          "Number of segments around the loop tube."),
    _spec("cartoon_oval_width", "cartoon.oval_width", "float", 0.25,
          "Half-thickness of the oval profile used for helices."),
    _spec("cartoon_oval_length", "cartoon.oval_length", "float", 1.35,
          "Half-breadth of the oval profile used for helices."),
    _spec("cartoon_oval_quality", "cartoon.oval_quality", "int", 20,
          "Number of segments around the oval profile."),
    _spec("cartoon_rect_width", "cartoon.rect_width", "float", 0.4,
          "Half-thickness of the rectangular profile used for strands."),
    _spec("cartoon_rect_length", "cartoon.rect_length", "float", 1.4,
          "Half-breadth of the rectangular profile used for strands."),
    _spec("cartoon_tube_radius", "cartoon.tube_radius", "float", 0.5,
          "Radius of the tube used by the tube cartoon style."),
    _spec("cartoon_tube_quality", "cartoon.tube_quality", "int", 18,
          "Number of segments around the cartoon tube."),
    _spec("cartoon_flat_sheets", "cartoon.flat_sheets", "bool", True,
          "Smooth the guide path through strands so sheets lie flat."),
    _spec("cartoon_flat_cycles", "cartoon.flat_cycles", "int", 4,
          "Smoothing passes applied when cartoon_flat_sheets is on."),
    _spec("cartoon_round_helices", "cartoon.round_helices", "bool", True,
          "Replace the helix guide path with the fitted helical axis."),
    _spec("cartoon_smooth_loops", "cartoon.smooth_loops", "bool", False,
          "Round the coil between elements; off in PyMOL too."),
    _spec("cartoon_smooth_cycles", "cartoon.smooth_cycles", "int", 2,
          "Smoothing passes applied when cartoon_smooth_loops is on."),
    _spec("cartoon_side_chain_helper", "cartoon.side_chain_helper", "bool", False,
          "Hide backbone sticks where a cartoon covers them, so side chains "
          "appear to grow out of the ribbon."),
    _spec("ribbon_side_chain_helper", "cartoon.side_chain_helper", "bool", False,
          "The same, for the ribbon. chimol draws one cartoon, so the two "
          "settings are one."),
    _spec("cartoon_refine_tips", "cartoon.refine_tips", "float", 10.0,
          "How hard a strand tip's tangent is aimed along the strand."),
    _spec("cartoon_refine_normals", "cartoon.refine_normals", "bool", True,
          "Keep the ribbon's face from flipping between neighbours."),
    _spec("cartoon_throw", "cartoon.throw", "float", 1.35,
          "How far the curve is thrown along the tangents between residues."),
    _spec("cartoon_power", "cartoon.power", "float", 2.0,
          "Biases where samples fall along each residue interval."),
    _spec("cartoon_power_b", "cartoon.power_b", "float", 0.52,
          "Shapes the throw envelope between residues."),

    # -- Spheres / sticks / dots -------------------------------------------
    _spec("sphere_scale", "balls.radius_multiplier", "float", 1.0,
          "Multiplier applied to sphere radii."),
    _spec("nonbonded_size", "balls.nonbonded_size", "float", 0.25,
          "Size of non-polymer atoms (waters, ions) relative to their vdW radius."),
    _spec("stick_radius", "sticks.radius", "float", 0.15,
          "Radius of the cylinders drawn for bonds."),
    _spec("stick_quality", "sticks.segments_circle", "int", 12,
          "Number of segments around a stick cylinder."),
    _spec("line_width", "sticks.width", "float", 2.0,
          "Line width in pixels for the line representation."),
    _spec("dot_width", "dots.size_px", "float", 8.0,
          "Point size in pixels for the dot representation."),

    # -- Hydrogen bonds / measurements --------------------------------------
    # The six that shape `distance ... mode=2`. They are one curve, not six
    # knobs: `cutoff_center` is the donor-acceptor cutoff head-on and
    # `cutoff_edge` the cutoff at `max_angle`, with the powers interpolating
    # between them. Setting `cutoff_edge` to zero flattens it to a plain
    # distance test, which is PyMOL's own escape hatch.
    _spec("h_bond_max_angle", "hbond.max_angle", "float", 63.0,
          "Largest acceptor-donor-hydrogen angle accepted, in degrees."),
    _spec("h_bond_cutoff_center", "hbond.cutoff_center", "float", 3.6,
          "Donor-acceptor cutoff at zero angle, in Angstroms."),
    _spec("h_bond_cutoff_edge", "hbond.cutoff_edge", "float", 3.2,
          "Donor-acceptor cutoff at the maximum angle; 0 disables the slide."),
    _spec("h_bond_power_a", "hbond.power_a", "float", 1.6,
          "First exponent shaping the angle-to-cutoff interpolation."),
    _spec("h_bond_power_b", "hbond.power_b", "float", 5.0,
          "Second exponent shaping the angle-to-cutoff interpolation."),
    _spec("h_bond_cone", "hbond.cone", "float", 180.0,
          "How wide a cone in front of the acceptor admits a hydrogen."),
    _spec("h_bond_exclusion", "hbond.exclusion", "int", 3,
          "Atoms this many bonds apart or closer are not polar contacts."),
    _spec("h_bond_from_proton", "hbond.from_proton", "bool", True,
          "Draw the contact from the hydrogen rather than the donor atom."),
    _spec("distance_exclusion", "measure.distance_exclusion", "int", 5,
          "Atoms this many bonds apart or closer are skipped by mode 3."),
    _spec("dash_length", "dash.length", "float", 0.15,
          "Length of one dash in a measurement line, in Angstroms."),
    _spec("dash_gap", "dash.gap", "float", 0.45,
          "Gap between dashes, in Angstroms."),
    _spec("dash_width", "dash.width", "float", 2.5,
          "Line width in pixels for measurement dashes."),
    _spec("dash_color", "dash.color", "color", [1.0, 1.0, 0.0, 1.0],
          "Colour of measurement dashes."),

    # -- Surface ------------------------------------------------------------
    # PyMOL counts transparency where chimol keeps alpha, and the two run
    # opposite ways: `transparency 0` is fully opaque, `alpha 1` is. The spec
    # carries the complement so there is one stored number rather than two that
    # must agree.
    # The default is chimol's shipped look, not PyMOL's. PyMOL's surface is
    # opaque (transparency 0); chimol ships alpha 0.85, and `unset` restores
    # *the default*, so it has to be the one this program actually ships.
    # Changing the shipped value is a config-version migration, not a settings
    # entry.
    _spec("transparency", "surface.alpha", "float", 0.15,
          "Surface transparency: 0 is opaque, 1 invisible (PyMOL's sense).",
          stored=_complement, shown=_complement),
    _spec("two_sided_lighting", "surface.two_sided", "bool", False,
          "Light the inside faces of a surface, which is what you see through "
          "a transparent one."),
    # One key, two consumers: the surface mesh reads it straight from the config
    # and `get_area` reads it through `get_setting`. It was registered *twice*,
    # onto two different config keys -- the later entry silently shadowed the
    # earlier, so `set solvent_radius` moved the number `get_area` uses and left
    # the surface you are looking at unchanged. That is the same "two numbers
    # that must agree and eventually will not" this table exists to prevent, and
    # a duplicate name is how it got in; `test_no_setting_is_registered_twice`
    # now fails on one.
    _spec("solvent_radius", "surface.probe_radius", "float", 1.4,
          "Probe radius in Angstrom: rolls the solvent-excluded surface, and "
          "is what get_area adds to each vdW radius when dot_solvent is on."),
    # A *level*, as PyMOL spells it, mapping onto the grid spacing chimol
    # stores -- see `_quality_spacing`. Registered as a float before, under
    # PyMOL's name but with PyMOL's argument meaning something else: a script
    # asking for `surface_quality 0` (normal) got a spacing of 0, which is not
    # "coarse" but "infinitely fine". chimol now ships PyMOL's own default
    # level (0 = `surface_normal`, 0.5 A), reached by a config migration that
    # changed the stored number without changing the picture -- see
    # DISPLAY_CONFIG_MIGRATIONS[8].
    _spec("surface_quality", "surface.grid_spacing", "int", 0,
          "Surface detail level, PyMOL's scale: 0 normal, higher is finer.",
          stored=_quality_spacing, shown=_spacing_quality),
    _spec("surface_best", "surface.best", "float", 0.25,
          "Point separation used by surface_quality levels 1 and above."),
    _spec("surface_normal", "surface.normal", "float", 0.5,
          "Point separation at surface_quality 0."),
    _spec("surface_poor", "surface.poor", "float", 0.85,
          "Point separation at surface_quality -1 and -2."),
    _spec("surface_miserable", "surface.miserable", "float", 2.0,
          "Point separation at surface_quality -3 and below."),

    # -- Raytracing / lighting ---------------------------------------------
    _spec("ray_shadow", "ray.shadow", "bool", True,
          "Cast shadows when raytracing."),
    _spec("antialias", "ray.antialias", "int", 2,
          "Supersampling factor used by the raytracer."),
    _spec("ambient", "ray.ambient", "float", 0.14,
          "Ambient light level in the raytraced image."),
    _spec("diffuse", "ray.diffuse", "float", 0.45,
          "Strength of the diffuse (lamp) lighting term."),
    _spec("specular", "ray.specular", "float", 0.25,
          "Intensity of specular highlights."),
    _spec("shininess", "ray.shininess", "float", 40.0,
          "Exponent of the specular reflection."),
    _spec("gamma", "ray.gamma", "float", 2.2,
          "Gamma applied to the raytraced image."),
    _spec("direct", "ray.direct", "float", 0.45,
          "Headlight brightness: how much a surface facing the viewer is lit, "
          "independent of the lamps (PyMOL `direct`)."),
    _spec("power", "ray.power", "float", 1.0,
          "Exponent on the headlight term; 1 is linear in the surface normal "
          "(PyMOL `power`)."),
    # Global, not the tracer's: both renderers read these three. See the key
    # move in `DISPLAY_CONFIG_KEY_MOVES` for why they no longer say `ray.`.
    _spec("depth_cue", "depth_cue.enabled", "bool", True,
          "Fade distant geometry into the background colour, in the viewport "
          "and in a traced image alike."),
    _spec("fog_start", "depth_cue.start", "float", 0.45,
          "Fraction of the depth range at which the cue begins."),
    _spec("fog", "depth_cue.intensity", "float", 1.0,
          "Depth-cue density: a value in (0, 1) pushes the far end of the cue "
          "beyond the scene, 1 or more clamps it to it."),

    # -- Cartoon putty ------------------------------------------------------
    # A tube whose thickness carries the b-factor. Defaults are PyMOL's, from
    # layer1/SettingInfo.h; the transform maths is analysis/putty.py.
    _spec("cartoon_putty_radius", "cartoon.putty_radius", "float", 0.4,
          "Base radius of the putty tube, before the per-residue scale."),
    _spec("cartoon_putty_scale_min", "cartoon.putty_scale_min", "float", 0.6,
          "Lower clamp on the putty scale, applied after the power."),
    _spec("cartoon_putty_scale_max", "cartoon.putty_scale_max", "float", 4.0,
          "Upper clamp on the putty scale, applied after the power."),
    _spec("cartoon_putty_scale_power", "cartoon.putty_scale_power", "float", 1.5,
          "Exponent applied to the putty scale by the nonlinear transforms."),
    _spec("cartoon_putty_range", "cartoon.putty_range", "float", 2.0,
          "Width of the distribution the putty z-score is spread over."),
    _spec("cartoon_putty_transform", "cartoon.putty_transform", "str",
          "normalized_nonlinear",
          "How the value becomes a radius: normalized (a z-score, the default "
          "and unit-free), relative, scaled, absolute, or implied_rms; each "
          "except the last in a linear and a nonlinear variant."),

    # -- Connectivity -------------------------------------------------------
    _spec("connect_cutoff", "sticks.connect_cutoff", "float", 0.35,
          "How far beyond the mean of two van der Waals radii two atoms may sit "
          "and still be bonded. Sulfur gets +0.2 and hydrogen -0.2, as in PyMOL."),

    # -- Surface area -------------------------------------------------------
    # Read by `get_area`. Defaults are PyMOL's own, from layer1/SettingInfo.h.
    _spec("dot_solvent", "surface.dot_solvent", "bool", False,
          "Measure the solvent-accessible surface rather than the van der "
          "Waals surface."),
    _spec("dot_density", "surface.dot_density", "int", 2,
          "Dot sampling level 0-4, giving 12, 42, 162, 642 or 2562 dots per "
          "atom. Higher is more accurate and slower."),

    # -- Sequence viewer ----------------------------------------------------
    _spec("seq_view", "sequence.seq_view", "bool", True,
          "Show the sequence viewer."),
    _spec("seq_view_label_spacing", "sequence.seq_view_label_spacing", "int", 5,
          "Residue-number label interval in the sequence viewer."),
)

SETTINGS: dict[str, SettingSpec] = {s.name: s for s in _SPECS}
"""Every registered PyMOL setting name, mapped to its :class:`SettingSpec`."""


# --------------------------------------------------------------------------- #
# Name resolution
# --------------------------------------------------------------------------- #
def setting_names() -> list[str]:
    """Return every registered setting name, sorted."""
    return sorted(SETTINGS)


def iter_settings() -> Iterator[SettingSpec]:
    """Iterate the registered settings in name order."""
    for name in setting_names():
        yield SETTINGS[name]


def resolve(name: str) -> SettingSpec:
    """Resolve ``name`` to a :class:`SettingSpec`.

    Accepts an exact setting name, an unambiguous prefix of one (as PyMOL's
    setting shortcuts do), or a dotted path into the display config for entries
    with no PyMOL name.

    Parameters
    ----------
    name : str
        Setting name, prefix, or dotted config path.

    Returns
    -------
    SettingSpec
        The matched setting. Dotted paths yield an ad-hoc spec whose ``kind`` is
        inferred from the value currently stored there.

    Raises
    ------
    UnknownSettingError
        If the name matches no setting and no existing config entry, or if a
        prefix is ambiguous.
    """
    key = (name or "").strip().lower()
    if not key:
        raise UnknownSettingError("no setting name given")

    spec = SETTINGS.get(key)
    if spec is not None:
        return spec

    if "." in key:
        return _spec_for_path(key)

    matches = [n for n in SETTINGS if n.startswith(key)]
    if len(matches) == 1:
        return SETTINGS[matches[0]]
    if len(matches) > 1:
        raise UnknownSettingError(
            f"'{name}' is ambiguous: " + ", ".join(sorted(matches))
        )
    raise UnknownSettingError(f"Unknown setting: {name}")


def _spec_for_path(dotted: str) -> SettingSpec:
    """Build a spec for a raw ``section.key`` config path that already exists."""
    path = tuple(dotted.split("."))
    node: Any = _DISPLAY_CONFIG
    for part in path:
        if not isinstance(node, dict) or part not in node:
            raise UnknownSettingError(f"Unknown setting: {dotted}")
        node = node[part]
    return SettingSpec(dotted, path, _kind_of(node), node,
                       "Chimol display-config entry.")


def _kind_of(value: Any) -> str:
    """Infer a coercion kind from a value already present in the config."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple)):
        return "vector"
    return "str"


# --------------------------------------------------------------------------- #
# Value coercion
# --------------------------------------------------------------------------- #
def coerce(value: Any, kind: str) -> Any:
    """Convert a command-line token to a setting's declared type.

    Booleans accept PyMOL's spellings (``on``/``off``, ``yes``/``no``,
    ``true``/``false``, ``1``/``0``); vectors accept ``[1, 2, 3]``, ``1 2 3`` or
    ``1,2,3``; colours accept either a colour name or a vector.

    Parameters
    ----------
    value : object
        Raw value, normally the string a command supplied.
    kind : str
        Target kind, as declared by a :class:`SettingSpec`.

    Returns
    -------
    object
        The converted value.

    Raises
    ------
    SettingValueError
        If the value does not parse as ``kind``.
    """
    if kind == "bool":
        if isinstance(value, bool):
            return value
        token = str(value).strip().lower()
        if token in _TRUE:
            return True
        if token in _FALSE:
            return False
        raise SettingValueError(f"expected on/off, got {value!r}")

    if kind in ("int", "float"):
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            raise SettingValueError(f"expected a number, got {value!r}") from None
        return int(round(number)) if kind == "int" else number

    if kind == "vector":
        return _as_vector(value)

    if kind in ("color", "color_or_default"):
        # PyMOL's per-representation colour settings carry a sentinel meaning
        # "no override, use the atom's own colour" -- the integer -1, which it
        # calls `cColorDefault` and every representation tests for
        # (`c != cColorDefault ? c : ai->color`). Stored as ``None``, because a
        # negative number is not a colour and a config full of -1 says nothing
        # to whoever reads it.
        if kind == "color_or_default" and (
            value is None or str(value).strip().lower() in _DEFAULT_COLOR_TOKENS
        ):
            return None
        # A colour name stays a name: chimol's background accepts 'k'/'white'
        # directly, and keeping the token means `get` echoes what was set.
        if isinstance(value, str) and not any(c in value for c in "[,0123456789"):
            return value.strip()
        try:
            return _as_vector(value)
        except SettingValueError:
            return str(value).strip()

    return str(value).strip()


def _as_vector(value: Any) -> list[float]:
    """Parse ``[1, 2, 3]``, ``1 2 3`` or ``1,2,3`` into a list of floats."""
    if isinstance(value, (list, tuple)):
        items: Sequence[Any] = value
    else:
        token = str(value).strip().strip("[]()")
        items = [p for p in token.replace(",", " ").split() if p]
    try:
        return [float(v) for v in items]
    except (TypeError, ValueError):
        raise SettingValueError(f"expected a numeric vector, got {value!r}") from None


# --------------------------------------------------------------------------- #
# Read / write
# --------------------------------------------------------------------------- #
def get_setting(name: str) -> Any:
    """Return the current value of ``name``.

    Parameters
    ----------
    name : str
        Setting name, prefix, or dotted config path.

    Returns
    -------
    object
        The stored value, or the spec's default when the config has no entry.
    """
    spec = resolve(name)
    node: Any = _DISPLAY_CONFIG
    for part in spec.path:
        if not isinstance(node, dict) or part not in node:
            return spec.default
        node = node[part]
    return spec.from_config(node)


def set_setting(name: str, value: Any) -> tuple[SettingSpec, Any]:
    """Write ``value`` to the setting ``name``.

    Parameters
    ----------
    name : str
        Setting name, prefix, or dotted config path.
    value : object
        Value to store; coerced to the setting's declared kind.

    Returns
    -------
    tuple
        The resolved :class:`SettingSpec` and the coerced value, so callers can
        report what was actually stored and refresh the right subsystem.

    Raises
    ------
    UnknownSettingError, SettingValueError
    """
    spec = resolve(name)
    # `toggle` on a boolean flips whatever it currently holds. A button that can
    # only say "on" or "off" has to read the setting first, and every caller
    # doing that themselves is how one of them ends up sending the literal word.
    if spec.kind == "bool" and str(value).strip().lower() == "toggle":
        coerced = not bool(get_setting(name))
    else:
        coerced = coerce(value, spec.kind)
    node: dict = _DISPLAY_CONFIG
    for part in spec.path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[spec.path[-1]] = spec.to_config(coerced)
    # Reported in the user's units, not the stored ones: `set transparency, 0.4`
    # must echo 0.4, not the 0.6 alpha it became.
    return spec, coerced


def unset_setting(name: str) -> tuple[SettingSpec, Any]:
    """Restore ``name`` to its default and return the spec and that default."""
    spec = resolve(name)
    node: dict = _DISPLAY_CONFIG
    for part in spec.path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[spec.path[-1]] = spec.to_config(spec.default)
    return spec, spec.default


def toggle_setting(name: str) -> tuple[SettingSpec, Any]:
    """Flip a boolean setting and return the spec and its new value.

    Raises
    ------
    SettingValueError
        If the setting is not boolean.
    """
    spec = resolve(name)
    if spec.kind != "bool":
        raise SettingValueError(f"{spec.name} is not a boolean setting")
    return set_setting(spec.name, not bool(get_setting(spec.name)))
