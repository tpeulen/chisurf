"""Safe edits of the shared files agents co-write: ``okf/log.md`` and the ``.ts`` catalogues.

Several agents work one tree, and a script that opens a shared file for writing
before it has read it (or that rewrites it from a stale or empty buffer) destroys
everyone else's uncommitted edits. Every edit to those files goes through here:

* :func:`edit_file` reads, applies ``fn(old) -> new`` and swaps the result in
  atomically; it refuses an empty or sharply shorter result and a file that
  changed under it.
* :func:`append_log_bullet` adds a bullet under the date's heading of
  ``okf/log.md`` and never creates a second heading for the same date.
* :func:`add_ts_entries` adds or updates messages in
  ``chisurf/gui/i18n/chisurf_<lang>.ts`` and leaves every other byte alone.

Command line::

    python -m build_tools.dev_utils.safe_edit log "bullet text" [--date YYYY-MM-DD]
    python -m build_tools.dev_utils.safe_edit log --dedupe
    python -m build_tools.dev_utils.safe_edit ts de --json entries.json

A ``"translation": ""`` entry adds the source as ``unfinished`` (catalogue
sources for new UI text, translated later) and never clears a translation.

Rule and rationale: ``okf/workflows/change-tracking.md`` ("Editing the shared files").
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[2]
LOG_PATH = REPO / "okf" / "log.md"
I18N_DIR = REPO / "chisurf" / "gui" / "i18n"

_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})[ \t]*$", re.MULTILINE)


class UnsafeEditError(RuntimeError):
    """Raised when an edit would empty, sharply shrink or race a shared file."""


def edit_file(
    path: str | os.PathLike[str],
    fn: Callable[[str], str],
    *,
    max_shrink: float = 0.2,
    allow_shrink: bool = False,
) -> bool:
    """Read ``path``, apply ``fn`` and replace the file atomically.

    The new content is written to a temporary file in the same directory and
    moved over the target with :func:`os.replace`, so a reader never sees a
    half-written file. A symlink is followed (``okf/agent-board.md`` is one).
    The file is re-read just before the swap; if another writer changed it in
    between, nothing is written.

    Parameters
    ----------
    path : str or path-like
        File to edit; it must exist (a missing file is never silently created).
    fn : callable
        ``fn(old_text) -> new_text``.
    max_shrink : float, optional
        Largest tolerated fractional loss of length, ``(old - new) / old``.
    allow_shrink : bool, optional
        Skip the empty/shrink check, for a deliberate deletion.

    Returns
    -------
    bool
        ``True`` if the file was rewritten, ``False`` if ``fn`` changed nothing.

    Raises
    ------
    UnsafeEditError
        If the result is empty, shorter than allowed, or the file changed
        while ``fn`` ran.
    """
    target = Path(path).resolve()
    old = target.read_bytes().decode("utf-8")
    new = fn(old)
    if new == old:
        return False
    if not allow_shrink:
        if not new.strip():
            raise UnsafeEditError(f"refusing to empty {target}")
        if old and (len(old) - len(new)) / len(old) > max_shrink:
            raise UnsafeEditError(
                f"refusing to shrink {target} from {len(old)} to {len(new)} characters "
                f"(more than {max_shrink:.0%}); pass allow_shrink=True if intended"
            )
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(new.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, target.stat().st_mode & 0o7777)
        if target.read_bytes().decode("utf-8") != old:
            raise UnsafeEditError(f"{target} changed while it was being edited; retry")
        os.replace(tmp_name, target)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return True


def _bullet_line(text: str) -> str:
    """Return ``text`` as one markdown bullet (``- `` prefix added if missing)."""
    text = text.strip()
    if not text:
        raise ValueError("empty log bullet")
    return text if text.startswith("- ") else "- " + text


def merge_duplicate_headings(text: str) -> str:
    """Merge repeated ``## YYYY-MM-DD`` sections of a log into the first of each date.

    Parameters
    ----------
    text : str
        Content of ``okf/log.md``.

    Returns
    -------
    str
        The log with each date heading once; bullets keep their order (first
        occurrence's bullets, then the later ones').
    """
    marks = list(_HEADING.finditer(text))
    first: dict[str, int] = {}
    bodies: dict[str, list[str]] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        bodies.setdefault(m.group(1), []).append(text[m.end() : end].strip("\n"))
        first.setdefault(m.group(1), i)
    if all(len(v) == 1 for v in bodies.values()):
        return text
    out = [text[: marks[0].start()]] if marks else [text]
    for i, m in enumerate(marks):
        if first[m.group(1)] != i:
            continue
        out.append(f"## {m.group(1)}\n\n" + "\n".join(b for b in bodies[m.group(1)] if b) + "\n\n")
    return "".join(out).rstrip("\n") + "\n"


def insert_log_bullet(text: str, bullet: str, date: str) -> str:
    """Return ``text`` with ``bullet`` added at the end of ``date``'s section.

    Parameters
    ----------
    text : str
        Content of the log.
    bullet : str
        Bullet text, with or without the leading ``- ``.
    date : str
        ``YYYY-MM-DD``. The heading is created (newest first, below the title)
        only when no section for that date exists; if several exist the first
        is used.

    Returns
    -------
    str
        The updated content.
    """
    line = _bullet_line(bullet)
    marks = list(_HEADING.finditer(text))
    for i, m in enumerate(marks):
        if m.group(1) == date:
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[m.end() : end].rstrip("\n") or "\n"
            rest = text[end:]
            return text[: m.end()] + body + "\n" + line + "\n" + ("\n" + rest if rest else "")
    if marks:
        at = marks[0].start()
        return text[:at] + f"## {date}\n\n{line}\n\n" + text[at:]
    return text.rstrip("\n") + f"\n\n## {date}\n\n{line}\n"


def append_log_bullet(
    text: str,
    date: str | None = None,
    *,
    path: str | os.PathLike[str] = LOG_PATH,
) -> bool:
    """Insert a dated bullet into ``okf/log.md`` under that date's heading.

    The heading is created once; an existing one is reused, never duplicated.

    Parameters
    ----------
    text : str
        The bullet (with or without ``- ``).
    date : str, optional
        ``YYYY-MM-DD``; today if omitted.
    path : str or path-like, optional
        Log file (default ``okf/log.md``); overridable for tests.

    Returns
    -------
    bool
        ``True`` if the file was written.
    """
    day = date or _dt.date.today().isoformat()
    return edit_file(path, lambda old: insert_log_bullet(old, text, day))


def dedupe_log_headings(path: str | os.PathLike[str] = LOG_PATH) -> bool:
    """Merge duplicate date headings of the log in place.

    Parameters
    ----------
    path : str or path-like, optional
        Log file (default ``okf/log.md``).

    Returns
    -------
    bool
        ``True`` if the file was written.
    """
    return edit_file(path, merge_duplicate_headings)


def _normalise_entries(
    entries: Iterable[Mapping[str, str] | tuple[str, str, str]] | Mapping[tuple[str, str], str],
) -> list[tuple[str, str, str]]:
    """Return ``(context, source, translation)`` triples from the accepted spellings."""
    if isinstance(entries, Mapping):
        return [(c, s, t) for (c, s), t in entries.items()]
    out = []
    for e in entries:
        if isinstance(e, Mapping):
            out.append((e["context"], e["source"], e["translation"]))
        else:
            c, s, t = e
            out.append((c, s, t))
    return out


def _put_ts_entry(text: str, context: str, source: str, translation: str) -> str:
    """Set one message in raw ``.ts`` text, touching only that message.

    An empty *translation* records the source only: a missing message is added
    ``unfinished`` (the runtime then shows the source text), and an existing
    message, finished or not, is left exactly as it is.
    """
    ctx_re = re.compile(
        r"(<context>\s*<name>" + re.escape(escape(context)) + r"</name>)(.*?)(\n[ \t]*</context>)",
        re.DOTALL,
    )
    src = f"<source>{escape(source)}</source>"
    new_tr = (
        f"<translation>{escape(translation)}</translation>"
        if translation
        else '<translation type="unfinished"/>'
    )
    ctx = ctx_re.search(text)
    if ctx is None:
        block = (
            f"    <context>\n        <name>{escape(context)}</name>\n"
            f"        <message>\n            {src}\n            {new_tr}\n        </message>\n"
            "    </context>\n"
        )
        end = text.rindex("</TS>")
        return text[:end] + block + text[end:]
    body = ctx.group(2)
    hits = 0

    def fix(m: re.Match[str]) -> str:
        nonlocal hits
        msg = m.group(0)
        if src not in msg:
            return msg
        if 'numerus="yes"' in msg.split(">", 1)[0]:
            raise ValueError(f"{source!r} is a plural message; not supported")
        hits += 1
        if not translation:
            return msg
        return re.sub(r"<translation\b[^>]*?(?:/>|>.*?</translation>)", lambda _m: new_tr, msg, flags=re.DOTALL)

    body = re.sub(r"<message\b.*?</message>", fix, body, flags=re.DOTALL)
    if not hits:
        indent = "        "
        body += f"\n{indent}<message>\n{indent}    {src}\n{indent}    {new_tr}\n{indent}</message>"
    return text[: ctx.start(2)] + body + text[ctx.end(2) :]


def add_ts_entries(
    lang: str,
    entries: Iterable[Mapping[str, str] | tuple[str, str, str]] | Mapping[tuple[str, str], str],
    *,
    directory: str | os.PathLike[str] = I18N_DIR,
) -> bool:
    """Add or update messages in ``chisurf_<lang>.ts``.

    Existing messages (matched by context and source) get a finished
    translation (an empty one leaves them untouched); missing ones are appended to their context (a missing context
    is appended at the end). Every untouched byte of the file stays as it was,
    and the result must still parse as XML before it replaces the file.

    Parameters
    ----------
    lang : str
        Language code, e.g. ``"de"``.
    entries : iterable or mapping
        ``(context, source, translation)`` triples, dicts with those keys, or a
        mapping ``{(context, source): translation}``.
    directory : str or path-like, optional
        Catalogue directory; overridable for tests.

    Returns
    -------
    bool
        ``True`` if the file was written.
    """
    triples = _normalise_entries(entries)
    path = Path(directory) / f"chisurf_{lang}.ts"

    def apply(old: str) -> str:
        new = old
        for c, s, t in triples:
            new = _put_ts_entry(new, c, s, t)
        ET.fromstring(new.encode("utf-8"))
        return new

    return edit_file(path, apply, max_shrink=0.0)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point (``log`` and ``ts`` sub-commands)."""
    ap = argparse.ArgumentParser(prog="safe_edit", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("log", help="append a bullet to okf/log.md under its date heading")
    lg.add_argument("text", nargs="?", help="bullet text")
    lg.add_argument("--date", help="YYYY-MM-DD (default today)")
    lg.add_argument("--dedupe", action="store_true", help="merge duplicate date headings")
    ts = sub.add_parser("ts", help="add/update messages in a .ts catalogue")
    ts.add_argument("lang")
    ts.add_argument("--json", required=True, help="file with [{context, source, translation}]")
    args = ap.parse_args(argv)
    if args.cmd == "log":
        if not args.text and not args.dedupe:
            ap.error("give bullet text or --dedupe")
        changed = dedupe_log_headings() if args.dedupe else False
        if args.text:
            changed = append_log_bullet(args.text, args.date) or changed
    else:
        changed = add_ts_entries(args.lang, json.loads(Path(args.json).read_text("utf-8")))
    print("written" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
