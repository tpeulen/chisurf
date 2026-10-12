"""Names for fits that stay distinguishable when two fits are called alike."""

from __future__ import annotations


def unique_labels(entries: list[tuple[str, str]]) -> list[str]:
    """One label per ``(name, dataset_name)`` entry, in order, all different.

    Two wizard runs name their fits alike ("Lifetime - Anisotropy VV"). A name used more than once
    gets its dataset appended, and a running number when even that repeats. Names used once are
    left as they are.
    """
    counts: dict[str, int] = {}
    for name, _data in entries:
        counts[name] = counts.get(name, 0) + 1
    labels = []
    for name, data in entries:
        if counts[name] > 1 and data and data != name:
            name = f"{name} ({data})"
        labels.append(name)
    totals: dict[str, int] = {}
    for label in labels:
        totals[label] = totals.get(label, 0) + 1
    seen: dict[str, int] = {}
    out = []
    for label in labels:
        if totals[label] > 1:
            seen[label] = seen.get(label, 0) + 1
            label = f"{label} #{seen[label]}"
        out.append(label)
    return out
