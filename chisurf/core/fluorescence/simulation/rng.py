"""One seed in, the engine's two seeds out.

The simulator draws from two independent streams — where molecules go, and when
they emit — so that changing one leaves the other alone. That is the right design
and it is why the engine takes ``seed_diffusion`` and ``seed_emission`` rather
than one seed.

It is not, however, what a caller wants to pass. ChiSurf's simulators each solved
that differently: some took a single ``seed`` and hard-coded the pair, some
exposed both, some buried one in a settings dictionary. A reader could not tell
whether two call sites with ``seed=11`` were running the same simulation.

They are now, because the derivation is here.
"""

from __future__ import annotations

__all__ = ["seeds"]

#: Offsets applied to a caller's seed. Arbitrary, and fixed forever: changing them
#: changes every simulated measurement in the tree, including the ones that
#: regression numbers were derived from.
_DIFFUSION_OFFSET = 0x9E3779B1
_EMISSION_OFFSET = 0x85EBCA77


def seeds(seed: int) -> dict[str, int]:
    """Return the engine's two seeds, derived from one.

    The two streams must not be equal and must not be correlated in an obvious
    way, so the caller's seed is offset by two different constants rather than
    used as-is for one and incremented for the other.

    Parameters
    ----------
    seed : int
        The caller's seed. The same value always gives the same simulation.

    Returns
    -------
    dict
        ``{"seed_diffusion": ..., "seed_emission": ...}``, ready to merge into a
        ``settings`` block.
    """
    value = int(seed) & 0xFFFFFFFF
    return {
        "seed_diffusion": (value + _DIFFUSION_OFFSET) & 0xFFFFFFFF,
        "seed_emission": (value + _EMISSION_OFFSET) & 0xFFFFFFFF,
    }
