r"""Triage a reference checkout, and write what each file is worth into it.

The companion to :mod:`reference_coverage`. That one answers *what has been
read*; this one exists because the honest answer was "almost nothing, and no
one can tell which of the four hundred remaining files would repay reading".

A **survey** is the cheap half of the loop: open a file, see what is in it, and
write one ranked line into its header saying what ChiSurf would get from
reading it properly. The next session then starts from a worklist instead of a
directory listing::

    python -m build_tools.dev_utils.reference_annotate junk/pymol-open-source \\
        --digest layer4
    python -m build_tools.dev_utils.reference_annotate junk/pymol-open-source \\
        --apply survey.json
    python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source --rank A

``--digest`` prints, per file, the evidence a rank is judged on: size, the
file's own header comment, the symbols it defines, and the settings it reads.
``--apply`` takes ``{relative/path: {rank, facets, value}}`` and inserts the
header. The **judgement is not automated** -- a script cannot say whether
PyMOL's wizard framework is worth having -- so the rank comes from a person (or
an agent) reading the digest, and this tool only gathers and writes.

Two rules, both inherited from the workflow concept
(``okf/workflows/reference-checkouts.md``):

* **header only, never the code.** A ``git diff`` inside the checkout must show
  insertions and zero deletions.
* **`SURVEYED` is not `REVIEWED`.** A survey is a look, not a read; conflating
  them would inflate the one number that says whether the source is exhausted.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

#: The OKF concept a PyMOL marker points back at. The markers are an index;
#: the concept is the record, because `junk/` is gitignored and re-clonable.
DEFAULT_RECORD = "okf/plugins/pymol-parity.md"

#: What a rank means, repeated here so `--digest` can print it beside the
#: evidence rather than sending the reader to another file.
RANKS = {
    "A": "read next -- a behaviour chimol needs and does not have",
    "B": "worth reading when that area comes up",
    "C": "reference only -- consult for a detail, do not transcribe",
    "D": "nothing here for chimol",
}

#: The facets a file can carry value in. Named, so a worklist can be filtered
#: by what someone is actually working on.
FACETS = ("ux", "gui", "feature", "render", "data", "perf")

_MARKED = re.compile(r"CHISURF-(REVIEWED|SURVEYED):", re.IGNORECASE)
_CPP_SYMBOL = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+\"C\"\s+)*"
    r"(?:[A-Za-z_][\w:<>*&\s]*?)\s+\**([A-Za-z_]\w*)\s*\([^;]*$",
    re.MULTILINE,
)
_CPP_TYPE = re.compile(r"^(?:class|struct|enum)\s+([A-Za-z_]\w*)", re.MULTILINE)
_PY_SYMBOL = re.compile(r"^(?:class|def)\s+([A-Za-z_]\w*)", re.MULTILINE)
_SETTING = re.compile(r"cSetting_([a-z0-9_]+)")
_SUFFIXES = {".cpp", ".c", ".h", ".py"}


def _head_comment(text: str, suffix: str) -> str:
    """The file's own opening comment, which is usually what it is *for*."""
    lines = text.splitlines()[:60]
    picked: list[str] = []
    if suffix == ".py":
        if lines and lines[0].startswith(('"""', "'''")):
            for line in lines:
                picked.append(line.strip().strip('"' + "'"))
                if len(picked) > 1 and line.rstrip().endswith(('"""', "'''")):
                    break
    else:
        started = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("/*"):
                started = True
            if started:
                picked.append(stripped.lstrip("/*").lstrip("*").strip())
            if started and stripped.endswith("*/"):
                break
    # PyMOL's files all open with the same copyright block; it says nothing.
    dropped = [
        p for p in picked
        if p and not p.startswith(("A*", "B*", "C*", "D*", "E*", "F*", "G*",
                                   "H*", "I*", "-*", "Z*"))
        and "copyright" not in p.lower()
        and "LICENSE" not in p
        and not set(p) <= {"-", "*", "="}
    ]
    return " ".join(dropped)[:400]


def digest(path: pathlib.Path, root: pathlib.Path) -> dict:
    """Everything a rank should be judged on, without reading the whole file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".py":
        symbols = _PY_SYMBOL.findall(text)
    else:
        symbols = _CPP_TYPE.findall(text) + _CPP_SYMBOL.findall(text)
    settings = sorted(set(_SETTING.findall(text)))
    seen = _MARKED.search(text[:2000])
    return {
        "path": str(path.relative_to(root)),
        "lines": text.count("\n") + 1,
        "marked": bool(seen),
        "about": _head_comment(text, suffix),
        "symbols": symbols[:24],
        "settings": settings[:24],
        "n_symbols": len(symbols),
        "n_settings": len(settings),
    }


def header_for(path: pathlib.Path, entry: dict, date: str, record: str) -> str:
    """The marker block, in the file's own comment syntax.

    An entry with ``reviewed`` set was **read**, not merely surveyed, and gets
    the `CHISURF-REVIEWED` marker with whatever it yielded -- `taken` and
    `skipped` -- on top of the ranked value line. The two depths are written by
    one tool because they are one loop: a survey ranks a file, reading it
    closes it, and the file should end up carrying both.
    """
    rank = str(entry["rank"]).upper()
    if rank not in RANKS:
        raise ValueError(f"{path}: rank {rank!r} is not one of {sorted(RANKS)}")
    facets = ",".join(
        f.strip() for f in str(entry.get("facets", "")).split(",") if f.strip()
    )
    for facet in facets.split(",") if facets else []:
        if facet not in FACETS:
            raise ValueError(f"{path}: facet {facet!r} is not one of {FACETS}")
    value = " ".join(str(entry["value"]).split())
    body = [f"CHISURF-SURVEYED: {date}"]
    if entry.get("reviewed"):
        body.append(f"CHISURF-REVIEWED: {date}")
    body.append(f"CHISURF-VALUE: {rank} {facets} -- {value}")
    for taken in entry.get("taken", []):
        body.append(f"CHISURF-TAKEN: {' '.join(str(taken).split())}")
    for skipped in entry.get("skipped", []):
        body.append(f"CHISURF-SKIPPED: {' '.join(str(skipped).split())}")
    body += [
        f"CHISURF-RECORD: {record}",
        "Header added by ChiSurf; the code below is untouched.",
    ]
    if path.suffix.lower() == ".py":
        return "".join(f"# {line}\n" for line in body)
    return "/*\n" + "".join(f" * {line}\n" for line in body) + " */\n"


def apply(root: pathlib.Path, notes: dict, date: str, record: str) -> tuple[int, int]:
    """Insert a header per note. Returns ``(written, skipped)``."""
    written = skipped = 0
    for relative, entry in notes.items():
        path = root / relative
        if not path.is_file():
            print(f"missing: {relative}", file=sys.stderr)
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _MARKED.search(text[:2000]):
            skipped += 1
            continue
        path.write_text(
            header_for(path, entry, date, record) + text, encoding="utf-8"
        )
        written += 1
    return written, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", help="path to a reference checkout under junk/")
    parser.add_argument(
        "--digest", metavar="DIR", help="print the triage evidence for this directory"
    )
    parser.add_argument(
        "--apply", metavar="JSON", help="insert headers from {path: {rank, facets, value}}"
    )
    parser.add_argument("--date", default="", help="the survey date (YYYY-MM-DD)")
    parser.add_argument("--record", default=DEFAULT_RECORD, help="the OKF concept")
    parser.add_argument(
        "--unmarked-only",
        action="store_true",
        help="digest only the files that carry no marker yet",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print(f"no such checkout: {root}", file=sys.stderr)
        return 2

    if args.digest:
        base = root / args.digest
        paths = [
            p for p in sorted(base.rglob("*"))
            if p.is_file() and p.suffix.lower() in _SUFFIXES
        ] if base.is_dir() else [base]
        out = [digest(p, root) for p in paths if p.is_file()]
        if args.unmarked_only:
            out = [d for d in out if not d["marked"]]
        print(json.dumps(out, indent=1))
        return 0

    if args.apply:
        if not args.date:
            print("--apply needs --date", file=sys.stderr)
            return 2
        notes = json.loads(pathlib.Path(args.apply).read_text(encoding="utf-8"))
        written, skipped = apply(root, notes, args.date, args.record)
        print(f"wrote {written}, skipped {skipped} (already marked or missing)")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
