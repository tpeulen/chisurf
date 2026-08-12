"""Display configuration loading for Chimol."""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

try:
    import chisurf.core.settings as _cs_settings
except Exception:  # pragma: no cover - moview can run without chisurf
    _cs_settings = None

DISPLAY_CONFIG_VERSION: int = 15
"""Current version of the chimol_display.json schema.

Increment this when keys are added, renamed, or removed, **or when a default
changes**, and record the change in :data:`DISPLAY_CONFIG_MIGRATIONS` so an
existing user copy picks it up.
"""

#: Defaults that changed, by the version that changed them:
#: ``{version: {section: {key: (old_default, new_default)}}}``.
#:
#: A user's copy of ``chimol_display.json`` is written once and then never
#: touched again, so *changing a default here reaches nobody who already has
#: one* -- which is every existing user. The version check that was supposed to
#: catch this was never called from anywhere.
#:
#: A value is updated only where the user's copy still holds the **old
#: default**, which means they never changed it. Anything else is a deliberate
#: choice and is left exactly as it is. That distinction is the whole point:
#: refreshing the file wholesale would throw away the settings people came to
#: rely on, and refreshing nothing leaves every appearance fix stranded in the
#: package.
DISPLAY_CONFIG_MIGRATIONS: dict[int, dict[str, dict[str, tuple]]] = {
    4: {
        "metaball": {
            # A metaball should look like a wet gel, not like clay. See the log
            # for 2026-07-28: the normals were the reason it never could.
            "ao_strength": (0.9, 0.35),
            "shininess": (22.0, 96.0),
            "specular_strength": (0.12, 0.85),
            "rim_strength": (0.2, 0.55),
            "rim_power": (3.0, 2.2),
            "sigma_factor": (2.2, 2.8),
        },
    },
    5: {
        "metaball": {
            # Fusion, which is what actually makes a metaball read as jelly:
            # the material was already glossy and the surface still showed every
            # bead. Larger sigma merges neighbours into smooth lobes. 9.0 was
            # tried and is too far -- the molecule becomes a featureless egg --
            # so this is the point where the fold is still legible.
            "sigma_factor": (2.8, 6.5),
            "iso_value": (0.1, 0.06),
        },
    },
    6: {
        "metaball": {
            # 6.5 went too far, and measuring says why: at that width the
            # surface encloses ~93,700 A^3 around a 165-residue protein whose
            # own envelope is ~25,000 -- the blob was not merely smooth, it sat
            # far off the molecule, and at 6.5 no iso_value can pull it back
            # (even 0.95 bottoms out at 71,400). 3.0 keeps the coherent gel skin
            # while the fold's lobes read again, and it builds ~6x faster.
            "sigma_factor": (6.5, 4.0),
            "iso_value": (0.06, 0.10),
            # And a jelly is translucent. This is only shippable now that the
            # normals point outward and the surface terms scale with alpha;
            # before either fix, a sub-1 alpha gave opaque milk.
            "alpha": (1.0, 0.55),
        },
    },
    8: {
        "surface": {
            # The grid spacing was being applied in *scene* units while it is
            # written in Angstrom, so 0.8 asked for 0.08 A and `max_dim` clamped
            # it straight back -- the setting had no measurable effect and the
            # cap decided the resolution. With the conversion fixed, 0.8 would
            # genuinely mean 0.8 A and the default surface would get *coarser*
            # than everyone has been seeing (13 654 vertices on 148L against
            # 27 114). 0.5 is PyMOL's own `surface_normal`, it is
            # `surface_quality 0`, and it reproduces today's appearance
            # (25 876 vertices). So the number changes and the picture does not.
            "grid_spacing": (0.8, 0.5),
        },
    },
    7: {
        "metaball": {
            # Version 6 shipped three different widths over one afternoon, and
            # whoever launched the app in between was left holding one of them
            # -- their file already stamped 6, so nothing above could ever reach
            # it. 3.0 and 3.5 are those intermediates: both wrap a helical
            # bundle too tightly, which is precisely the tearing this was meant
            # to fix. Named here so the correction actually arrives.
            "sigma_factor": ((3.0, 3.5), 4.0),
            "iso_value": ((0.14, 0.12), 0.10),
        },
    },
    10: {
        "selection": {
            # The marker became PyMOL's: pink, at every selected atom, sized by
            # its own width rule. Shipping the new default alone would have
            # reached nobody -- a user copy is written once and never refreshed,
            # so every existing install keeps the yellow this replaces, which is
            # the colour the "the selection is not visible" report was looking
            # at.
            "color": ([1.0, 1.0, 0.0, 1.0], [1.0, 0.2, 0.6, 1.0]),
        },
    },
    12: {
        "occlusion": {
            # Not a change of look: a change of arithmetic that had to be paid
            # for somewhere. The cast-shadow kernel used to step along the
            # shadow ray in strides of `shadow_distance` and search a 3x3x3 cell
            # neighbourhood at each stride -- and consecutive neighbourhoods
            # overlap, so an occluder in a shared cell was accumulated two or
            # three times. Measured on 148L the accumulated blockage came out
            # 2.79x too large at the median (2.0 at p10, 3.0 at p90), varying
            # per vertex with how the cells happened to fall.
            #
            # The kernel now counts each occluder once. Carrying the strength
            # keeps every existing scene looking as it did, rather than making
            # a correctness fix arrive as "the shadows went pale".
            "shadow_strength": (1.0, 2.8),
        },
    },
    15: {
        "balls": {
            # Impostors for every sphere, not only for a bead model of twenty
            # thousand. An impostor is the *exact* sphere where a tessellation
            # is a polyhedron, and it costs two triangles against ninety-two:
            # `show spheres` on 148L was 124,704 triangles built by 94 ms of
            # NumPy per rebuild, and is now 2,726 built by nothing. The knob
            # stays -- set it high to get the mesh back -- but its floor has no
            # reason to be above one.
            "impostor_min_atoms": (20000, 1),
        },
    },
    17: {
        "label": {
            # The size nobody was ever seeing: `paint_labels` hard-coded 10
            # while this said 14, so the setting was documented, stored and
            # read by nothing. Honouring it is already an increase, and the
            # size actually on screen -- 10 -- was reported as too small, so
            # the default moves too rather than restoring a number that was
            # never in effect.
            "size": (14.0, 16.0),
        },
    },
    14: {
        "selection": {
            # A three-pixel marker cannot show a three-band marker: at PyMOL's
            # floor the white core is a fifth of a pixel, so the indicator
            # resolves to a single pink speck per atom and a selection reads as
            # a scatter of dots over the molecule -- which is how it was
            # reported, twice. The rule and the clamp are unchanged; the band
            # the clamp allows is wide enough for the bands to exist.
            "width": (3.0, 7.0),
            "width_max": (10.0, 16.0),
        },
    },
}


#: Settings that moved to a different section, by the version that moved them:
#: ``{version: ((old_section, old_key, new_section, new_key, old_default), ...)}``.
#:
#: :data:`DISPLAY_CONFIG_MIGRATIONS` can only change a *value*, so a setting that
#: turns out to live in the wrong place has nowhere to go: leaving it means the
#: name reads wrong for ever, and moving it silently discards whatever the user
#: had chosen. A move carries the value across when it is not the old default --
#: the same "they chose this" test the value migrations use -- and drops the old
#: key either way, so the section it left does not keep a stale twin that some
#: reader might still find.
DISPLAY_CONFIG_KEY_MOVES: dict[int, tuple[tuple[str, str, str, str, object], ...]] = {
    9: (
        # PyMOL's `depth_cue`, `fog` and `fog_start` are **global**: they govern
        # the viewport, and the tracer follows them. They were registered under
        # `ray.` back when only the tracer honoured them, so once the viewport
        # gained its depth cue the prefix said something untrue about who obeys
        # them. The feature is the depth cue; fog is how it is implemented.
        ("ray", "depth_cue", "depth_cue", "enabled", True),
        ("ray", "fog_start", "depth_cue", "start", 0.45),
        ("ray", "fog_intensity", "depth_cue", "intensity", 1.0),
    ),
}

#: Keys deleted outright, by the version that deleted them:
#: ``{version: ((section, key), ...)}``.
#:
#: Deleting a key from the packaged defaults reaches **nobody who already has a
#: copy of the file**, and the two migration kinds above cannot express a
#: deletion: one changes a value and the other moves it somewhere. So a removed
#: setting stayed in every existing user's config, still reachable through
#: ``set``, still stored on change, and read by nothing.
#:
#: That is not hypothetical. ``sticks.ambient_occlusion`` was removed as a dead
#: second switch for what ``occlusion.enabled`` governs, and the guard test that
#: asserts there is only one such switch passed anyway -- because it runs against
#: a *fresh* settings directory, where the key is genuinely gone. On an existing
#: profile both switches were still there. A deletion needs a migration for the
#: same reason a default change does.
DISPLAY_CONFIG_KEY_REMOVALS: dict[int, tuple[tuple[str, str], ...]] = {
    11: (
        # Registered, reachable, stored, and read by nothing -- sticks bake no
        # occlusion at all, so there was never anything for it to switch on.
        ("sticks", "ambient_occlusion"),
    ),
}


_update_listeners: list[Callable[[], None]] = []
"""Registered callbacks to notify when display config is reloaded."""


def register_update_listener(listener: Callable[[], None]) -> None:
    """Register a callback invoked after each config reload."""
    _update_listeners.append(listener)


def unregister_update_listener(listener: Callable[[], None]) -> None:
    """Remove a previously registered callback."""
    try:
        _update_listeners.remove(listener)
    except ValueError:
        pass


def get_package_display_config_path() -> Path:
    """Return the path to the chimol_display.json shipped with the package."""
    return Path(__file__).with_name("chimol_display.json")


def get_user_display_config_path() -> Path | None:
    """Return the expected user ``chimol_display.json`` path, or ``None``.

    When chisurf is available this is ``~/.chisurf/chimol_display.json``;
    otherwise ``None`` is returned (standalone Chimol uses the package copy).
    """
    if _cs_settings is not None:
        try:
            return _cs_settings.get_path("settings") / "chimol_display.json"
        except Exception:
            return None
    return None


def check_for_display_config_update() -> bool:
    """Return ``True`` if the user's ``chimol_display.json`` is outdated.

    Compares the ``_version`` field in the user copy (if any) against
    :data:`DISPLAY_CONFIG_VERSION`.  Returns ``False`` when there is no
    user copy or when the versions match.
    """
    user_path = get_user_display_config_path()
    if user_path is None or not user_path.is_file():
        return False
    try:
        with user_path.open("r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        user_version = cfg.get("_version", 0)
        return user_version < DISPLAY_CONFIG_VERSION
    except Exception:
        return False


def apply_display_config_migrations(cfg: dict, from_version: int) -> list[str]:
    """Bring *cfg* forward, changing only values the user never touched.

    Parameters
    ----------
    cfg : dict
        A loaded ``chimol_display.json``, modified in place.
    from_version : int
        The ``_version`` the file was written with; 0 when it has none.

    Returns
    -------
    list of str
        ``"section.key"`` for each value updated, so the caller can report or
        persist. Empty when nothing changed.

    Notes
    -----
    A value moves only if it still equals the **old default**. If it differs,
    the user chose it and it stays -- a migration that overwrote choices would
    be worse than one that never ran.

    Keys that changed *section* are handled here too, from
    :data:`DISPLAY_CONFIG_KEY_MOVES`, and the rule is the mirror image: the
    value is carried across when it is **not** the old default, because that is
    what the user chose and it must not be lost with the name.
    """
    changed: list[str] = []
    for version in sorted(DISPLAY_CONFIG_MIGRATIONS):
        if version <= int(from_version or 0):
            continue
        for section, keys in DISPLAY_CONFIG_MIGRATIONS[version].items():
            block = cfg.get(section)
            if not isinstance(block, dict):
                continue
            for key, (old, new) in keys.items():
                if key not in block:
                    continue
                current = block[key]
                if any(_same_value(current, candidate) for candidate in _as_tuple(old)):
                    block[key] = new
                    changed.append(f"{section}.{key}")

    for version in sorted(DISPLAY_CONFIG_KEY_MOVES):
        if version <= int(from_version or 0):
            continue
        for old_section, old_key, new_section, new_key, old_default in (
            DISPLAY_CONFIG_KEY_MOVES[version]
        ):
            source = cfg.get(old_section)
            if not isinstance(source, dict) or old_key not in source:
                continue
            value = source.pop(old_key)
            if not _same_value(value, old_default):
                target = cfg.get(new_section)
                if not isinstance(target, dict):
                    target = {}
                    cfg[new_section] = target
                target[new_key] = value
            changed.append(f"{old_section}.{old_key} -> {new_section}.{new_key}")

    # Deletions last: a key that a later version removes may well be one an
    # earlier version moved or re-defaulted, and running the removals first
    # would make those entries silently no-ops.
    for version in sorted(DISPLAY_CONFIG_KEY_REMOVALS):
        if version <= int(from_version or 0):
            continue
        for section, key in DISPLAY_CONFIG_KEY_REMOVALS[version]:
            block = cfg.get(section)
            if isinstance(block, dict) and key in block:
                # Removed whatever the value is. Unlike a default change, there
                # is no "the user chose this" case to protect: the setting is
                # gone, and keeping a chosen value for it would keep exactly the
                # dead second switch the removal exists to delete.
                block.pop(key)
                changed.append(f"{section}.{key} (removed)")
    return changed


def _as_tuple(old) -> tuple:
    """Return the superseded value(s) of a migration entry as a tuple.

    An entry may name **several** old defaults, because a default can change
    more than once within one version during development. Anyone who launched
    the app while an intermediate value was the shipped one has a file already
    stamped with the current version, and no later migration will ever run for
    them: the correction is unreachable, and they stay on a value nobody
    intended. Naming the intermediate values explicitly is what reaches them.
    """
    return old if isinstance(old, tuple) else (old,)


def _same_value(current, old) -> bool:
    """Return whether *current* is the default *old*, comparing floats loosely."""
    if (
        isinstance(current, (int, float))
        and isinstance(old, (int, float))
        and not isinstance(current, bool)
    ):
        return abs(float(current) - float(old)) < 1e-9
    return current == old


#: Key in the user's copy that switches the start-up comparison off.
#: Absent means "ask" -- opting out has to be a decision someone made, not the
#: state a file happens to be in.
UPDATE_PROMPT_KEY = "_ask_about_package_defaults"


def diff_against_package(cfg: dict | None = None) -> dict[str, tuple]:
    """Return where a config disagrees with the one the package ships.

    Migration can only correct values it *names*; anything else stays, whether
    it was chosen deliberately or stranded by a default that moved twice inside
    one version. This says what actually differs, which is the question the
    start-up prompt asks and the only check that does not depend on the version
    stamp being right.

    Parameters
    ----------
    cfg : dict, optional
        A loaded config. Defaults to the user's copy on disk; ``{}`` when there
        is none, which reports no differences.

    Returns
    -------
    dict
        ``{"section.key": (yours, shipped)}``, empty when they agree. Meta keys
        (those starting with ``_``) are never compared: they describe the file
        rather than the rendering.
    """
    if cfg is None:
        cfg = _read_user_display_config() or {}
    try:
        shipped = json.loads(
            get_package_display_config_path().read_text(encoding="utf-8")
        )
    except Exception:  # pragma: no cover - a package without its own config
        return {}

    differences: dict[str, tuple] = {}
    for section, block in shipped.items():
        if section.startswith("_") or not isinstance(block, dict):
            continue
        mine = cfg.get(section)
        if not isinstance(mine, dict):
            continue
        for key, shipped_value in block.items():
            if key.startswith("_") or key not in mine:
                continue
            if not _same_value(mine[key], shipped_value):
                differences[f"{section}.{key}"] = (mine[key], shipped_value)
    return differences


def _read_user_display_config() -> dict | None:
    """Return the user's copy as a dict, or ``None`` when there is none."""
    path = get_user_display_config_path()
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_update_prompt_enabled() -> bool:
    """Return whether start-up should ask about differences from the package."""
    cfg = _read_user_display_config() or {}
    return bool(cfg.get(UPDATE_PROMPT_KEY, True))


def set_update_prompt_enabled(enabled: bool) -> bool:
    """Turn the start-up comparison on or off, persistently.

    Parameters
    ----------
    enabled : bool
        ``False`` to stop asking.

    Returns
    -------
    bool
        Whether the preference reached the disk. A settings directory that
        cannot be written is a permissions problem, not a reason to fail.
    """
    path = get_user_display_config_path()
    cfg = _read_user_display_config()
    if path is None or cfg is None:
        return False
    cfg[UPDATE_PROMPT_KEY] = bool(enabled)
    try:
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except Exception:  # pragma: no cover - unwritable settings directory
        logging.getLogger(__name__).debug(
            "Could not persist the display-config update preference", exc_info=True
        )
        return False
    return True


def adopt_package_values(names) -> list[str]:
    """Copy the shipped values for *names* into the user's config, and save.

    Parameters
    ----------
    names : iterable of str
        ``"section.key"`` entries, as reported by :func:`diff_against_package`.

    Returns
    -------
    list of str
        The names actually written.
    """
    path = get_user_display_config_path()
    cfg = _read_user_display_config()
    if path is None or cfg is None:
        return []
    try:
        shipped = json.loads(
            get_package_display_config_path().read_text(encoding="utf-8")
        )
    except Exception:  # pragma: no cover
        return []

    adopted: list[str] = []
    for name in names:
        section, _, key = str(name).partition(".")
        source = shipped.get(section)
        target = cfg.get(section)
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        if key in source:
            target[key] = source[key]
            adopted.append(name)

    if adopted:
        cfg["_version"] = DISPLAY_CONFIG_VERSION
        try:
            path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        except Exception:  # pragma: no cover - unwritable settings directory
            logging.getLogger(__name__).debug(
                "Could not write the adopted display defaults", exc_info=True
            )
            return []
    return adopted


def _write_user_display_config(path, cfg: dict) -> None:
    """Write *cfg* back to the user's copy, stamped with the current version.

    Failure is not fatal: the migrated values are already in the dict the
    session will use, and a config that cannot be written is a permissions
    problem rather than a reason to refuse to draw.
    """
    try:
        payload = dict(cfg)
        payload["_version"] = DISPLAY_CONFIG_VERSION
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    except Exception:  # pragma: no cover - unwritable settings directory
        logging.getLogger(__name__).debug(
            "chimol: could not update %s", path, exc_info=True
        )


def _load_display_config() -> dict:
    """Load Chimol display configuration from JSON file.

    All tunable visual parameters (cartoon radius, AO strength, ball sizes,
    etc.) are collected in ``chimol_display.json``. If the file cannot be
    read, sensible defaults are used. For backward compatibility, legacy
    ``molview_display.json`` or ``protview_display.json`` are also accepted
    if present.
    """

    default = {
        "_version": DISPLAY_CONFIG_VERSION,
        # Which backend draws the viewport. `wgpu` is the WGSL renderer that the
        # desktop and the browser share; `opengl` is the older one, and is used
        # automatically anyway wherever no WebGPU adapter can be created.
        "renderer": {"backend": "wgpu"},
        "background": "k",
        "defaults": {
            "color_mode": "by_sequence",
        },
        "grid": {"size": 20.0, "spacing": 1.0},
        "info_overlay": {
            "max_width": 260,
            "min_width": 180,
            "full_height": True,
        },
        "cartoon": {
            # PyMOL's `cartoon_side_chain_helper`, off by default as it is
            # there. Read by MolView._apply_side_chain_helper, which drops the
            # backbone bonds a cartoon already covers from sticks and lines.
            "side_chain_helper": False,
            "putty_radius": 0.4,
            "putty_scale_min": 0.6,
            "putty_scale_max": 4.0,
            "putty_scale_power": 1.5,
            "putty_range": 2.0,
            "putty_transform": "normalized_nonlinear",
            "radius_scale": 0.01,
            "min_radius": 0.5,
            "segments_circle": 18,
            "subdivisions": 7,
            "cartoon_sampling": 7,
            "tube_radius": 0.5,
            "tube_quality": 18,
            "ao_radius": 4.0,
            "ao_max_neighbors": 16,
            "ao_strength": 0.45,
            "style": "ribbon",
            "profile_segments": 20,
            # Slight tension to reduce wiggly beta strands; 0 = classic Catmull-Rom
            "spline_tension": 0.3,
            # PyMOL-style dimensions in scene units, not scaled by molecule size.
            "loop_radius": 0.2,
            "loop_quality": 14,
            "rect_width": 0.4,
            "rect_length": 1.4,
            "oval_width": 0.25,
            "oval_length": 1.35,
            "oval_quality": 20,
            "arrow_sampling": 2,
            # PyMOL's inter-residue curve (see geometry/spline.py).
            "throw": 1.35,
            "power": 2.0,
            "power_b": 0.52,
            "refine_tips": 10.0,
            "refine_normals": True,
            # Guide-path conditioning, matching the PyMOL settings of the same
            # name (cartoon_flat_sheets / cartoon_round_helices).
            "flat_sheets": True,
            "flat_cycles": 4,
            "round_helices": True,
            # PyMOL's cartoon_smooth_loops family. Off by default there and
            # here: it rounds the coil but pulls it away from the real backbone.
            "smooth_loops": False,
            "smooth_cycles": 2,
            "smooth_first": 1,
            "smooth_last": 1,
            # Legacy ss_shapes kept for backward compatibility
            "ss_shapes": {
                "helix": {"width": 0.5, "thickness": 1.35, "profile_power": 1.6},
                "strand": {"width": 1.8, "thickness": 1.5,
                           "arrow_scale": 0.2, "profile_power": 18.0},
                "coil": {"width": 0.5, "thickness": 0.5, "profile_power": 2.2},
            },
        },
        # PyMOL has no equivalent outside its ray tracer; ChimeraX exposes it as
        # a per-scene setting, and the names here are its names.
        "silhouette": {
            "enabled": False,
            "thickness": 1.0,
            "depth_jump": 0.03,
            "color": [0.0, 0.0, 0.0, 1.0],
        },
        "balls": {
            "size_scale": 0.04,
            "min_size": 3.0,
            "radius_multiplier": 1.0,
            # Non-polymer atoms (waters, ions) are drawn at this fraction of
            # their vdW radius, matching PyMOL's nonbonded_size.
            "nonbonded_size": 0.25,
            "ao_radius": 4.0,
            "ao_max_neighbors": 24,
            "ao_strength": 0.5,
            "max_atoms": 8000,
            # Sphere tessellation for atom-ball glyphs. Thousands of small balls
            # do not need the 16x32 default sphere; a coarse sphere keeps the
            # merged mesh light for both the CPU build and the GPU.
            "sphere_lat": 10,
            "sphere_lon": 16,
            # Past this many beads an integrative model is drawn as sphere
            # impostors -- one vertex each, shaded as a sphere in the fragment
            # shader -- instead of a merged mesh of ~160 vertices per bead.
            "impostor_min_atoms": 1,
        },
        "overlay": {
            # Cap on rendered points for transparent point-cloud overlays (AV
            # clouds, dye densities). Overdraw of transparent sprites scales with
            # this; the cloud is random-subsampled with alpha compensation above
            # the cap so it stays fast without visibly thinning.
            "max_points": 30000,
        },
        "dots": {
            "size_px": 8.0,
            "max_points": 250000,
            "alpha": 1.0,
            "base_color": [0.8, 0.8, 1.0, 1.0],
            "px_mode": True,
        },
        "surface": {
            # PyMOL's `transparency` is the complement of this; the settings
            # table carries the conversion so only alpha is stored.
            "two_sided": False,
            # The four point separations PyMOL's surface_quality levels select
            # between (layer2/RepSurface.cpp). Named settings in PyMOL too.
            "best": 0.25,
            "normal": 0.5,
            "poor": 0.85,
            "miserable": 2.0,
            "dot_solvent": False,
            "dot_density": 2,
            "size_scale": 0.03,
            "min_size": 2.5,
            "ao_radius": 4.5,
            "ao_max_neighbors": 24,
            "ao_strength": 0.6,
            "alpha": 0.85,
            "max_points": 10000,
            "color_mode": "ao_gray",
            "base_color": [0.85, 0.85, 0.92, 1.0],
            # 0.5 A is PyMOL's `surface_normal`, i.e. `surface_quality 0`.
            "grid_spacing": 0.5,
            "iso_value": 0.5,
            "padding": 3.0,
            "max_dim": 96,
            "mesh_sigma_factor": 1.0,
            "mesh_sigma_default": 1.8,
            "method": "gaussian",
            "probe_radius": 1.4,
        },
        "metaball": {
            # Density field function: "wyvill" (compact support, faster) or "gaussian"
            "field_function": "wyvill",
            # Isosurface threshold for marching cubes (lower = larger, blobbier surface)
            "iso_value": 0.10,
            # Per-atom sigma multiplier (higher = rounder, more fused blobs).
            # A gel should have no *beads*, but it must still have a shape: at
            # 6.5 the surface enclosed ~93,700 A^3 around a protein whose own
            # envelope is ~25,000 and the fold disappeared into an egg -- and no
            # iso_value could pull it back, since even 0.95 bottomed out at
            # 71,400. Set from the hard case, a helical stalk rather than a
            # globular protein: below 3.5 the surface wraps each helix on its
            # own and the envelope tears open between them.
            "sigma_factor": 4.0,
            # Grid resolution in Angstroms (smaller = finer mesh, slower)
            "grid_spacing": 0.6,
            # Extra space around bounding box in Angstroms
            "padding": 5.0,
            # Maximum grid dimension (auto-coarsens spacing if exceeded)
            "max_dim": 128,
            # Mesh transparency (1.0 = opaque, <1.0 = transparent). A gel is
            # translucent, and this is only shippable now that two things are
            # fixed. The mesh normals used to point *inward*, so the shader's
            # fresnel term drove alpha to opaque whatever was asked for. And
            # reflection, rim and specular were added at full strength on every
            # one of the many sheets an isosurface folds into, which stacked up
            # as white -- the "cotton wool" this comment used to describe. Both
            # now scale with alpha, so the surface stays coloured and the knob
            # does something across its range.
            "alpha": 0.55,
            # Ambient occlusion strength (0.0 = off, 1.0 = maximum darkening in
            # crevices). Deliberately moderate: heavy occlusion reads as dust
            # settling in the creases, which is the opposite of a wet surface.
            "ao_strength": 0.35,
            # AO search radius in Angstroms (larger = broader, softer crevice shadows)
            "ao_radius": 7.0,
            # Material shininess (higher = sharper specular highlights). High:
            # a gel's highlight is a small hard glint, not a broad sheen.
            "shininess": 96.0,
            # Specular highlight intensity (0.0 = matte, 1.0 = mirror-like).
            # High: this *is* meant to look like wet plastic.
            "specular_strength": 0.85,
            # Rim lighting strength (edge glow). Strong, because light carried
            # through a translucent body and out at a grazing edge is the other
            # half of what makes something look like jelly rather than stone.
            "rim_strength": 0.55,
            # Rim lighting falloff power (higher = sharper edge)
            "rim_power": 2.2,
            # Which normals to shade with. "isosurface" takes them from the
            # density field at each vertex; "density" replaces them with a
            # Gaussian-weighted average over several bead radii, which is far
            # smoother -- and smoother is not better: it airbrushes the surface
            # into a soft glow that no specular highlight survives, which is why
            # a metaball never looked wet.
            "normals": "isosurface",
            # Use only surface-exposed atoms (faster, cleaner surface)
            "surface_only": True,
            # Neighbor search radius for surface classification (Angstroms)
            "surface_radius": 5.0,
            # Max neighbors to be considered surface-exposed
            "surface_max_neighbors": 20,
        },
        # What counts as a hydrogen bond, and how a measurement is drawn.
        # PyMOL's defaults, from layer1/SettingInfo.h; the two cutoffs are the
        # ends of an angle-dependent interpolation rather than two independent
        # distances, so changing one alone tilts the curve.
        "hbond": {
            "max_angle": 63.0,
            "cutoff_center": 3.6,
            "cutoff_edge": 3.2,
            "power_a": 1.6,
            "power_b": 5.0,
            "cone": 180.0,
            "exclusion": 3,
            "from_proton": True,
        },
        "measure": {
            # `distance ... mode=3` drops pairs this many bonds apart or closer,
            # which is what stops a "contact" map from being mostly covalent
            # bonds and their neighbours.
            "distance_exclusion": 5,
        },
        "dash": {
            "length": 0.15,
            "gap": 0.45,
            "width": 2.5,
            "color": [1.0, 1.0, 0.0, 1.0],
        },
        "sticks": {
            "connect_cutoff": 0.35,
            # Analytic cylinders rather than a twelve-sided tube. `False`
            # restores the mesh, which is only worth doing to compare them.
            "impostors": True,
            "width": 2.0,
            "radius": 0.15,
            "segments_circle": 12,
            "max_bonds": 20000,
            "bond_max_length": 1.9,
            # `ambient_occlusion` used to live here. It was a second switch for
            # something `occlusion.enabled` already governs: registered,
            # reachable through `set sticks.ambient_occlusion`, stored on change,
            # and read by nothing. Removed rather than wired up, because sticks
            # bake no occlusion at all -- there was nothing for it to turn on.
        },
        "colors": {
            "base": [0.8, 0.8, 1.0, 1.0],
            # PyMOL's per-representation colour overrides. `None` is its
            # `cColorDefault` (-1): no override, so the representation takes
            # each atom's own colour. Every one of its representations tests
            # exactly this -- `c != cColorDefault ? c : ai->color` -- so one
            # sentinel and one rule serve all three.
            "stick_color": None,
            "cartoon_color": None,
            "surface_color": None,
            "cell_color": None,
            "aa_groups": {
                "hydrophobic": [0.4, 0.8, 0.4, 1.0],
                "polar": [0.4, 0.7, 0.9, 1.0],
                "positive": [0.3, 0.3, 0.9, 1.0],
                "negative": [0.9, 0.3, 0.3, 1.0],
                "gly": [0.8, 0.8, 0.8, 1.0],
            },
            "secondary_structure": {
                "helix": [0.3, 0.3, 0.9, 1.0],
                "strand": [0.9, 0.3, 0.3, 1.0],
                "coil": [0.9, 0.9, 0.7, 1.0],
            },
            "sequence_gradient": {
                "start": [0.95, 0.45, 0.25, 1.0],
                "end": [0.25, 0.55, 0.95, 1.0],
            },
            "element_cpk": {
                "H": [1.0, 1.0, 1.0, 1.0],
                "C": [0.5, 0.5, 0.5, 1.0],
                "N": [0.0, 0.0, 1.0, 1.0],
                "O": [1.0, 0.0, 0.0, 1.0],
                "S": [1.0, 1.0, 0.0, 1.0],
                "P": [1.0, 0.65, 0.0, 1.0],
                "default": [0.8, 0.8, 0.8, 1.0],
            },
        },
        # PyMOL's selection indicator, name for name: `selection_width` (3),
        # `selection_width_max` (10) and `selection_width_scale` (2.0) from its
        # `SettingInfo.h`, and the pink its indicator pass hard-codes. The
        # reference radius is PyMOL's `stick_radius`, which is what its width
        # rule scales -- kept separate here because chimol's stick radius is a
        # representation setting and this must not follow it.
        "selection": {
            "color": [1.0, 0.2, 0.6, 1.0],
            # Wider than PyMOL's 3-10 on purpose -- see migration 14 and
            # `renderer/markers.py`: a three-pixel marker cannot show three
            # bands, and resolves to one pink speck per atom.
            "width": 7.0,
            "width_max": 16.0,
            "width_scale": 2.0,
            "width_reference_radius": 0.25,
            "click_radius_px": 8.0,
        },
        "layout": {
            "root_margins": [4, 4, 4, 4],
            "root_spacing": 4,
            # How big the in-viewport chrome draws -- text and the rows around
            # it together. Below one by default: the chrome is read at a glance
            # and then looked past, and every pixel it takes is a pixel of the
            # molecule it covers.
            "ui_scale": 1.0,
            # Dragged windows snap to the viewport's sides and corners and
            # anchor there. Off means a window goes exactly where it is
            # dropped and follows no edge.
            "window_snap": True,
            # The chrome, piece by piece. All off leaves a bare 3-D viewer,
            # which is what an embedded or kiosk view wants.
            "show_menubar": True,
            "show_toolbar": True,
            "show_command_line": True,
            "show_status": True,
            # Developer instruments: the chrome-size slider and the frame-rate
            # readout, both bottom-right in the status band. Off by default
            # because a permanent slider and a permanent number in the corner
            # of a figure are chrome that only earns its space while somebody
            # is measuring.
            "debug": False,
        },
        # --- export ------------------------------------------------------ #
        "export": {
            # Drop particles that are buried inside the model before writing a
            # mesh. A mesoscale structure exported whole is mostly geometry
            # nobody can see: every bead becomes a tessellated sphere, and the
            # nuclear pore's 234,184 of them make a glTF too large to open.
            # The test is a neighbour count, not a visibility computation --
            # fast and approximate on purpose, since this is for a picture.
            "hollow": True,
            # How enclosed a particle must be to count as buried. Close packing
            # puts 12 spheres in contact, so well past that is surrounded.
            # Lower removes more and eats into the surface; higher keeps more.
            "hollow_min_neighbors": 18,
            # The neighbourhood, as a multiple of the median particle radius.
            "hollow_radius_scale": 2.5,
        },
        "sequence": {
            "residue_tick_step": 20,
            "selection_color": [1.0, 0.95, 0.4, 1.0],
            "selection_text_color": [0.1, 0.1, 0.1, 1.0],
            "number_step": 5,
            "font_family": "Courier New",
            "font_size": 9,
            "font_bold": True,
            "number_font_bold": True,
            "number_height": 16,
            "residue_height": 20,
            "number_color": [0.25, 0.25, 0.25, 1.0],
            "number_bg_color": [0.12, 0.12, 0.12, 1.0],
            "independent_scroll": False,
            # PyMOL-compatible sequence viewer globals
            "seq_view": True,
            "seq_view_gap_mode": 1,
            "seq_view_label_spacing": 5,
            "seq_view_format": 0,
            "seq_view_color": -1,
            "seq_view_fill_color": -1,
            "seq_view_label_color": [1.0, 1.0, 1.0, 1.0],
            "seq_view_overlay": False,
        },
        "backbone_trace": {
            "protein_atoms": ["CA"],
            "nucleic_atoms": ["P", "O5'", "C5'", "C4'", "C3'", "O3'", "C1'", "C1*"],
        },
        "occlusion": {
            # Per-vertex ambient occlusion baked into the mesh colours at build
            # time. Normal-aware, so crevices darken and convex surfaces stay
            # bright; costs nothing per frame and cannot shimmer as the camera
            # moves. PyMOL has no equivalent.
            "enabled": True,
            # Scales the accumulated coverage before the exponential; higher
            # deepens the shading without ever passing full occlusion.
            "strength": 1.4,
            # How far the darkest crevice is taken toward black.
            "darkness": 0.7,
            # Occluders further than this (in Angstrom) are ignored.
            "max_distance": 10.0,
            # "residues" occludes with the backbone trace, "atoms" with every
            # atom. A ribbon threads through its own side chains, so the
            # all-atom set buries a cartoon in shadow; it suits space-filling.
            "occluders": "residues",
            # Radius standing in for a whole residue, in Angstrom.
            "residue_radius": 3.2,
            # Cast shadows for the key light, baked per vertex. Ambient
            # occlusion says how enclosed a point is; this says whether anything
            # stands between it and the light. PyMOL casts shadows only when
            # raytracing, so this is the interactive view going further.
            "shadows": True,
            "shadow_darkness": 0.45,
            "shadow_softness": 1.6,
            "shadow_distance": 20.0,
            # 2.8 rather than 1.0 because the kernel stopped counting each
            # occluder two or three times; see the version-12 migration.
            "shadow_strength": 2.8,
            # Toward the light source; PyMOL's `light` default (-0.4, -0.4,
            # -1) is the direction it travels, so this is its negation.
            "shadow_direction": [0.4, 0.4, 1.0],
        },
        "compute": {
            # Where the scene-building kernels run. "auto" dispatches the
            # per-vertex ones to WGSL compute when an adapter exists and the
            # mesh is big enough to pay for the round trip, and falls back to
            # NumPy otherwise; "cpu" and "gpu" force one side, which is what a
            # parity test needs. The GPU works in f32 and the CPU route in f64,
            # so the two agree to about 1e-6 relative rather than to the bit.
            "backend": "auto",
        },
        "label": {
            # PyMOL draws labels in the foreground colour, white on black.
            "color": [1.0, 1.0, 1.0, 1.0],
            "size": 14.0,
        },
        "lighting": {
            "light_direction": [0.0, 0.0, 1.0],
            "ambient_strength": 0.45,
            "specular_strength": 0.25,
            "shininess": 40.0,
            "rim_strength": 0.18,
            "rim_power": 2.4,
        },
        "camera": {
            "near_clip": 0.03,
            "far_clip": 2000.0,
            "min_near_clip": 0.005,
            "max_near_clip": 5.0,
            "clip_wheel_scale": 0.85,
            # Vertical field of view in degrees. 20 is PyMOL's default, and
            # matching it is what makes a view tuple copied from PyMOL frame
            # the molecule the same way here.
            "field_of_view": 20.0,
            "orthoscopic": False,
            # Mouse interaction style: "pymol" rotates and pans the object in
            # the camera view (intuitive, follows the cursor); "chimol"
            # rotates and pans the camera/plane so the object moves opposite
            # to the cursor.
            "mouse_mode": "pymol",
            # Whether stepping a trajectory re-centres the camera on the frame
            # being shown. On for a molecule, where it keeps a structure that
            # wanders across the box in view; off for anything that grows or is
            # attached to something, where following the centroid slides the
            # scene under it. PyMOL has no equivalent -- it never re-centres.
            "recenter_on_frame": True,
        },
        # PyMOL's depth_cue/fog/fog_start, which are **global**: the viewport and
        # the ray tracer read the same three numbers, so they belong to neither.
        "depth_cue": {
            "enabled": True,
            # Fraction of the fitted depth range at which the cue begins.
            "start": 0.45,
            # PyMOL's `fog`: a density, where a value in (0, 1) pushes the far
            # plane of the cue beyond the scene and 1 or more clamps it to it.
            "intensity": 1.0,
        },
        "ray": {
            "ambient": 0.14,
            "diffuse": 0.45,
            "reflect_power": 1.0,
            # PyMOL's `direct` and `power` (SettingInfo.h 8 and 11): the
            # headlight term and its exponent. Without them the traced
            # image tops out at ambient + diffuse and comes out far
            # darker than the viewport.
            "direct": 0.45,
            "power": 1.0,
            "specular": 0.25,
            "shininess": 40.0,
            "direct_specular": 0.30,
            "direct_specular_power": 55.0,
            "legacy_lighting": 0.0,
            "antialias": 2,
            "shadow": True,
            "shadow_fudge": 0.001,
            "shadow_decay_factor": 0.2,
            "shadow_decay_range": 1.8,
            "gamma": 2.2,
            "color_blend": True,
            "color_blend_red": 0.17,
            "color_blend_green": 0.25,
            "color_blend_blue": 0.14,
            "light_directions": [
                [0.0, 0.0, 1.0],
                [0.5, 0.3, 1.0]
            ],
        },
        # NOTE: PyMOL's flat setting names (cartoon_loop_radius, ray_shadow,
        # field_of_view, ...) are not stored here. They are aliases onto the
        # nested entries above, defined once in settings.py, which is what the
        # set/get/unset commands resolve against.
    }

    # Prefer a JSON file in the global chisurf settings folder so the user
    # can override display options without touching the source tree. When
    # chisurf is not available (standalone Chimol), fall back to a JSON file
    # shipped next to this module.
    package_path = get_package_display_config_path()
    try:
        override_env = os.environ.get("CHIMOL_DISPLAY_CONFIG")
        if override_env:
            override_path = Path(override_env)
            if override_path.is_file():
                path = override_path
            else:
                path = package_path
        elif _cs_settings is not None:
            settings_dir = _cs_settings.get_path("settings")
            user_path = settings_dir / "chimol_display.json"
            if not user_path.is_file():
                legacy = settings_dir / "molview_display.json"
                if legacy.is_file():
                    path = legacy
                else:
                    legacy2 = settings_dir / "protview_display.json"
                    path = legacy2 if legacy2.is_file() else user_path
                # If no user or legacy file exists, copy the package default.
                if not path.is_file() and package_path.is_file():
                    settings_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(package_path, user_path)
                    path = user_path
                elif not path.is_file():
                    path = package_path
            else:
                path = user_path
        else:
            path = package_path
    except Exception:
        path = package_path

    try:
        with path.open("r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        return default

    # Track the user copy version for the update-prompt feature.
    global _DISPLAY_CONFIG_USER_VERSION
    _DISPLAY_CONFIG_USER_VERSION = cfg.get("_version", 0)

    # Strip meta keys that should not leak into the rendered config.
    cfg.pop("_version", None)
    cfg.pop(UPDATE_PROMPT_KEY, None)

    # Bring forward defaults that changed since this copy was written.
    migrated = apply_display_config_migrations(cfg, _DISPLAY_CONFIG_USER_VERSION)
    # Persisted only when the file being read *is* the user's copy -- never the
    # package's, which is read-only as far as a session is concerned and shared
    # by every install.
    if migrated and path != package_path:
        _write_user_display_config(path, cfg)

    # Shallow-merge user config with defaults to ensure all keys exist.
    for key, sub in default.items():
        if key == "_version":
            continue
        if isinstance(sub, dict):
            section = cfg.setdefault(key, {})
            for sk, sv in sub.items():
                section.setdefault(sk, sv)
        else:
            cfg.setdefault(key, sub)
    return cfg


_DISPLAY_CONFIG_USER_VERSION: int = 0
"""Version number read from the user's ``chimol_display.json``, or 0."""

_DISPLAY_CONFIG_PACKAGE_VERSION: int = DISPLAY_CONFIG_VERSION
"""Version number shipped with the package."""

_DISPLAY_CONFIG: dict = _load_display_config()


def reload_display_config() -> None:
    """Reload MolView display configuration JSON into the global cache.

    Existing :class:`MolView` widgets read from the module-level
    :data:`_DISPLAY_CONFIG` inside :meth:`MolView._update_view`, so they
    will pick up new parameters on the next redraw after this function is
    called.

    After reloading, all registered :data:`_update_listeners` are invoked so
    that open viewers recompute their representations.
    """

    _merge_in_place(_DISPLAY_CONFIG, _load_display_config())
    for listener in list(_update_listeners):
        try:
            listener()
        except Exception:
            pass


def _merge_in_place(target: dict, fresh: dict) -> None:
    """Make *target* hold *fresh*, without replacing the dict itself.

    Ten modules -- including the two that draw, `renderer.view` and
    `renderer.wgpu_view` -- hold this config by name (``from ..config import
    _DISPLAY_CONFIG``). Rebinding the module global, which is what this used to
    do, left every one of them pointing at the dict from *before* the reload:
    the settings were reloaded and the renderer went on drawing from the old
    ones, exactly contrary to what the docstring above promises. Saving in the
    Config editor appeared to do nothing.

    Sections are merged rather than swapped for the same reason one level down:
    anything holding ``_DISPLAY_CONFIG["metaball"]`` would otherwise keep the
    old section object.
    """
    for key in [k for k in target if k not in fresh]:
        del target[key]
    for key, value in fresh.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_in_place(current, value)
        else:
            target[key] = value
