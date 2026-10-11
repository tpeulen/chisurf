"""A tour's "Press <b>…</b>" names the caption the button really shows.

Three imaging tours told the reader to press **Load demo** or **Demo** while the button reads *Load example*
(``action_caption("example")``); a reader looking for the named button does not find it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from chisurf.plugins.emtk_layout import action_caption

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOURS = [
    "chisurf/plugins/microscopy/region_mle/gui/guide.json",
    "chisurf/plugins/microscopy/img_flow/gui/guide.json",
    "chisurf/plugins/microscopy/img_pixel_nb/gui/guide.json",
]


@pytest.mark.parametrize("tour", TOURS)
def test_the_example_step_names_the_load_example_button(tour):
    caption = action_caption("example").split(None, 1)[-1].strip()  # without the icon
    hints = [
        (step.get("await") or {}).get("hint", "")
        for step in json.loads((ROOT / tour).read_text(encoding="utf-8"))["steps"]
    ]
    pressed = {m for hint in hints for m in re.findall(r"Press <b>([^<]+)</b>", hint)}
    assert caption in pressed, (caption, pressed)
    assert not pressed & {"Load demo", "Demo"}, pressed
