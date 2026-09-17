"""How much of the reference implementations has been mined, and what is left.

ChiMOL is built by **reading PyMOL's source and transcribing it** -- the working
rule that has paid off every time it was followed, and that produced a wrong
answer every time it was not. That raises a question nothing in the tree could
answer: *which parts have already been read?* Without it, the same file gets
re-read by the next session, and "is the source exhausted?" has no answer at
all.

The answer is a marker left **in the reference file itself**, so it is found by
whoever opens it rather than by whoever thinks to search the knowledge base:

    /* CHISURF-REVIEWED: 2026-08-06
     * CHISURF-TAKEN: cSetting_stick_color -> renderer/view.py::_representation_color
     * CHISURF-SKIPPED: RepValence -- ChiSurf has no bond orders
     * CHISURF-RECORD: okf/plugins/pymol-parity.md
     */

Editing the reference checkouts for this is **sanctioned** -- see the OKF
concept -- and is restricted to that header: never the code, so a `git diff`
inside the checkout stays readable and the file keeps saying what PyMOL does.

``junk/`` is gitignored and re-clonable, so these markers are a *convenience
index*, not the record. The record is the OKF concept, which is why every marker
points at it. A re-clone loses the markers and loses nothing else; this script
then reports the coverage as zero, which is the honest reading of "nobody has
looked at this checkout".

Run it against any checkout::

    python -m build_tools.dev_utils.reference_coverage junk/FRETBursts
    python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source --preset pymol
    python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source --unreviewed layer2
    python -m build_tools.dev_utils.reference_coverage --all

With no preset the whole checkout is surveyed, minus the noise every repository
carries (tests, examples, build directories, vendored dependencies). A preset
narrows it to the directories that are actually worth reading, which is what
makes the percentage mean something: PyMOL is ~3000 files and most of them are
build glue, so counting those would hold coverage near zero for ever and tell
nobody anything.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys

#: Where the interesting code is. PyMOL is ~3000 files and most of them --
#: build glue, bundled dependencies, the OpenVR bridge -- have nothing ChiSurf
#: would take, so counting them would put coverage permanently near zero and
#: tell no one anything. These are the directories the parity work actually
#: reads, and the denominator is over *them*.
PYMOL_SOURCE_DIRS: tuple[str, ...] = (
    "layer0", "layer1", "layer2", "layer3", "layer4", "layer5",
    "modules/pymol",
    # The Qt front end, because PyMOL is the authority on the *GUI and UX*.
    # `pmg_tk` is the retired Tk one and is deliberately absent.
    "modules/pmg_qt",
)

#: The same for ChimeraX, which is the authority on **functionality** -- what a
#: viewer should be able to do -- where PyMOL is the authority on the GUI and
#: the UX. `std_commands` is therefore the interesting directory: it is the
#: capability surface, one module per command.
CHIMERAX_SOURCE_DIRS: tuple[str, ...] = (
    "src/bundles/graphics/src",
    "src/bundles/std_commands/src",
    "src/bundles/atomic/src",
)

#: Narrowings worth naming. Any other checkout is surveyed whole.
PRESETS: dict[str, tuple[str, ...]] = {
    "pymol": PYMOL_SOURCE_DIRS,
    "chimerax": CHIMERAX_SOURCE_DIRS,
}

#: Directory names skipped when a checkout is surveyed whole: nobody mines a
#: reference implementation's test suite or its vendored dependencies, and
#: counting them makes the coverage figure meaningless.
SKIP_DIRECTORIES = frozenset({
    ".git", "build", "dist", "test", "tests", "testing", "examples", "example",
    "doc", "docs", "third_party", "external", "vendor", "contrib",
    "__pycache__", "node_modules", ".tox", ".venv",
})

_MARKER = re.compile(
    r"CHISURF-REVIEWED:\s*(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})", re.IGNORECASE
)
#: The triage pass: *looked at*, not read line by line. Kept apart from
#: `REVIEWED` on purpose -- a survey that inflated the coverage figure would
#: make the one number this script exists to produce a lie.
_SURVEYED = re.compile(
    r"CHISURF-SURVEYED:\s*(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})", re.IGNORECASE
)
#: What a surveyed file is *worth*, so a later pass can start at the top:
#: ``CHISURF-VALUE: A ux,gui -- the whole mouse-mode matrix lives here``.
_VALUE = re.compile(
    r"CHISURF-VALUE:\s*(?P<rank>[A-Da-d])\s+(?P<facets>[a-z, ]*?)\s*--\s*(?P<text>.+)"
)
_TAKEN = re.compile(r"CHISURF-TAKEN:\s*(?P<text>.+)")
_SKIPPED = re.compile(r"CHISURF-SKIPPED:\s*(?P<text>.+)")
#: ``.m``: MATLAB references (ebFRET, PAM, MASH-FRET) are read and annotated like
#: any other, and without it their headers never reached the coverage figure.
_SUFFIXES = {".cpp", ".c", ".h", ".py", ".txt", ".m"}

#: What the ranks mean. A file is ranked for *ChiSurf*, not in the abstract:
#: the question is always "what would reading this buy the viewer".
RANKS: dict[str, str] = {
    "A": "read next -- a behaviour chimol needs and does not have",
    "B": "worth reading when that area comes up",
    "C": "reference only -- consult for a detail, do not transcribe",
    "D": "nothing here for chimol",
}


@dataclasses.dataclass
class FileReview:
    """What one reference file's marker says."""

    path: pathlib.Path
    date: str | None = None
    surveyed: str | None = None
    rank: str = ""
    facets: tuple[str, ...] = ()
    value: str = ""
    taken: list[str] = dataclasses.field(default_factory=list)
    skipped: list[str] = dataclasses.field(default_factory=list)

    @property
    def reviewed(self) -> bool:
        return self.date is not None

    @property
    def touched(self) -> bool:
        """Whether anyone has looked at this file at all, at either depth."""
        return self.reviewed or self.surveyed is not None


def read_marker(path: pathlib.Path) -> FileReview:
    """Read a file's marker, looking only at its first lines.

    Only the head is read: a marker belongs in the header, and scanning whole
    files across a 132 MB checkout to find one that is not there is the
    difference between a second and a minute.
    """
    review = FileReview(path=path)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = "".join(next(handle, "") for _ in range(40))
    except OSError:
        return review
    match = _MARKER.search(head)
    surveyed = _SURVEYED.search(head)
    value = _VALUE.search(head)
    if match is None and surveyed is None:
        return review
    if match is not None:
        review.date = match.group("date")
    if surveyed is not None:
        review.surveyed = surveyed.group("date")
    if value is not None:
        review.rank = value.group("rank").upper()
        review.facets = tuple(
            f.strip() for f in value.group("facets").split(",") if f.strip()
        )
        review.value = value.group("text").strip()
    review.taken = [m.group("text").strip() for m in _TAKEN.finditer(head)]
    review.skipped = [m.group("text").strip() for m in _SKIPPED.finditer(head)]
    return review


def survey(
    root: pathlib.Path, directories: tuple[str, ...] | None = None
) -> list[FileReview]:
    """Every source file worth mining, with whatever marker it carries.

    Parameters
    ----------
    root : pathlib.Path
        The checkout.
    directories : tuple of str, optional
        Narrow to these subdirectories. ``None`` surveys the whole checkout
        minus :data:`SKIP_DIRECTORIES`.
    """
    reviews: list[FileReview] = []
    bases = [root / d for d in directories] if directories else [root]
    for base in bases:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in _SUFFIXES or not path.is_file():
                continue
            if SKIP_DIRECTORIES.intersection(path.relative_to(root).parts[:-1]):
                continue
            reviews.append(read_marker(path))
    return reviews


def report(reviews: list[FileReview], root: pathlib.Path) -> str:
    """A per-directory coverage table, and what has been taken from where."""
    by_directory: dict[str, list[FileReview]] = {}
    for review in reviews:
        key = str(review.path.parent.relative_to(root))
        by_directory.setdefault(key, []).append(review)

    header = (
        f"{'directory':34} {'reviewed':>9} {'surveyed':>9} {'files':>7}  {'coverage':>8}"
    )
    lines = [header]
    total_reviewed = 0
    total_surveyed = 0
    for directory in sorted(by_directory):
        group = by_directory[directory]
        done = sum(1 for r in group if r.reviewed)
        seen = sum(1 for r in group if r.surveyed is not None)
        total_reviewed += done
        total_surveyed += seen
        share = 100.0 * done / len(group) if group else 0.0
        lines.append(
            f"{directory:34} {done:9d} {seen:9d} {len(group):7d}  {share:7.1f}%"
        )
    share = 100.0 * total_reviewed / len(reviews) if reviews else 0.0
    lines.append(
        f"{'TOTAL':34} {total_reviewed:9d} {total_surveyed:9d} "
        f"{len(reviews):7d}  {share:7.1f}%"
    )

    ranked = [r for r in reviews if r.rank and not r.reviewed]
    if ranked:
        lines.append("")
        lines.append(
            f"Worklist -- surveyed, ranked, not yet read ({len(ranked)}). "
            "A: " + RANKS["A"]
        )
        for rank in ("A", "B"):
            group = [r for r in ranked if r.rank == rank]
            if not group:
                continue
            lines.append(f"  {rank} ({len(group)}):")
            for review in group:
                facets = ",".join(review.facets)
                lines.append(
                    f"    {review.path.relative_to(root)}"
                    f"{f' [{facets}]' if facets else ''}: {review.value}"
                )
        for rank in ("C", "D"):
            group = [r for r in ranked if r.rank == rank]
            if group:
                lines.append(f"  {rank} ({len(group)}) -- {RANKS[rank]}")

    taken = [(r, t) for r in reviews if r.reviewed for t in r.taken]
    if taken:
        lines.append("")
        lines.append(f"Taken into ChiSurf ({len(taken)}):")
        for review, entry in taken:
            lines.append(f"  {review.path.relative_to(root)}: {entry}")
    skipped = [(r, t) for r in reviews if r.reviewed for t in r.skipped]
    if skipped:
        lines.append("")
        lines.append(f"Read and deliberately not taken ({len(skipped)}):")
        for review, entry in skipped:
            lines.append(f"  {review.path.relative_to(root)}: {entry}")
    return "\n".join(lines)


def _preset_for(name: str) -> str:
    """The preset a checkout's directory name implies, or ``""``."""
    lowered = name.lower()
    if "pymol" in lowered:
        return "pymol"
    if "chimerax" in lowered:
        return "chimerax"
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "root", nargs="?", help="path to a reference checkout under junk/"
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        help="narrow to the directories worth reading in a known checkout",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="one line per checkout under junk/, so the whole shelf is visible",
    )
    parser.add_argument(
        "--unreviewed",
        metavar="DIR",
        help="list the unreviewed files under this directory instead of the table",
    )
    parser.add_argument(
        "--unsurveyed",
        metavar="DIR",
        help="list the files under this directory nobody has even triaged",
    )
    parser.add_argument(
        "--rank",
        metavar="LETTER",
        help="list only the surveyed files at this rank (A..D), highest value first",
    )
    args = parser.parse_args(argv)

    if args.all:
        junk = pathlib.Path(args.root or "junk").resolve()
        if not junk.is_dir():
            print(f"no such directory: {junk}", file=sys.stderr)
            return 2
        print(f"{'checkout':34} {'reviewed':>10} {'files':>7}  {'coverage':>8}")
        for checkout in sorted(p for p in junk.iterdir() if p.is_dir()):
            preset = PRESETS.get(_preset_for(checkout.name))
            reviews = survey(checkout, preset)
            if not reviews:
                continue
            done = sum(1 for r in reviews if r.reviewed)
            share = 100.0 * done / len(reviews)
            print(f"{checkout.name:34} {done:10d} {len(reviews):7d}  {share:7.1f}%")
        return 0

    if not args.root:
        print("give a checkout, or --all", file=sys.stderr)
        return 2
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print(f"no such checkout: {root}", file=sys.stderr)
        return 2
    directories = PRESETS.get(args.preset or "") or PRESETS.get(_preset_for(root.name))

    if args.unreviewed:
        reviews = survey(root, (args.unreviewed,))
        for review in reviews:
            if not review.reviewed:
                print(review.path.relative_to(root))
        return 0

    if args.unsurveyed:
        reviews = survey(root, (args.unsurveyed,))
        for review in reviews:
            if not review.touched:
                print(review.path.relative_to(root))
        return 0

    if args.rank:
        wanted = args.rank.upper()
        for review in survey(root, directories):
            if review.rank != wanted:
                continue
            facets = ",".join(review.facets)
            print(
                f"{review.path.relative_to(root)}"
                f"{f' [{facets}]' if facets else ''}: {review.value}"
            )
        return 0

    print(report(survey(root, directories), root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
