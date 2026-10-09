"""Validate the OKF bundle; mechanical fixes never cross repository boundaries."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote, urlsplit

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from build_tools.docs.okf import (
    apply_front_matter,
    plain_text,
    read_front_matter,
    split_front_matter,
)

TYPE_BY_DIR = {
    "architecture": "Architecture",
    "subsystems": "Subsystem",
    "plugins": "Plugin Note",
    "plugins/emtk-ports": "Report",
    "plans": "Plan",
    "prds": "PRD",
    "usecases": "Use Case",
    "reviews": "Review",
    "references": "Reference",
    "specs": "Spec",
    "workflows": "Playbook",
    "handover": "Handover",
    "validation": "Validation",
    "recipes": "Recipe",
}
LEGEND = {
    "done": "✅",
    "in-progress": "🚧",
    "draft": "✏️",
    "stub": "🌱",
    "planned": "📋",
    "superseded": "⛔",
}
ALIAS = {"complete": "done", "active": "in-progress", "proposed": "draft", "obsolete": "superseded"}
DATE = r"\d{4}-\d{2}-\d{2}"


@dataclass(frozen=True)
class Finding:
    """An actionable rule violation at a bundle-relative source position."""

    rule: str
    path: str
    line: int
    msg: str
    fixable: bool = False


def _git(root: Path, *args: str) -> str:
    """Run a read-only git query, returning empty output outside a checkout."""
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def _spaces(text: str) -> str:
    """Mask content while preserving offsets and line numbers."""
    return re.sub(r"[^\n]", " ", text)


def _prose(text: str) -> str:
    """Mask YAML, fenced code and matching inline backtick runs."""
    raw, body = split_front_matter(text)
    if raw:
        text = _spaces(text[: len(text) - len(body)]) + body
    lines = text.splitlines(keepends=True)
    fence = None
    for i, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            lines[i] = _spaces(line)
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
        elif marker:
            fence = marker[1]
            lines[i] = _spaces(line)
    text = "".join(lines)
    return re.sub(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", lambda m: _spaces(m[0]), text, flags=re.S)


class Bundle:
    """Snapshot discoverable Markdown and enforce safe, concurrent-aware writes."""

    def __init__(self, root: Path):
        """Discover tracked and nonignored untracked files, including board links."""
        self.root = root.absolute()
        if not self.root.is_dir():
            raise ValueError(f"Bundle root is not a directory: {self.root}")
        self._writable_cache: dict[Path, bool] = {}
        repo = _git(self.root, "rev-parse", "--show-toplevel").strip()
        self.repo = Path(repo) if repo else self.root.parent
        if repo:
            paths = _git(
                self.repo,
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                str(self.root),
            )
            candidates = (self.repo / p for p in paths.split("\0") if p)
        else:
            candidates = self.root.rglob("*.md")
        self.pages = {
            p: p.read_text(encoding="utf-8")
            for p in sorted(set(candidates))
            if p.suffix == ".md" and p.is_file()
        }

    def finding(
        self, rule: str, path: Path, offset: int, msg: str, fixable: bool = False
    ) -> Finding:
        """Locate a finding in the original snapshot."""
        return Finding(
            rule,
            path.relative_to(self.root).as_posix(),
            self.pages[path].count("\n", 0, offset) + 1,
            msg,
            fixable and self.writable(path),
        )

    def writable(self, path: Path) -> bool:
        """Allow writes only within this repository, refusing dirty shared ledgers."""
        if path.is_symlink() and not path.resolve().is_relative_to(self.root.resolve()):
            return False
        if not path.resolve().is_relative_to(self.repo.resolve()):
            return False
        if path.name in {"log.md", "known-issues.md"}:
            if path not in self._writable_cache:
                status = _git(self.repo, "status", "--porcelain", "--", str(path))
                self._writable_cache[path] = not any(
                    line and not line.startswith("??") for line in status.splitlines()
                )
            return self._writable_cache[path]
        return True

    def write(self, path: Path, text: str) -> None:
        """Write only unchanged, owned snapshots and retain the updated snapshot."""
        if text == self.pages[path]:
            return
        if not self.writable(path):
            print(
                f"Refusing fix for {path}: external symlink/repository or dirty shared ledger",
                file=sys.stderr,
            )
            return
        if path.read_text(encoding="utf-8") != self.pages[path]:
            raise RuntimeError(f"Concurrent edit: {path}")
        path.write_text(text, encoding="utf-8")
        self.pages[path] = text


def fm(bundle: Bundle, fix: bool) -> list[Finding]:
    """Require metadata and derive conservative stubs from authored prose."""
    findings: list[Finding] = []
    for path, text in list(bundle.pages.items()):
        if path.name in {"index.md", "log.md", "agent-board.md"}:
            continue
        meta = read_front_matter(text)
        missing = [
            key
            for key in ("type", "title", "description")
            if not isinstance(meta.get(key), str) or not meta[key].strip()
        ]
        if not missing:
            continue
        raw, body = split_front_matter(text)
        malformed = (text.startswith("---\n") and not raw) or (bool(raw) and not meta)
        findings.append(
            bundle.finding(
                "FM", path, 0, "missing non-empty fields: " + ", ".join(missing), not malformed
            )
        )
        if fix and not malformed:
            relative = path.relative_to(bundle.root)
            heading = re.search(r"^# (.+)$", _prose(body), re.M)
            paragraphs = [
                plain_text(p)
                for p in re.split(r"\n\s*\n", _prose(body))
                if p.strip() and not p.lstrip().startswith(("#", "-", "*", "|", ">"))
            ]
            kind = next(
                (
                    TYPE_BY_DIR[k]
                    for k in sorted(TYPE_BY_DIR, key=len, reverse=True)
                    if relative.as_posix().startswith(k + "/")
                ),
                "Concept",
            )
            defaults = {
                "type": kind,
                "title": plain_text(heading[1]) if heading else path.stem,
                "description": paragraphs[0][:200] if paragraphs else "",
                "tags": [relative.parts[0]],
                "timestamp": _git(bundle.repo, "log", "-1", "--format=%cI", "--", str(path)).strip()
                or date.today().isoformat(),
            }
            for key, value in defaults.items():
                if key in missing or not meta.get(key):
                    meta[key] = value
            if re.fullmatch(r"prd-\d+", path.stem):
                meta.setdefault("prd", path.stem[4:])
            # Existing YAML may include booleans and nested mappings that the
            # documentation stub renderer intentionally does not model.
            rendered = (
                (
                    "---\n"
                    + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
                    + "---\n\n"
                    + body.lstrip("\n")
                )
                if raw
                else apply_front_matter(text, meta)
            )
            bundle.write(path, rendered)
    return findings


def links(bundle: Bundle, fix: bool) -> list[Finding]:
    """Resolve local Markdown destinations under the bundle-root convention."""
    findings: list[Finding] = []
    pattern = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+['\"][^\n]*?['\"])?\s*\)")
    for path, text in list(bundle.pages.items()):
        changes = []
        for match in pattern.finditer(_prose(text)):
            target = match[1].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            value = unquote(parsed.path)
            foreign = value.startswith(("/Users/", "/home/", "/private/", "/tmp/"))
            repo_link = bool(re.match(r"^/(chisurf|docs|modules|test)/", value))
            resolved = (
                Path(value)
                if foreign
                else (
                    bundle.repo / value[1:]
                    if repo_link
                    else bundle.root / value[1:]
                    if value.startswith("/")
                    else path.parent / value
                )
            )
            if foreign or repo_link or not resolved.exists():
                repair = (foreign or repo_link) and resolved.exists()
                findings.append(
                    bundle.finding(
                        "LINK",
                        path,
                        match.start(),
                        f"{'nonportable' if foreign or repo_link else 'missing'} link: {target}",
                        repair,
                    )
                )
                if fix and repair:
                    replacement = (
                        quote(os.path.relpath(resolved, path.parent), safe="/")
                        + ("?" + parsed.query if parsed.query else "")
                        + ("#" + parsed.fragment if parsed.fragment else "")
                    )
                    if match[1].startswith("<"):
                        replacement = "<" + replacement + ">"
                    changes.append((match.start(1), match.end(1), replacement))
        for start, end, replacement in reversed(changes):
            text = text[:start] + replacement + text[end:]
        if changes:
            bundle.write(path, text)
    return findings


def wiki(bundle: Bundle, fix: bool) -> list[Finding]:
    """Reject prose wikilinks without flagging code examples."""
    return [
        bundle.finding("WIKI", p, m.start(), "wikilink: " + m[0])
        for p, t in bundle.pages.items()
        for m in re.finditer(r"\[\[[^\[\]]+\]\]", _prose(t))
    ]


def prd(bundle: Bundle, fix: bool) -> list[Finding]:
    """Check canonical PRD status, index membership and status glyphs."""
    findings: list[Finding] = []
    index = bundle.root / "prds/index.md"
    index_text = bundle.pages.get(index, "")
    pattern = re.compile(r"^(?:\*|-) (\S+) \[.*?\]\((prd-[^)]+\.md)\)", re.M)
    entries = {m[2]: m for m in pattern.finditer(_prose(index_text))}
    replacements = []
    additions = []
    for path, text in list(bundle.pages.items()):
        if path.parent != bundle.root / "prds" or not re.fullmatch(r"prd-\d+\.md", path.name):
            continue
        meta = read_front_matter(text)
        raw = str(meta.get("status", ""))
        status = ALIAS.get(raw.casefold(), raw.casefold())
        if status not in LEGEND:
            findings.append(bundle.finding("PRD", path, 0, f"unknown status: {raw or '(missing)'}"))
        elif raw != status:
            findings.append(
                bundle.finding("PRD", path, 0, f"noncanonical status: {raw} -> {status}", True)
            )
            if fix:
                bundle.write(path, re.sub(r"(?m)^status:.*$", "status: " + status, text, count=1))
        entry = entries.get(path.name)
        if entry is None:
            findings.append(
                bundle.finding(
                    "PRD", path, 0, "PRD is not indexed", status in LEGEND and index in bundle.pages
                )
            )
            if status in LEGEND:
                title = str(meta.get("title") or path.stem)
                additions.append(f"* {LEGEND[status]} [{title}]({path.name})\n")
        elif status in LEGEND and entry[1] != LEGEND[status]:
            findings.append(
                bundle.finding(
                    "PRD",
                    index,
                    entry.start(),
                    f"{path.name}: glyph {entry[1]} should be {LEGEND[status]}",
                    True,
                )
            )
            replacements.append((entry.start(1), entry.end(1), LEGEND[status]))
    if fix and index in bundle.pages:
        for start, end, glyph in sorted(replacements, reverse=True):
            index_text = index_text[:start] + glyph + index_text[end:]
        if additions:
            if "# Unsorted (added by okf_lint)" not in index_text:
                index_text = index_text.rstrip() + "\n\n# Unsorted (added by okf_lint)\n\n"
            index_text += "".join(additions)
        bundle.write(index, index_text)
    return findings


def _blocks(text: str, pattern: str) -> tuple[str, list[tuple[int, str]]]:
    """Split original text at prose-only structural markers."""
    matches = list(re.finditer(pattern, _prose(text), re.M))
    return (
        text[: matches[0].start()] if matches else text,
        [
            (
                m.start(),
                text[m.start() : matches[i + 1].start() if i + 1 < len(matches) else len(text)],
            )
            for i, m in enumerate(matches)
        ],
    )


def ki(bundle: Bundle, fix: bool) -> list[Finding]:
    """Check issue uniqueness, explicit status and descending discovery dates."""
    path = bundle.root / "references/known-issues.md"
    if path not in bundle.pages:
        return []
    prefix, blocks = _blocks(bundle.pages[path], r"^## ")
    findings, output = [], []
    seen: dict[str, str] = {}
    previous = "9999-99-99"
    status_pattern = re.compile(rf"status: (?:open|(?:resolved|withdrawn) {DATE})(?: — .+)?$")
    for offset, block in blocks:
        lines = block.splitlines()
        title = lines[0][3:].strip()
        duplicate = title in seen
        identical = duplicate and seen[title].strip() == block.strip()
        if duplicate:
            findings.append(
                bundle.finding("KI", path, offset, "duplicate title: " + title, identical)
            )
        seen.setdefault(title, block)
        first = next((line.strip() for line in lines[1:] if line.strip()), "")
        date_match = (
            re.search(DATE, first if first.startswith("status:") else "")
            or re.search(DATE, title)
            or re.search(DATE, "\n".join(lines[1:]))
        )
        entry_date = (
            date_match[0]
            if date_match
            else _git(
                bundle.repo, "log", "--follow", "--format=%cs", "-1", "-S" + title, "--", str(path)
            ).strip()
        )
        if not entry_date:
            findings.append(
                bundle.finding("KI", path, offset, "issue has no derivable date: " + title)
            )
        if not status_pattern.fullmatch(first):
            # Never reinterpret an explicit (but invalid) authored status.
            derivable = not first.startswith("status:")
            marker = re.search(
                r"✅\s*FIXED|\bRESOLVED\b|\bWITHDRAWN\b|\(closed\)|~~|\(fixed[^)]*\)|—\s*FIXED",
                title,
            )
            can_fix = derivable and (not marker or bool(entry_date))
            findings.append(
                bundle.finding(
                    "KI",
                    path,
                    offset,
                    "first nonblank line must be status: open|resolved DATE|withdrawn DATE",
                    can_fix,
                )
            )
            if fix and can_fix:
                status = (
                    ("withdrawn" if "WITHDRAWN" in title else "resolved") + " " + entry_date
                    if marker
                    else "open"
                )
                title = re.sub(
                    r"✅\s*FIXED|\bRESOLVED\b|\bWITHDRAWN\b|\(closed\)|~~|\(fixed[^)]*\)|—\s*FIXED",
                    "",
                    title,
                ).strip()
                block = (
                    "## "
                    + title
                    + "\n\nstatus: "
                    + status
                    + "\n\n"
                    + "\n".join(lines[1:]).lstrip("\n")
                    + "\n"
                )
        if entry_date and entry_date > previous:
            findings.append(bundle.finding("KI", path, offset, "issues are not newest first", True))
        if entry_date:
            previous = entry_date
        if not (fix and identical):
            output.append((entry_date, block))
    if fix:
        bundle.write(
            path,
            prefix
            + "".join(
                block.rstrip() + "\n\n"
                for _, block in sorted(output, key=lambda pair: pair[0], reverse=True)
            ),
        )
    return findings


def board(bundle: Bundle, fix: bool) -> list[Finding]:
    """Check ticket identity, active scopes and completed-ticket placement."""
    path = bundle.root / "agent-board.md"
    if path not in bundle.pages:
        return []
    text = bundle.pages[path]
    prefix, sections = _blocks(text, r"^## ")
    findings, seen, moved, rewritten = [], set(), [], []
    for section_offset, section in sections:
        heading = section.splitlines()[0]
        intro, tickets = _blocks(section, r"^- \*\*T-")
        kept = []
        for offset, block in tickets:
            identity = re.match(r"- \*\*(T-[^*\s:]+)", block)
            if not identity:
                continue
            ticket = identity[1]
            if ticket in seen:
                findings.append(
                    bundle.finding(
                        "BOARD", path, section_offset + offset, "duplicate ticket: " + ticket
                    )
                )
            seen.add(ticket)
            prose = _prose(block)
            if "🔄" in prose and not re.search(r"\bTouching\s*:", prose):
                findings.append(
                    bundle.finding(
                        "BOARD",
                        path,
                        section_offset + offset,
                        ticket + ": active ticket lacks Touching:",
                    )
                )
            completed = "✅" in prose and bool(re.match(r"## (Open|Active)\b", heading))
            if completed:
                findings.append(
                    bundle.finding(
                        "BOARD",
                        path,
                        section_offset + offset,
                        ticket + ": completed ticket in active/open section",
                        True,
                    )
                )
            if completed and fix:
                moved.append(block)
            else:
                kept.append(block)
        rewritten.append((heading, intro, kept))
    if fix and moved:
        found = False
        chunks = [prefix]
        for heading, intro, kept in rewritten:
            if not found and re.match(r"## Resolved\b", heading):
                kept = moved + kept
                found = True
            chunks.append(intro + "".join(kept))
        if not found:
            chunks.append("\n## Resolved\n\n" + "".join(moved))
        bundle.write(path, "".join(chunks))
    return findings


def log(bundle: Bundle, fix: bool) -> list[Finding]:
    """Normalize dated log sections without losing any normalized bullet body."""
    path = bundle.root / "log.md"
    if path not in bundle.pages:
        return []
    text = bundle.pages[path]
    lines = text.splitlines(keepends=True)
    prose_lines = _prose(text).splitlines(keepends=True)
    findings, prefix, bullets_before = [], [], []
    sections: dict[str, list[str]] = {}
    current = None
    previous = "9999-99-99"
    offset = 0
    safe = True
    i = 0
    heading_seen = False
    tail = re.compile(rf"^- (?:\*\*({DATE})\*\*\s*[—-]\s*|({DATE})[ :·]\s*)(.*)")
    while i < len(lines):
        line = lines[i]
        prose = prose_lines[i]
        if re.match(r"^#{1,6} ", prose) and not prose.startswith("## "):
            if not (prose.startswith("# ") and not heading_seen and current is None):
                findings.append(
                    bundle.finding(
                        "LOG", path, offset, "only the initial H1 and dated H2 sections are allowed"
                    )
                )
                safe = False
                current = None
            heading_seen = True
        if prose.startswith("## "):
            heading_seen = True
            match = re.fullmatch(rf"## ({DATE})(?:[^\n]*)\n?", prose)
            if not match:
                findings.append(
                    bundle.finding("LOG", path, offset, "log section must be ## YYYY-MM-DD")
                )
                safe = False
                current = None
                prefix.append(line)
            else:
                day = match[1]
                if prose.strip() != "## " + day or day >= previous:
                    findings.append(
                        bundle.finding(
                            "LOG",
                            path,
                            offset,
                            "log dates must be unique, plain and newest first",
                            True,
                        )
                    )
                current = day
                previous = day
                sections.setdefault(day, [])
            offset += len(line)
            i += 1
            continue
        if re.match(r"^[-*+] ", prose):
            start = offset
            chunk = [line]
            i += 1
            offset += len(line)
            # Preserve the complete bullet, including fenced/indented continuations.
            while i < len(lines) and not re.match(r"^(?:[-*+] |#{1,6} )", prose_lines[i]):
                chunk.append(lines[i])
                offset += len(lines[i])
                i += 1
            body = "".join(chunk).rstrip()
            dated = tail.match(body)
            day = (dated[1] or dated[2]) if dated else current
            if dated:
                body = "- " + dated[3] + body[len(dated[0]) :]
                findings.append(
                    bundle.finding(
                        "LOG",
                        path,
                        start,
                        "dated tail bullet must be folded into its day section",
                        True,
                    )
                )
            if day is None:
                findings.append(
                    bundle.finding("LOG", path, start, "bullet outside a dated section")
                )
                prefix.append("".join(chunk))
                safe = False
            else:
                existing = sections.setdefault(day, [])
                if body in existing:
                    findings.append(
                        bundle.finding("LOG", path, start, "duplicate log bullet", True)
                    )
                existing.append(body)
            bullets_before.append(body)
            continue
        # Preserve introductory text; non-bullet section text is not mechanically movable.
        if current is None:
            prefix.append(line)
        elif line.strip():
            sections[current].append(line.rstrip())
        offset += len(line)
        i += 1
    if fix and safe:
        chunks = ["".join(prefix).rstrip() + "\n\n"]
        after = []
        for day in sorted(sections, reverse=True):
            chunks.append("## " + day + "\n\n")
            seen = set()
            for body in sections[day]:
                is_bullet = bool(re.match(r"^[-*+] ", body))
                if is_bullet and body in seen:
                    continue
                if is_bullet:
                    seen.add(body)
                    after.append(body)
                chunks.append(body + "\n\n")
        before_count, after_count = Counter(bullets_before), Counter(after)
        expected = Counter(
            body
            for bodies in sections.values()
            for body in set(bodies)
            if re.match(r"^[-*+] ", body)
        )
        if after_count != expected or set(before_count) != set(after_count):
            raise RuntimeError("Log normalization changed bullet bodies; refusing write")
        result = "".join(chunks)
        if result != text and bundle.writable(path):
            print(
                f"log.md: {len(lines)} -> {len(result.splitlines())} lines; removed {sum(before_count.values()) - sum(after_count.values())} duplicate bullets",
                file=sys.stderr,
            )
            bundle.write(path, result)
    return findings


def names(bundle: Bundle, fix: bool) -> list[Finding]:
    """Flag external product names outside explicitly exempt reference pages."""
    words = [
        s.strip()
        for s in Path(__file__).with_name("third_party_names.txt").read_text().splitlines()
        if s.strip() and not s.startswith("#")
    ]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, words)) + r")(?!\w)", re.I)
    findings: list[Finding] = []
    for path, text in bundle.pages.items():
        if read_front_matter(text).get("convention-exempt") is True or path.name.endswith(
            ("-retirement.md", "-parity.md", "-mining.md", "-lessons.md")
        ):
            continue
        findings.extend(
            bundle.finding("NAMES", path, m.start(), "use a software role instead of: " + m[0])
            for m in pattern.finditer(_prose(text))
        )
    return findings


def pickup(bundle: Bundle, fix: bool) -> list[Finding]:
    """Require bounded, explicitly actionable resume bullets."""
    findings: list[Finding] = []
    for path, text in bundle.pages.items():
        prose = _prose(text)
        for section in re.finditer(r"(?m)^(#{1,6}) Where to pick this up\s*$", prose):
            end = re.search(r"(?m)^#{1,6} ", prose[section.end() :])
            stop = section.end() + end.start() if end else len(prose)
            bullets = list(
                re.finditer(r"(?m)^[ \t]*(?:[-*+] |\d+[.)] )(.+)$", prose[section.end() : stop])
            )
            if len(bullets) > 12:
                findings.append(
                    bundle.finding(
                        "PICKUP",
                        path,
                        section.start(),
                        f"resume section has {len(bullets)} bullets; maximum is 12",
                    )
                )
            for bullet in bullets:
                value = bullet[1].lstrip("* ")
                if not value.startswith(("Open:", "Blocked:", "Measure:", "Tried and reverted:")):
                    findings.append(
                        bundle.finding(
                            "PICKUP",
                            path,
                            section.end() + bullet.start(),
                            "resume bullet must start Open:, Blocked:, Measure: or Tried and reverted:",
                        )
                    )
    return findings


RULES: dict[str, Callable[[Bundle, bool], list[Finding]]] = {
    "FM": fm,
    "LINK": links,
    "WIKI": wiki,
    "PRD": prd,
    "KI": ki,
    "BOARD": board,
    "LOG": log,
    "NAMES": names,
    "PICKUP": pickup,
}


def scan(root: Path) -> list[Finding]:
    """Return all findings without modifying the bundle."""
    bundle = Bundle(Path(root))
    return [finding for rule in RULES.values() for finding in rule(bundle, False)]


def main(argv: list[str] | None = None) -> int:
    """Run selected rules, reporting remaining findings after optional repairs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("okf"))
    parser.add_argument("--only", help="comma-separated rule names")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv)
    selected = args.only.upper().split(",") if args.only else list(RULES)
    if any(name not in RULES for name in selected):
        parser.error("unknown rule; choose " + ",".join(RULES))
    if not args.root.is_dir():
        parser.error("bundle root must be an existing directory")
    try:
        bundle = Bundle(args.root)
        if args.fix:
            for name in selected:
                RULES[name](bundle, True)
            bundle = Bundle(args.root)
        findings = [finding for name in selected for finding in RULES[name](bundle, False)]
    except Exception as error:
        print(f"okf_lint: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f"{f.path}:{f.line}: {f.rule}: {f.msg}" + (" [fixable]" if f.fixable else ""))
    return (2 if args.fix else 1) if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
