"""The task colour key of the emtk shell: one category, one colour, readable, on every tool.

``chisurf/emtk/task_colors.yaml`` declares the colours; these tests hold the file to its
promises (both themes, WCAG contrast, every shipped plugin placed) and check that the shell
really draws a hosted tool's dock tab in its category's colour.
"""

from __future__ import annotations

import time

import pytest
from emtk import im
from emtk import style as st
from emtk.accents import header_colours, neutral_tab, region_colours, resolve
from emtk.app import ImApp
from emtk.im_core import Col, Style
from emtk.testing import Driver

from chisurf.emtk import task_colors as tc
from chisurf.emtk.main_app import EmtkShellApp, menu_entries


def _style(dark: bool) -> Style:
    """The toolkit's dark style, or its light one (``style_colors_light``)."""
    style = Style()
    if not dark:
        im.style_colors_light(style)
    return style


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


def test_the_palette_loads_with_both_themes_and_the_owners_anchors():
    cats = tc.categories()
    assert len(cats) >= 10
    for name in cats:
        themed = tc.accent(name)
        assert themed.dark is not None and themed.light is not None
    # The owner's anchors: documentation blue, wizards orange, imaging green.
    doc, wiz, img = (tc.accent(n).dark.fill for n in ("documentation", "wizards", "imaging"))
    assert doc[2] > doc[0] and doc[2] > doc[1]
    assert wiz[0] > wiz[1] > wiz[2]
    assert img[1] > img[0] and img[1] > img[2]
    # Hues differ in lightness too (colour-vision deficiencies): the fills span a range.
    lum = sorted(st.relative_luminance(tc.accent(n).dark.fill) for n in cats)
    assert lum[-1] - lum[0] > 0.08


def test_every_shipped_plugin_resolves_to_a_task_colour():
    from chisurf.emtk.plugins import manifests

    entries = menu_entries(manifests())
    known = tc.plugin_categories(entries)
    missing = sorted(e.plugin_id for e in entries if not known.get(e.plugin_id))
    assert not missing, (
        f"plugins without a task colour (add their group to task_colors.yaml): {missing}"
    )
    assert known["help"] == "documentation"
    assert known["wizards"] == "wizards"
    assert known["imaging_tools"] == "imaging"
    assert known["hmm"] == "kinetics" and known["lltf"] == "decay"


def test_the_shells_own_docks_have_their_category():
    assert tc.dock_category("fit.analysis", {}) == "fitting"
    assert tc.dock_category("data.read", {}) == "fitting"
    assert tc.dock_category("fit.3", {}) == "fitting"
    assert tc.dock_category("console", {}) == "console"
    assert tc.dock_category("log", {}) == "console"
    assert tc.dock_category("tools", {}) is None
    assert tc.dock_category("plugin.wizards", {"wizards": "wizards"}) == "wizards"


@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
def test_text_on_every_task_colour_reads_at_4_5_to_1(dark):
    style = _style(dark)
    background = style.color(Col.WINDOW_BG)
    text = style.color(Col.TEXT)
    ground = neutral_tab(style)

    def seen(colour):
        return st.lerp_colour(background, colour, colour[3] / 255.0) if colour[3] < 255 else colour

    for name in [*tc.categories(), "neutral"]:
        themed = tc.accent(name) if name != "neutral" else tc.neutral()
        accent = resolve(themed, style)
        assert accent is (themed.dark if dark else themed.light)
        assert st.contrast_ratio(accent.fill, accent.text) >= 4.5, (name, "active tab")
        assert st.contrast_ratio(accent.foreground, background) >= 4.5, (name, "caption")
        for share in (accent.muted, accent.muted * 1.5):  # inactive, hovered
            muted = accent.mute(ground, share)
            assert st.contrast_ratio(muted, accent.muted_text(muted, text)) >= 4.5, (name, share)
        # Headers, tabs and title bars inside the dock: 4.5, or no worse than the theme's own.
        for role, colour in region_colours(style, themed).items():
            own = st.contrast_ratio(seen(st.parse_colour(style.color(role))), text)
            assert st.contrast_ratio(seen(colour), text) >= min(4.5, own) - 1e-6, (name, role)
        assert set(header_colours(style, themed)) <= set(region_colours(style, themed))


class _Tool(ImApp):
    def __init__(self):
        super().__init__(lambda: None)


def test_a_hosted_dock_tab_is_drawn_in_its_category_colour():
    shell = EmtkShellApp(
        loader=lambda _pid: _Tool(), console_history=False, console_session_file=False
    )
    driver = Driver(shell, (1200, 800))
    driver.frame(2)
    for plugin_id in ("help", "wizards"):
        hosted = shell.open_plugin(plugin_id)
        end = time.monotonic() + 30
        while hosted.build is not None:
            assert time.monotonic() < end
            driver.frame(1)
            time.sleep(0.01)
    driver.frame(2)
    painter = driver.frame()
    wizards, docs = tc.accent("wizards").dark, tc.accent("documentation").dark
    # Wizards opened last: its tab is on top in its fill and text, Documentation's muted with a line of blue.
    assert shell.docks.window("plugin.wizards").accent == tc.accent("wizards")
    tab = shell.docks.tab_rect("plugin.wizards")
    fills = [tuple(c)[:3] for x, y, w, h, c in painter.fills if (x, w) == (tab[0], tab[2])]
    assert wizards.fill[:3] in fills
    title = [c for *_b, s, c, _bold in painter.texts if s == "Wizards"]
    assert any(tuple(c)[:3] == wizards.text[:3] for c in title)
    assert docs.fill[:3] in {tuple(c)[:3] for *_b, c in painter.fills}
    # The ribbon's Help group (Documentation) writes its caption in the blue ink.
    shell.ribbon.ribbon.current = "Main"
    painter = driver.frame()
    help_captions = [c for *_b, s, c, _bold in painter.texts if s == "Help"]
    assert any(tuple(c)[:3] == docs.foreground[:3] for c in help_captions)
    shell.close()
