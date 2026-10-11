"""A layout measures the text it draws: never the English source of a translated caption.

``im.button(tr("Next"))`` draws "Suivant" in a French session; a right-aligned bar that made room
with ``im.calc_text_size("Next")`` leaves "Suivant" clipped at the window edge. Found by the
real-use language matrix (okf/workflows/testing.md, "Real-use QA matrix") in the anisotropy
wizard's Back / Next bar; the same pattern sat in four more tools.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "chisurf"
#: ``calc_text_size("Word ...")``: an English literal measured as is (a single glyph such as
#: "X" or "M" is a size probe, not a caption, and is allowed).
PATTERN = re.compile(r"""calc_text_size\(\s*["']([A-Z][^"']+)["']""")


def test_no_layout_measures_an_untranslated_caption():
    found = []
    for path in ROOT.rglob("*.py"):
        if "test" in path.parts or "tests" in path.parts:
            continue
        for number, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
            for match in PATTERN.finditer(line):
                if len(match.group(1)) > 1:
                    found.append(f"{path.relative_to(ROOT.parent)}:{number}: {match.group(0)}")
    assert not found, "measure tr(caption), the text that is drawn:\n  " + "\n  ".join(found)
