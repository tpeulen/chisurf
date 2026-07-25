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

from collections.abc import Iterator, Sequence
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
    """

    name: str
    path: tuple[str, ...]
    kind: str
    default: Any
    doc: str = ""


def _spec(name: str, path: str, kind: str, default: Any, doc: str) -> SettingSpec:
    return SettingSpec(name, tuple(path.split(".")), kind, default, doc)


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

    # -- Surface ------------------------------------------------------------
    _spec("solvent_radius", "surface.probe_radius", "float", 1.4,
          "Probe radius used when building the solvent-excluded surface."),
    _spec("surface_quality", "surface.grid_spacing", "float", 0.8,
          "Surface grid spacing in Angstroms; smaller is finer and slower."),

    # -- Raytracing / lighting ---------------------------------------------
    _spec("ray_shadow", "ray.shadow", "bool", True,
          "Cast shadows when raytracing."),
    _spec("antialias", "ray.antialias", "int", 2,
          "Supersampling factor used by the raytracer."),
    _spec("ambient", "ray.ambient", "float", 0.14,
          "Ambient light level in the raytraced image."),
    _spec("direct", "ray.diffuse", "float", 0.45,
          "Strength of the direct (camera) light."),
    _spec("specular", "ray.specular", "float", 0.25,
          "Intensity of specular highlights."),
    _spec("shininess", "ray.shininess", "float", 40.0,
          "Exponent of the specular reflection."),
    _spec("gamma", "ray.gamma", "float", 2.2,
          "Gamma applied to the raytraced image."),
    _spec("depth_cue", "ray.depth_cue", "bool", True,
          "Fade distant geometry into the background colour."),
    _spec("fog_start", "ray.fog_start", "float", 0.45,
          "Fraction of the depth range at which fog begins."),
    _spec("fog", "ray.fog_intensity", "float", 1.0,
          "Fog density."),

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

    if kind == "color":
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
    return node


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
    coerced = coerce(value, spec.kind)
    node: dict = _DISPLAY_CONFIG
    for part in spec.path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[spec.path[-1]] = coerced
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
    node[spec.path[-1]] = spec.default
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
