"""Audit the shipped package for retired nomenclature.

The owner's nomenclature (ChiSurf and ndX, every user-visible name):

1. **detectors** are named ``<emission>|<excitation>`` from the setup
   (``G|G``, ``R|G``, ``R|R``); never the old ``green``/``red``/``yellow``
   detector names, never "donor channel" / "acceptor channel";
2. **background** rates are ``Bg_<detector>`` in kHz; never ``Bg``/``Br``/``By``,
   ``B_<det>``, ``n_bg``, ``g_bg``/``s_bg`` or a "Background (kHz)" header;
3. **polarisation** is ``VV`` / ``VH``; never ``par``/``per`` or ``∥``/``⊥``;
4. **lifetimes and anisotropies** are named after their detector
   (``Tau (G|G)``, ``r (R|R)``); never ``τ_D``/``τ_A``/``r_D``/``r_A`` or
   "donor lifetime" as a column / control name (``τ_D(0)``, the donor-only
   lifetime of the FRET line, is a physical quantity and stays);
5. **ranges** are ``a:b``; never ``a-b`` / ``a–b`` (a column's ``| 0-2048``,
   an f-string ``{lo}-{hi}``);
6. the **G factor** is per detection colour: ``G (G|G)``; never ``G (green)``;
7. **no HDF5**: CSV at most for exports.

Each rule is a set of regexes with exclusions. The scan covers the shipped
package and reports it by area: ``chisurf/`` Python, ndX's ``ndxplorer/``
Python, ``view.json`` specs, YAML/JSON settings, shipped help markdown, and,
separately, ``docs/`` and ``okf/``. Tests are not scanned: they document the
old names they migrate.

Usage::

    python -m build_tools.dev_utils.nomenclature_audit            # counts per area
    python -m build_tools.dev_utils.nomenclature_audit --hits     # every hit
    python -m build_tools.dev_utils.nomenclature_audit --rule bg --area docs --hits

The guard ``test/test_nomenclature.py`` runs :func:`scan` against the
shrinking ``test/nomenclature_allowlist.txt``.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys
from typing import Dict, Iterable, Iterator, List, NamedTuple, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
NDX = ROOT / "modules" / "ndxplorer" / "ndxplorer"

_TEXT = {".py", ".json", ".md", ".yaml", ".yml", ".rst", ".txt"}

#: Directories never scanned: tests document the names they migrate, build
#: output and caches are not source, locale catalogues follow their source.
_SKIP_PARTS = {"tests", "test", "__pycache__", "build", "dist", ".git", "node_modules",
               "locale", "i18n", "junk", ".pixi", "_build", "firmware"}

#: Files that *are* the read-side migration of old names (the one place a
#: retired spelling is allowed to be named, so that old data opens).
MIGRATION_FILES = {
    "chisurf/core/fluorescence/detector_names.py",
    "modules/ndxplorer/ndxplorer/core/detector_names.py",
    "chisurf/core/fluorescence/nomenclature_migration.py",
    "build_tools/dev_utils/nomenclature_audit.py",
    "okf/references/nomenclature.md",  # the rule's own page names what it retires
}


class Rule(NamedTuple):
    """One retired term: a pattern, the lines it must not fire on, and where it counts.

    ``where`` is ``"all"`` (a retired *name*: wrong everywhere it is spelled) or
    ``"visible"`` (a retired *phrase*: wrong where a user reads it -- a view
    spec, a settings file, help or a guide, a translated / label / tooltip
    string in Python -- and fine as physics prose in a docstring, a comment or
    a concept page).
    """

    key: str
    title: str
    pattern: re.Pattern
    exclude: Tuple[re.Pattern, ...] = ()
    where: str = "all"
    #: ``"match"``: an exclusion rescues only what it covers; ``"line"``: the whole line.
    exclude_mode: str = "match"


def _rx(text: str, flags: int = 0) -> re.Pattern:
    return re.compile(text, flags)


#: A Python line a user reads: a translated string, a label, a tooltip, a help text.
_VISIBLE_PY = _rx(r"\btr\(|\bmark\(|label|tooltip|\btip\b|description|help=|title|header|"
                  r"status|message|\.text\(|caption|placeholder|im\.(?:text|button|checkbox)", re.I)

RULES: Tuple[Rule, ...] = (
    Rule("detector", "old detector names: (green)/(red)/(yellow), Green Count Rate, S prompt green",
         _rx(r"\((?:green|red|yellow)\)|\b(?:Green|Red|Yellow) Count Rate"
             r"|\bS (?:prompt|delayed) (?:green|red|yellow)\b|\bTau (?:green|red|yellow)\b"
             r"|\bDuration \((?:green|red|yellow)\)", re.I),
         # a colour of something drawn (a curve, a marker, a button), not a detector
         (_rx(r"\b(?:plot|curves?|lines?|drawn|shown|highlight\w*|markers?|button|linked|IRF|"
              r"threshold|target bin|GPIO|laser|TTL|colou?rs?|cyan|blue\)|fit window|"
              r"parameter\*\*|\?\*\*)", re.I),),
         exclude_mode="line"),
    Rule("detector_word", "green/red/donor/acceptor channel or detector as a detector's name",
         _rx(r"\b(?:donor|acceptor|green|red|yellow) (?:channel|detector)s?\b", re.I),
         where="visible"),
    Rule("bg", "retired background names (Bg/Br/By, B_<det>, n_bg, g_bg/s_bg, Background (kHz))",
         _rx(r"['\"](?:Bg|Br|By|BG|BR|BY)['\"]|\b(?:Bg|Br|By)\s*(?::\s*float|=\s*[\d.]|\s*[-+*/]\s*\w)"
             r"|\bB_(?:[BGRY]\|[BGRY]|G|R|Y|green|red|yellow)\b"
             r"|\bn_bg\b|\bg_bg\b|\bs_bg\b"
             r"|Background \(kHz\)|Background rate \(kHz\)"),
         (_rx(r'"Symbol"|"title": "By"|\bBr\b"?: \{|"BR": 1\.|PAIRS'),)),
    Rule("polarisation", "par/per, parallel/perpendicular or ∥/⊥ for a polarisation channel (VV/VH)",
         _rx(r"[∥⊥]|\b(?:par|perp?)\s*/\s*(?:par|perp?)\b"
             r"|[\"'](?:par|perp|parallel|perpendicular|Parallel|Perpendicular)[\"']"
             r"|\((?:par|per|perp)\)"
             r"|\b(?:parallel|perpendicular) (?:channel|detector|signal|decay|polari[sz]ation)s?\b",
             re.I),
         (_rx(r"\"perp\": \"⊥\""),)),
    Rule("polarisation_ident", "par/perp in a code identifier (i_par, n_perp, par_raw)",
         _rx(r"\b[a-z]\w*_(?:par|perp?)\b|\b(?:par|perp)_[a-z]\w*"),
         (_rx(r"\b(?:n|num|n_fit|n_free)_par\b|\bpar_(?:ams?|ser?|tition|ent|ti\w*|allel\w*|se\w*)\b"
              r"|\b\w*_per_\w*|\bperp_?endicular", re.I),)),
    Rule("lifetime", "a detector's lifetime / anisotropy named donor/acceptor (Tau (G|G), r (R|R))",
         _rx(r"τ_[DA] (?:donor|acceptor)|\br_[DA] (?:donor|acceptor)"
             r"|\b(?:donor|acceptor) (?:lifetime|anisotropy) column"
             r"|\bTau (?:green|red|yellow)\b|\b(?:lifetime|anisotropy) (?:green|red|yellow)\b",
             re.I)),
    Rule("range", "ranges written a-b / a–b instead of a:b",
         _rx(r"\)\s*\|\s*\d+\s*[-–]\s*\d+\b|\|\s*\{\w+\}\s*[-–]\s*\{\w+\}"
             r"|f[\"'][^\"'\n]*\{[^{}\n#]+\}[-–]\{[^{}\n]+\}"
             r"|\b(?:channels?|bins?|windows?|gates?|range|tail)\s+\d+\s*[-–]\s*\d+\b", re.I),
         (_rx(r"\d{4}-\d{2}-\d{2}|uuid|stamp|digest|serial|\{i:03d\}|resSeq|##|\{stem\}|\{key\}|"
              r"\{ident\}|\{prefix\}|\{name\}-|\{base|\{n\}\{|object_uuid|\{i\}-\{j\}|"
              r"\.(?:csv|png|zip|json|txt|pto|svg)\b|_name\s*=|path\s*=", re.I),),
         exclude_mode="line"),
    Rule("gfactor", "G factor not per detection colour (G (green), G_green)",
         _rx(r"\bG\s*\((?:green|red|yellow)\)|\bG_(?:green|red|yellow)\b"
             r"|\bg_?factor_(?:green|red|yellow)\b", re.I)),
    Rule("hdf5", "HDF5 (CSV at most for exports)",
         _rx(r"\bHDF5?\b|\bh5py\b|\.h5\b|\.hdf5?\b|\bto_hdf\b|\bread_hdf\b|\bhdf5\b", re.I)),
)

RULE_KEYS = tuple(r.key for r in RULES)


def _area(rel: str, suffix: str) -> str:
    """The audit area of a repo-relative path."""
    if rel.startswith("docs/"):
        return "docs"
    if rel.startswith("okf/"):
        return "okf"
    if rel.endswith("view.json") or rel.endswith(".view.json") or "/views/" in rel:
        return "view_specs"
    if suffix in {".yaml", ".yml", ".json"}:
        return "settings"
    if suffix in {".md", ".rst", ".txt"}:
        return "help_md"
    if rel.startswith("modules/ndxplorer/"):
        return "ndxplorer"
    return "chisurf"


AREAS = ("chisurf", "ndxplorer", "view_specs", "settings", "help_md", "docs", "okf")


def _files(roots: Iterable[pathlib.Path]) -> Iterator[pathlib.Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _TEXT:
                continue
            rel_parts = path.relative_to(ROOT).parts
            if _SKIP_PARTS.intersection(rel_parts[:-1]):
                continue
            name = path.name
            if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
                continue
            yield path


def _roots(include_docs: bool = True) -> List[pathlib.Path]:
    roots = [ROOT / "chisurf", NDX]
    if include_docs:
        roots += [ROOT / "docs", ROOT / "okf"]
    return roots


class Hit(NamedTuple):
    """One retired term found."""

    rel: str
    area: str
    rule: str
    line: int
    text: str


#: Generated docs pages: fixed through their generator, not counted twice.
_GENERATED = ("docs/reference/plugins/",)
#: OKF history: a dated log records what happened, in the words of the day.
_HISTORY = ("okf/log.md", "okf/agent-board.md", "docs/changelog", "okf/prds/")


def _visible(rel: str, area: str, line: str) -> bool:
    """Whether *line* of *rel* is one a user reads (for ``where="visible"`` rules)."""
    if rel.startswith(("docs/concepts/", "docs/references/", "docs/development/", "docs/manual/",
                       "okf/")):
        return False  # theory, literature, process: physics prose is the point
    if area in ("chisurf", "ndxplorer"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            return False
        return bool(_VISIBLE_PY.search(line))
    return True


def scan(include_docs: bool = True, rules: Iterable[str] = RULE_KEYS) -> List[Hit]:
    """Every retired-term hit in the scanned tree."""
    wanted = [r for r in RULES if r.key in set(rules)]
    hits: List[Hit] = []
    for path in _files(_roots(include_docs)):
        rel = path.relative_to(ROOT).as_posix()
        if rel in MIGRATION_FILES or rel.startswith(_HISTORY):
            continue
        area = _area(rel, path.suffix.lower())
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for no, line in enumerate(text.splitlines(), 1):
            if "nomenclature: ok" in line:
                continue
            for rule in wanted:
                if not rule.pattern.search(line):
                    continue
                if rule.where == "visible" and not _visible(rel, area, line):
                    continue
                if any(ex.search(line) for ex in rule.exclude):
                    if rule.exclude_mode == "line":
                        continue
                    # an exclusion only rescues the line when every match is inside it
                    rest = line
                    for ex in rule.exclude:
                        rest = ex.sub(" ", rest)
                    if not rule.pattern.search(rest):
                        continue
                hits.append(Hit(rel, area, rule.key, no, line.strip()[:200]))
    return hits


def counts(hits: Iterable[Hit]) -> Dict[str, Dict[str, int]]:
    """``{area: {rule: n}}``."""
    out: Dict[str, Dict[str, int]] = {a: collections.Counter() for a in AREAS}
    for hit in hits:
        out[hit.area][hit.rule] += 1
    return out


def per_file(hits: Iterable[Hit]) -> Dict[Tuple[str, str], int]:
    """``{(path, rule): n}`` -- what the guard's allowlist records."""
    return dict(collections.Counter((h.rel, h.rule) for h in hits))


def _table(c: Dict[str, Dict[str, int]]) -> str:
    head = f"{'area':<12}" + "".join(f"{k:>19}" for k in RULE_KEYS) + f"{'total':>8}"
    rows = [head, "-" * len(head)]
    grand = collections.Counter()
    for area in AREAS:
        row = c.get(area, {})
        grand.update(row)
        rows.append(f"{area:<12}" + "".join(f"{row.get(k, 0):>19}" for k in RULE_KEYS)
                    + f"{sum(row.values()):>8}")
    rows.append("-" * len(head))
    rows.append(f"{'total':<12}" + "".join(f"{grand.get(k, 0):>19}" for k in RULE_KEYS)
                + f"{sum(grand.values()):>8}")
    return "\n".join(rows)


def main(argv=None) -> int:
    """Command line: print the counts (and, with ``--hits``, every hit)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hits", action="store_true", help="list every hit")
    ap.add_argument("--rule", action="append", choices=RULE_KEYS, help="only these rules")
    ap.add_argument("--area", action="append", choices=AREAS, help="only these areas")
    ap.add_argument("--files", action="store_true", help="hits per file")
    args = ap.parse_args(argv)
    hits = scan(rules=args.rule or RULE_KEYS)
    if args.area:
        hits = [h for h in hits if h.area in args.area]
    print(_table(counts(hits)))
    if args.files:
        for (rel, rule), n in sorted(per_file(hits).items()):
            print(f"{n:5d}  {rule:<13} {rel}")
    if args.hits:
        for h in hits:
            print(f"{h.area:<10} {h.rule:<13} {h.rel}:{h.line}: {h.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
