"""The ebFRET tour names each button it waits on by the caption the button draws.

The tour told the user to press **Load demo** at a button that reads *Load example*
(guide 20 repeated it), the same slip the ALEX Suite tour had.
"""

from __future__ import annotations

import json
import pathlib
import re

GUI = pathlib.Path(__file__).resolve().parents[1] / "gui"


def _buttons():
    out = {}
    for spec in GUI.glob("*.view.json"):
        text = spec.read_text(encoding="utf-8")
        for match in re.finditer(r'"action":\s*"(\w+)",\s*"label":\s*"([^"]+)"', text):
            out[match.group(1)] = match.group(2)
    return out


def test_await_hints_name_the_button_by_its_caption():
    buttons = _buttons()
    assert "load_example" in buttons
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    checked = 0
    for step in steps:
        name = (step.get("target") or {}).get("name")
        if name in buttons and "await" in step:
            named = re.findall(
                r"<b>([^<]+)</b>", step["await"].get("hint", "") + step.get("text", "")
            )
            assert buttons[name] in named, (name, buttons[name], named)
            checked += 1
    assert checked
