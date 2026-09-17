"""Every console colour must be legible on its own background.

A console is unusable at low contrast in a way that no functional test notices
and that a screenshot only *sometimes* reveals -- a colour can look plausible in
a thumbnail and be unreadable at the editor's 9 pt. So the check is numeric.

This is not hypothetical for this codebase. Measuring the first draft of these
themes found the continuation prompt at **2.42:1** in all three, and the dark
theme printing the exception message itself -- the one line of a traceback
anybody reads -- at **3.24:1**. A sibling ChiSurf widget had previously shipped
a 1.09:1 pairing.
"""

from __future__ import annotations

import pytest

from chisurf.gui.chinsole.theme import THEMES, ConsoleTheme

#: WCAG 2.1 AA for normal-size text.
MINIMUM_RATIO = 4.5


def _relative_luminance(colour: str) -> float:
    """Return the WCAG relative luminance of *colour*.

    Parameters
    ----------
    colour : str
        ``#rrggbb``.

    Returns
    -------
    float
    """
    value = colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours.

    Parameters
    ----------
    foreground, background : str
        ``#rrggbb``.

    Returns
    -------
    float
        Between 1.0 and 21.0.
    """
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _foreground_colours(theme: ConsoleTheme) -> dict[str, str]:
    """Return every colour drawn as text on the theme's background.

    Parameters
    ----------
    theme : ConsoleTheme

    Returns
    -------
    dict
        Label to colour.
    """
    colours = {
        "foreground": theme.foreground,
        "prompt_in": theme.prompt_in,
        "prompt_out": theme.prompt_out,
        "prompt_continuation": theme.prompt_continuation,
        "stderr_fg": theme.stderr_fg,
        "traceback_fg": theme.traceback_fg,
    }
    for index, colour in enumerate(theme.ansi):
        # Slots 0 and 8 are the palette's black and bright-black. On a dark
        # background they are near-invisible by construction, and that is
        # correct: a program emitting \x1b[30m has asked for black, usually
        # paired with a background colour it also set. Remapping them to
        # something legible would corrupt exactly those pairings, and no real
        # terminal does it either.
        if index in (0, 8):
            continue
        colours[f"ansi[{index}]"] = colour
    for token, colour in theme.syntax.items():
        colours[f"syntax[{token}]"] = colour
    return colours


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_theme_contrast(theme_name):
    """No colour in a theme falls below the AA threshold on its background."""
    theme = THEMES[theme_name]
    failures = []
    for label, colour in _foreground_colours(theme).items():
        ratio = contrast_ratio(colour, theme.background)
        if ratio < MINIMUM_RATIO:
            failures.append(f"{label} {colour} on {theme.background}: {ratio:.2f}:1")
    assert not failures, (
        f"{theme_name} has unreadable colours (need {MINIMUM_RATIO}:1): " + "; ".join(failures)
    )


def test_contrast_ratio_is_not_vacuous():
    """The measurement itself must distinguish good from bad.

    A contrast test that returns a large number for everything passes forever
    and protects nothing.
    """
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)
    # The value the first draft of the dark theme actually shipped with.
    assert contrast_ratio("#5a5a5a", "#1e1e1e") < MINIMUM_RATIO


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_selection_is_legible(theme_name):
    """Selected text must be readable against the selection highlight."""
    theme = THEMES[theme_name]
    ratio = contrast_ratio(theme.selection_fg, theme.selection_bg)
    assert ratio >= 3.0, f"{theme_name}: selected text at {ratio:.2f}:1 on the selection colour"


def test_legacy_style_names_still_resolve():
    """An existing user's ``console_style`` keeps working.

    ChiSurf merges packaged defaults underneath the user's settings file and
    never overwrites it, so ``console_style: linux`` -- qtconsole's spelling --
    is on every installation permanently.
    """
    from chisurf.gui.chinsole.theme import resolve_theme

    assert resolve_theme("linux").name == "chisurf-dark"
    assert resolve_theme("lightbg").name == "chisurf-light"
    assert resolve_theme("nocolor").name == "chisurf-mono"


def test_unknown_theme_falls_back_rather_than_raising():
    """A typo in a hand-edited settings file must not stop the console."""
    from chisurf.gui.chinsole.theme import resolve_theme

    assert resolve_theme("no-such-theme") in THEMES.values()
