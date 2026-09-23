#!/usr/bin/env python
"""Write the Literature page from the bibliography.

``docs/references/bibliography.yaml`` is the source of truth for every work the
documentation cites; this generates the page a reader browses
(``docs/references/index.md``), grouped by topic, with each entry linking to
somewhere the paper can be obtained.

Usage::

    python build_tools/docs/make_bibliography.py [--check]

``--check`` regenerates in memory and fails if the file on disk differs, which
is what a build should run.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from build_tools.docs import okf  # noqa: E402
from chisurf.plugins.core.help.api import bibliography as bib  # noqa: E402

#: Topic key -> the heading it appears under, in reading order. A topic missing
#: here still appears, under "Other", so adding one to the YAML cannot lose it.
TOPIC_TITLES = [
    ("fret", "FRET: mechanism, accuracy and corrections"),
    ("smfret", "Single-molecule FRET"),
    ("mfd", "Multiparameter fluorescence detection"),
    ("pda", "Photon distribution analysis"),
    ("dynamics", "Dynamics and kinetics"),
    ("hmm", "Hidden Markov models"),
    ("fcs", "Fluorescence correlation spectroscopy"),
    ("filtered-fcs", "Filtered and lifetime-resolved FCS"),
    ("imaging", "Image correlation and scanning microscopy"),
    ("resolution", "Image resolution"),
    ("tracking", "Particle tracking"),
    ("segmentation", "Image segmentation and region measurement"),
    ("colocalisation", "Colocalisation"),
    ("structure", "Structure, surfaces and polymers"),
    ("polymer", "Polymer models"),
    ("tcspc", "Time-resolved fluorescence"),
    ("anisotropy", "Anisotropy"),
    ("saturation", "Optical saturation and focal volumes"),
    ("photophysics", "Photophysics"),
    ("optics", "Optics and point-spread functions"),
    ("flim", "Fluorescence-lifetime imaging"),
    ("mle", "Maximum-likelihood estimation"),
    ("statistics", "Statistics, sampling and convergence"),
    ("exploration", "Dimensionality reduction and clustering"),
    ("formats", "Data formats and standards"),
    ("data", "Data, provenance and vocabularies"),
]

#: The OKF header the generated page carries. Emitted here rather than
#: injected afterwards, which the next regeneration would undo.
FRONT_MATTER = okf.render_front_matter(
    {
        "type": "Bibliography",
        "title": "Literature",
        "description": "Every work the ChiSurf documentation cites, each linking through to "
        "the publisher's page.",
        "resource": "docs/references/bibliography.yaml",
        "tags": ["references", "literature", "citations", "bibliography"],
        "anchor": "literature",
        "generator": "build_tools/docs/make_bibliography.py",
    }
)

HEADER = FRONT_MATTER + """
(literature)=
# Literature

Every work the ChiSurf documentation cites, in one place. **Each entry links to
the paper** — to its DOI where one is recorded, and otherwise to a literature
search for its title, so there is always a way through to the publisher's page
and the download.

Pages cite a work by its **key** — the name each entry is anchored under below —
and the citation renders as a link to the paper. The source of truth is
[`bibliography.yaml`](bibliography.yaml) — add a work there and it appears here.

*{count} works.*
"""


def render() -> str:
    """Return the Literature page as Markdown."""
    entries = bib.bibliography(refresh=True)
    lines = [HEADER.format(count=len(entries))]

    seen: set[str] = set()
    for topic, title in TOPIC_TITLES:
        group = [
            entry
            for entry in entries.values()
            if topic in entry.topics and entry.key not in seen
        ]
        if not group:
            continue
        lines.append(f"\n## {title}\n")
        for entry in sorted(group, key=lambda e: (e.first_author.lower(), e.year)):
            seen.add(entry.key)
            lines.append(_entry_markdown(entry))

    rest = [entry for entry in entries.values() if entry.key not in seen]
    if rest:
        lines.append("\n## Other\n")
        for entry in sorted(rest, key=lambda e: (e.first_author.lower(), e.year)):
            lines.append(_entry_markdown(entry))

    lines.append(
        "\n---\n\nA work with no DOI recorded links to a literature search "
        "rather than to a guessed identifier: sending a reader to the wrong "
        "paper is worse than sending them to a search.\n"
    )
    return "\n".join(lines)


def _entry_markdown(entry) -> str:
    """One entry: an anchor, the citation, the reference and the note."""
    url = bib.entry_url(entry)
    reference = bib.format_entry(entry)
    note = f"  \n*{entry.note.rstrip('.')}.*" if entry.note else ""
    # The anchor is its own block: a MyST target immediately above a list item
    # is consumed into the item's text, and the bullet then renders as a
    # literal "-" at the start of the line.
    return (
        f"({entry.key})=\n\n"
        f"**[{bib.short_citation(entry)}]({url})** — {reference}{note}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the page on disk is not what the bibliography implies",
    )
    args = parser.parse_args()

    target = REPO_ROOT / "docs" / "references" / "index.md"
    content = render()
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != content:
            print(f"{target} is stale — run build_tools/docs/make_bibliography.py")
            return 1
        print(f"{target} is up to date")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"wrote {target} ({len(bib.bibliography())} works)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
