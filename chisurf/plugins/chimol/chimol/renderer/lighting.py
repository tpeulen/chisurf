"""The light rig, resolved once for every backend.

Why this is its own module
--------------------------
The WebGPU backend shipped with its own dictionary of "the OpenGL backend's
defaults", written from reading the shader rather than from reading the config.
It was wrong in the way a transcribed constant always eventually is, and the
symptom was not "the lighting differs" -- it was *"the WGSL cartoon is markedly
darker than the baseline, but only against a white background"*. The rig had a
key light 25 degrees off-axis where the configured one points straight down the
camera, and a fill light at 0.45 where the configuration asks for none. Off-axis
key plus fill gives a strongly modelled ribbon with dark flanks; head-on key
gives a flat, evenly lit one. Against black both read as "dark" and the pair
looked fine; against white the difference is the whole image.

So the numbers live here, once, and both backends resolve them from the same
display config. A backend that wants a different look overrides the rig
explicitly -- which is a decision in the caller rather than a divergence nobody
can see.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = ["LightRig", "resolve_light_rig"]

#: ChimeraX's parameter names, as ``set_lighting`` and the presets use them,
#: mapped onto this rig's fields. Kept beside the rig so a preset stays a plain
#: dict and no call site needs a translation table.
CHIMERAX_NAMES: dict[str, str] = {
    "key_light_intensity": "key",
    "fill_light_intensity": "fill",
    "ambient_light_intensity": "ambient",
    "specular_strength": "specular",
    "shininess": "shininess",
    "rim_strength": "rim_strength",
    "rim_power": "rim_power",
}


@dataclass
class LightRig:
    """A two-light rig plus the surface terms every backend's shader reads.

    Attributes
    ----------
    light_dir, fill_dir : tuple of float
        Key and fill directions, in view space.
    key, fill, ambient, specular : float
        Intensities. ``ambient`` is a *mixing* weight, not an additive term: the
        diffuse contribution is scaled by ``1 - ambient``, so the total stays in
        range and a value above 1 would make a lit face darker than an unlit one.
    shininess : float
        Specular exponent, also the floor of the environment sun's exponent.
    rim_strength, rim_power : float
        The edge glow.
    """

    light_dir: tuple[float, float, float] = (0.0, 0.0, 1.0)
    fill_dir: tuple[float, float, float] = (-0.4, -0.3, 0.8)
    key: float = 1.0
    #: Zero by default, and deliberately so: chimol's configured look is a single
    #: head-on key light. A fill light is what turns an evenly lit ribbon into a
    #: modelled one, so inventing a non-zero default changes every render.
    fill: float = 0.35
    ambient: float = 0.62
    specular: float = 0.18
    shininess: float = 38.0
    rim_strength: float = 0.18
    rim_power: float = 2.4

    def replace(self, **values) -> "LightRig":
        """Return a copy with ``values`` applied, under this class's own names."""
        unknown = set(values) - set(self.__dataclass_fields__)
        if unknown:
            raise ValueError(
                f"unknown lighting parameter(s): {', '.join(sorted(unknown))}"
            )
        return LightRig(**{**self.__dict__, **values})


def _direction(value, fallback: Sequence[float]) -> tuple[float, float, float]:
    """Read a three-vector from config, falling back when it is absent or short."""
    try:
        x, y, z = (float(v) for v in list(value)[:3])
    except (TypeError, ValueError):
        return tuple(float(v) for v in fallback)  # type: ignore[return-value]
    return (x, y, z)


def resolve_light_rig(config: Optional[dict] = None) -> LightRig:
    """Build the rig from the ``lighting`` display-config section.

    Parameters
    ----------
    config : dict, optional
        The ``lighting`` section. ``None`` reads the live display config, which
        is what a renderer wants; passing a dict is how a test pins the rig.

    Returns
    -------
    LightRig
    """
    if config is None:
        from ..config import _DISPLAY_CONFIG

        config = _DISPLAY_CONFIG.get("lighting") or {}

    base = LightRig()
    return LightRig(
        light_dir=_direction(config.get("light_direction"), base.light_dir),
        fill_dir=_direction(config.get("fill_light_direction"), base.fill_dir),
        key=float(config.get("key_light_intensity", base.key)),
        fill=float(config.get("fill_light_intensity", base.fill)),
        # `ambient_strength` in the config file, `ambient_light_intensity` in
        # ChimeraX's vocabulary. Both are accepted rather than one being
        # renamed: the file name is what users' saved configs contain.
        ambient=float(
            config.get(
                "ambient_strength",
                config.get("ambient_light_intensity", base.ambient),
            )
        ),
        specular=float(config.get("specular_strength", base.specular)),
        shininess=float(config.get("shininess", base.shininess)),
        rim_strength=float(config.get("rim_strength", base.rim_strength)),
        rim_power=float(config.get("rim_power", base.rim_power)),
    )
