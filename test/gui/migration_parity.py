"""Qt-free helpers for judging a GUI migration on control inventory, not pixels.

An AutoForm/emtk port deliberately changes layout (a parameter table replaces stacked
labelled rows -- that is the point), so a pixel-similarity threshold is either always
red or so loose it proves nothing. The comparable content is the set of normalised
control texts: :func:`_normalize_control_text` reduces one label to its comparable form,
:func:`compare_inventories` diffs two inventories. The Qt capture half (rendering a
legacy widget) went with the Qt widgets; the frozen ``*_qt_inventory.json`` records are
what is compared against now.

See the migration rule in ``okf/workflows/testing.md``.
"""

from __future__ import annotations

#: Decoration stripped before comparing control text, so a control that merely
#: changed its rendering is not reported as lost. Includes the rich-text markup
#: legacy widgets used for subscripts (``t<sub>Bg</sub>`` and ``tBg`` are the same
#: control) and the disclosure glyphs AutoForm puts on panel headers.
_STRIP_PREFIXES = ("▶", "▼", "▸", "▾")


def _normalize_control_text(text: str) -> str:
    """Reduce control text to what is comparable across a migration.

    Parameters
    ----------
    text : str
        Raw label or button text.

    Returns
    -------
    str
        Lower-cased text with rich-text tags stripped, HTML entities decoded,
        disclosure glyphs, surrounding punctuation and internal whitespace
        removed.
    """
    import html
    import re

    # Entities are decoded, not just tags stripped: these labels are full of
    # them (``&tau;``, ``&kappa;``, ``&rarr;``), and comparing an escaped label
    # against a rendered one reports every Greek-lettered parameter as lost.
    out = html.unescape(re.sub(r"<[^>]+>", "", text))
    for glyph in _STRIP_PREFIXES:
        out = out.replace(glyph, "")
    out = out.strip().strip(":").strip()
    return re.sub(r"\s+", "", out).lower()


def compare_inventories(before: dict, after: dict) -> dict:
    """Diff two :func:`control_inventory` results.

    Parameters
    ----------
    before, after : dict
        Inventories of the legacy widget and its replacement.

    Returns
    -------
    dict
        ``lost`` is the blocker -- normalized controls present before and absent
        after. ``gained`` are additions, which are fine. ``counts`` pairs each
        numeric field as ``(before, after)`` to show how the layout changed.
    """
    return {
        "lost": sorted(set(before["controls"]) - set(after["controls"])),
        "gained": sorted(set(after["controls"]) - set(before["controls"])),
        "counts": {
            k: (before[k], after[k]) for k in ("line_edits", "combos", "spin_boxes", "tables")
        },
    }
