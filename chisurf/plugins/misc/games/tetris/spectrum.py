"""The original chigame spectral colour mapping, without its GUI imports."""


def wavelength_to_srgb(nanometres: float) -> tuple[float, float, float]:
    """Convert a visible wavelength to an approximate sRGB colour.

    This is the art direction of the default pack: a fluorophore is drawn in the
    colour it actually emits, so the palette is data rather than taste and the
    picture teaches spectra. Wavelengths outside the visible range clamp to the
    nearest visible end rather than fading to black, because an invisible
    creature is a bug, not a feature.

    Parameters
    ----------
    nanometres : float
        Wavelength in nm.

    Returns
    -------
    tuple of float
        sRGB components in 0..1.
    """
    w = float(min(max(nanometres, 380.0), 780.0))
    if w < 440.0:
        r, g, b = -(w - 440.0) / 60.0, 0.0, 1.0
    elif w < 490.0:
        r, g, b = 0.0, (w - 440.0) / 50.0, 1.0
    elif w < 510.0:
        r, g, b = 0.0, 1.0, -(w - 510.0) / 20.0
    elif w < 580.0:
        r, g, b = (w - 510.0) / 70.0, 1.0, 0.0
    elif w < 645.0:
        r, g, b = 1.0, -(w - 645.0) / 65.0, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0

    # Roll off at the ends of vision, but never all the way to black.
    #
    # The red rolloff starts at 645 rather than 700 deliberately. Above 645 the
    # hue is pure red and stops changing, so without a brightness gradient every
    # wavelength from there to 780 renders *identically* -- which showed up as
    # two adjacent spectral bands that were supposed to differ looking the same.
    # Eye sensitivity really does fall away across that span, so dimming it is
    # both the fix and the more faithful answer. It starts at 620 rather than
    # 645 because two bands only ~40 nm apart still have to be told apart.
    if w < 420.0:
        falloff = 0.3 + 0.7 * (w - 380.0) / 40.0
    elif w > 620.0:
        falloff = 0.28 + 0.72 * (780.0 - w) / 160.0
    else:
        falloff = 1.0
    return r * falloff, g * falloff, b * falloff
