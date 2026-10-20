"""Commit named files in the shared working tree without reverting anyone else's commits.

Many agents commit to one checkout at the same time. The hand-rolled recipe
(temporary ``GIT_INDEX_FILE``, ``read-tree``, ``update-index``, ``commit-tree``,
``update-ref``) failed in four ways that each landed a commit which silently
undid someone else's work:

* the temporary index was read from a HEAD that had moved by the time the
  commit was written, so the new tree reverted every file committed meanwhile;
* the blob was taken from a working-tree file that lacked lines another agent had
  just committed (a stale buffer), so the commit deleted those lines;
* the index held deletions of unrelated paths, which went in unnoticed;
* the path list went through shell word splitting, so the commit held one file
  instead of five.

:func:`commit` makes those failures refusals:

* the temporary index is built from HEAD *at commit time* and the ref is moved
  with a compare-and-swap (``git update-ref HEAD new old``); a HEAD that moved in
  between makes it rebuild from the new HEAD and check again;
* a staged file that **loses lines HEAD has** (moved lines do not count) is refused unless
  the path is given with ``--allow-drop`` (or, with ``--base``, unless none of
  the removed lines was added after the commit the caller started from);
* a path deleted in the commit must be named with ``--remove``; a missing file
  given with ``--file`` is refused;
* an empty commit, and any change to a path that was not named, are refused;
* no trailer is ever added: the message is exactly the ``-m`` paragraphs.

After the commit the real index entries of exactly those paths are set to the
committed blobs, so ``git status`` does not show them as staged reverts.

Command line (paths are separate arguments, so no word-splitting trap)::

    python -m build_tools.dev_utils.safe_edit commit -m "subject" [-m "body"] \\
        --file PATH [--file PATH ...] [--remove PATH ...] [--allow-drop PATH ...] \\
        [--base REV] [--dry-run]

Rule and rationale: ``okf/workflows/change-tracking.md`` ("Committing in the
shared tree").
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_NULL_SHA = "0" * 40


class UnsafeCommitError(RuntimeError):
    """Raised when a commit would revert, delete or sweep work it was not asked to."""


@dataclass
class CommitResult:
    """Outcome of :func:`commit`.

    Attributes
    ----------
    sha : str
        The new commit (empty on a dry run).
    parent : str
        The HEAD it was built on.
    attempts : int
        Number of builds; above one means HEAD moved and the commit was rebuilt.
    dropped : dict
        ``{path: [removed lines]}`` for paths allowed to drop lines.
    """

    sha: str
    parent: str
    attempts: int
    dropped: dict[str, list[str]] = field(default_factory=dict)


def _env(index: str | None = None) -> dict[str, str]:
    """Return the environment for git: the caller's ``GIT_INDEX_FILE`` never leaks in."""
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    if index is not None:
        env["GIT_INDEX_FILE"] = index
    env["LC_ALL"] = "C"
    return env


def _git(
    repo: Path,
    *args: str,
    index: str | None = None,
    stdin: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run ``git args`` in ``repo`` and return the completed process (bytes output)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=_env(index),
        input=stdin,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise UnsafeCommitError(
            f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc


def _out(repo: Path, *args: str, index: str | None = None) -> str:
    """Return the stripped stdout of ``git args``."""
    return _git(repo, *args, index=index).stdout.decode("utf-8", "replace").strip()


def repo_root(start: str | os.PathLike[str] | None = None) -> Path:
    """Return the top-level directory of the repository containing ``start`` (default cwd)."""
    here = Path(start or os.getcwd())
    return Path(_out(here, "rev-parse", "--show-toplevel")).resolve()


def _repo_path(repo: Path, path: str | os.PathLike[str]) -> str:
    """Return ``path`` (absolute, or relative to the cwd) as a repository-relative POSIX path.

    Only the parent directory is resolved, so a tracked symlink is committed as
    the link, not as its target.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
    parent = p.parent.resolve()
    try:
        rel = (parent / p.name).relative_to(repo)
    except ValueError:
        raise UnsafeCommitError(f"{path} is outside the repository {repo}") from None
    s = rel.as_posix()
    if s in ("", "."):
        raise UnsafeCommitError(f"{path} is the repository root, not a file")
    return s


def _removed_lines(repo: Path, index: str, path: str) -> list[str] | None:
    """Return the lines of HEAD's ``path`` that the staged content no longer has.

    Lines are compared as a multiset, so a line that only moved (a reordered log
    section) is not lost; a line HEAD has *n* times and the new content fewer
    times is. Returns ``None`` for a binary change, which cannot be checked.
    """
    num = _git(repo, "diff", "--cached", "--numstat", "HEAD", "--", path, index=index).stdout
    if num.startswith(b"-\t-\t"):
        return None
    old = _git(repo, "show", f"HEAD:{path}").stdout.decode("utf-8", "replace").splitlines()
    new = _git(repo, "show", f":{path}", index=index).stdout.decode("utf-8", "replace")
    left = Counter(old) - Counter(new.splitlines())
    lost = []
    for ln in old:
        if left[ln] > 0:
            left[ln] -= 1
            lost.append(ln)
    return lost


def _diff_lines(patch: bytes, sign: str) -> list[str]:
    """Return the ``sign`` (``"+"`` or ``"-"``) content lines of a unified diff."""
    out = []
    for raw in patch.decode("utf-8", "replace").splitlines():
        if raw.startswith(sign) and not raw.startswith(sign * 3 + " "):
            out.append(raw[1:])
    return out


def _lines_added_since(repo: Path, base: str, head: str, path: str) -> Counter[str]:
    """Return the lines added to ``path`` between ``base`` and ``head`` (a multiset)."""
    patch = _git(
        repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
        base, head, "--", path,
    ).stdout
    return Counter(_diff_lines(patch, "+"))


def _changed_paths(repo: Path, index: str) -> dict[str, str]:
    """Return ``{path: status letter}`` of the temporary index against HEAD."""
    raw = _git(repo, "diff", "--cached", "--name-status", "-z", "--no-renames", "HEAD",
               index=index).stdout.decode("utf-8", "surrogateescape")
    parts = [p for p in raw.split("\0") if p]
    return {parts[i + 1]: parts[i] for i in range(0, len(parts) - 1, 2)}


def _build(
    repo: Path,
    head: str,
    files: Sequence[str],
    removes: Sequence[str],
    allow_drop: set[str],
    base: str | None,
    index: str,
) -> dict[str, list[str]]:
    """Fill ``index`` from ``head`` plus the named changes and check every guard.

    Returns
    -------
    dict
        ``{path: removed lines}`` for allowed drops (for the report).
    """
    _git(repo, "read-tree", head, index=index)
    if files:
        _git(repo, "update-index", "--add", "--remove", "-z", "--stdin", index=index,
             stdin=b"".join(f.encode("utf-8", "surrogateescape") + b"\0" for f in files))
    if removes:
        _git(repo, "update-index", "--force-remove", "-z", "--stdin", index=index,
             stdin=b"".join(f.encode("utf-8", "surrogateescape") + b"\0" for f in removes))
    changed = _changed_paths(repo, index)
    if not changed:
        raise UnsafeCommitError("nothing to commit: every named path matches HEAD")
    named = set(files) | set(removes)
    stray = sorted(set(changed) - named)
    if stray:
        raise UnsafeCommitError(f"the commit would touch paths that were not named: {stray}")
    problems = []
    dropped: dict[str, list[str]] = {}
    for path, status in sorted(changed.items()):
        if status == "D":
            if path not in removes:
                problems.append(
                    f"{path}: the commit deletes it, but it was not given with --remove "
                    "(it is missing from the working tree)"
                )
            continue
        if status != "M":
            continue
        lost = _removed_lines(repo, index, path)
        if lost is None:
            if path not in allow_drop:
                problems.append(
                    f"{path}: binary file replaced; its old content cannot be checked "
                    "line by line - give --allow-drop if replacing it is intended"
                )
            continue
        if not lost:
            continue
        if path in allow_drop:
            dropped[path] = lost
            continue
        if base is not None:
            newer = _lines_added_since(repo, base, head, path)
            lost_newer = [ln for ln in lost if newer[ln] > 0]
            if not lost_newer:
                dropped[path] = lost
                continue
            lost = lost_newer
            why = f"lines committed after the base {base[:10]}"
        else:
            why = "lines that are in HEAD"
        shown = "\n".join(f"      | {ln}" for ln in lost[:8])
        more = f"\n      ... and {len(lost) - 8} more" if len(lost) > 8 else ""
        problems.append(
            f"{path}: the working-tree file removes {len(lost)} line(s): {why}:\n{shown}{more}\n"
            "    If those lines were committed by another agent, your copy is stale: merge "
            "them back into the file. If you removed them on purpose, give "
            f"--allow-drop {path}"
            + ("" if base else " (or --base <the HEAD you started from>)")
            + "."
        )
    if problems:
        raise UnsafeCommitError("refusing to commit:\n  " + "\n  ".join(problems))
    return dropped


def _sync_real_index(repo: Path, sha: str, files: Sequence[str], removes: Sequence[str]) -> None:
    """Point the real index entries of the committed paths at the committed blobs."""
    paths = list(dict.fromkeys([*files, *removes]))
    listing = _git(repo, "ls-tree", "-z", sha, "--", *paths).stdout
    present: dict[str, bytes] = {}
    for rec in listing.split(b"\0"):
        if not rec:
            continue
        meta, name = rec.split(b"\t", 1)
        mode, _type, blob = meta.split(b" ")
        present[name.decode("utf-8", "surrogateescape")] = mode + b" " + blob
    lines = []
    for p in paths:
        enc = p.encode("utf-8", "surrogateescape")
        info = present.get(p, b"0 " + _NULL_SHA.encode())
        lines.append(info + b"\t" + enc + b"\0")
    proc = _git(repo, "update-index", "-z", "--index-info", stdin=b"".join(lines), check=False)
    if proc.returncode != 0:
        print(
            "warning: committed, but the real index could not be synced "
            f"({proc.stderr.decode('utf-8', 'replace').strip()}); "
            "`git status` may show those paths as staged changes",
            file=sys.stderr,
        )


def commit(
    message: str | Sequence[str],
    files: Iterable[str | os.PathLike[str]] = (),
    *,
    removes: Iterable[str | os.PathLike[str]] = (),
    allow_drop: Iterable[str | os.PathLike[str]] = (),
    base: str | None = None,
    repo: str | os.PathLike[str] | None = None,
    retries: int = 5,
    dry_run: bool = False,
    _before_update_ref: Callable[[int], None] | None = None,
) -> CommitResult:
    """Commit the working-tree content of ``files`` (and the deletion of ``removes``) on HEAD.

    Parameters
    ----------
    message : str or sequence of str
        Subject, or ``[subject, body, ...]`` paragraphs joined by blank lines.
        Nothing is appended (no trailers).
    files : iterable of path
        Paths whose working-tree content is committed (absolute or cwd-relative).
    removes : iterable of path
        Paths deleted by the commit; each must be tracked in HEAD.
    allow_drop : iterable of path
        Paths allowed to lose lines that HEAD has.
    base : str, optional
        The commit the caller started from. With it, a removed line is refused
        only if it was added between ``base`` and HEAD (someone else's newer
        work); without it, any removed line is refused.
    repo : path, optional
        Any directory inside the repository (default cwd).
    retries : int, optional
        Rebuilds allowed when HEAD moves between build and ``update-ref``.
    dry_run : bool, optional
        Build and check, but do not commit.
    _before_update_ref : callable, optional
        Test hook, called with the attempt number just before the ref update.

    Returns
    -------
    CommitResult

    Raises
    ------
    UnsafeCommitError
        If a guard refuses, or HEAD kept moving for ``retries`` attempts.
    """
    root = repo_root(repo)
    paragraphs = [message] if isinstance(message, str) else list(message)
    paragraphs = [p.strip() for p in paragraphs if p and p.strip()]
    if not paragraphs:
        raise UnsafeCommitError("empty commit message")
    text = "\n\n".join(paragraphs) + "\n"
    files_r = list(dict.fromkeys(_repo_path(root, f) for f in files))
    removes_r = list(dict.fromkeys(_repo_path(root, f) for f in removes))
    drops = {_repo_path(root, f) for f in allow_drop}
    if not files_r and not removes_r:
        raise UnsafeCommitError("no paths given (--file / --remove)")
    both = sorted(set(files_r) & set(removes_r))
    if both:
        raise UnsafeCommitError(f"paths given with both --file and --remove: {both}")
    for f in files_r:
        p = root / f
        if p.is_dir() and not p.is_symlink():
            raise UnsafeCommitError(f"{f} is a directory; name the files")
        if not p.exists() and not p.is_symlink():
            raise UnsafeCommitError(f"{f} does not exist; to delete it from the commit use --remove")
    if base is not None:
        base = _out(root, "rev-parse", "--verify", base + "^{commit}")
    git_dir = Path(_out(root, "rev-parse", "--absolute-git-dir"))

    for attempt in range(1, retries + 1):
        head = _out(root, "rev-parse", "--verify", "HEAD")
        for r in removes_r:
            if _git(root, "cat-file", "-e", f"{head}:{r}", check=False).returncode != 0:
                raise UnsafeCommitError(f"{r} is not tracked in HEAD; nothing to --remove")
        fd, index = tempfile.mkstemp(prefix="safe_commit.", suffix=".index", dir=git_dir)
        os.close(fd)
        os.unlink(index)  # git wants to create the index itself
        try:
            dropped = _build(root, head, files_r, removes_r, drops, base, index)
            if dry_run:
                print(_out(root, "diff", "--cached", "--stat", "HEAD", index=index))
                return CommitResult("", head, attempt, dropped)
            tree = _out(root, "write-tree", index=index)
        finally:
            for leftover in (index, index + ".lock"):
                if os.path.exists(leftover):
                    os.unlink(leftover)
        sha = _git(root, "commit-tree", tree, "-p", head, "-F", "-",
                   stdin=text.encode("utf-8")).stdout.decode().strip()
        if _before_update_ref is not None:
            _before_update_ref(attempt)
        subject = paragraphs[0].splitlines()[0]
        cas = _git(root, "update-ref", "-m", f"safe_commit: {subject}", "HEAD", sha, head,
                   check=False)
        if cas.returncode == 0:
            _sync_real_index(root, sha, files_r, removes_r)
            return CommitResult(sha, head, attempt, dropped)
        print(f"HEAD moved during attempt {attempt}; rebuilding on the new HEAD", file=sys.stderr)
    raise UnsafeCommitError(f"HEAD kept moving; gave up after {retries} attempts")


def add_commit_parser(sub) -> None:
    """Register the ``commit`` sub-command on an argparse sub-parser group."""
    cp = sub.add_parser(
        "commit",
        help="commit named files on the current HEAD without reverting others' commits",
        description=__doc__.split("\n\n")[0],
    )
    cp.add_argument("-m", "--message", action="append", required=True,
                    help="subject; repeat for body paragraphs")
    cp.add_argument("--file", action="append", default=[], metavar="PATH",
                    help="commit this path's working-tree content (repeat per path)")
    cp.add_argument("--remove", action="append", default=[], metavar="PATH",
                    help="delete this tracked path in the commit (repeat per path)")
    cp.add_argument("--allow-drop", action="append", default=[], metavar="PATH",
                    help="allow this path to lose lines HEAD has - only for a removal you made "
                         "on purpose; a refusal usually means your copy is stale")
    cp.add_argument("--base", metavar="REV",
                    help="the HEAD you started from: then only removing lines committed after "
                         "it is refused")
    cp.add_argument("--retries", type=int, default=5)
    cp.add_argument("--dry-run", action="store_true", help="check and show the stat only")


def run_commit_args(args) -> int:
    """Execute a parsed ``commit`` sub-command; return the process exit code."""
    try:
        res = commit(
            args.message, args.file, removes=args.remove, allow_drop=args.allow_drop,
            base=args.base, retries=args.retries, dry_run=args.dry_run,
        )
    except UnsafeCommitError as exc:
        print(f"safe_commit: {exc}", file=sys.stderr)
        return 1
    for path, lines in res.dropped.items():
        print(f"note: {path} drops {len(lines)} line(s) (allowed)", file=sys.stderr)
    if args.dry_run:
        print(f"dry run: checks passed on {res.parent[:10]}")
        return 0
    root = repo_root()
    print(res.sha)
    sys.stdout.flush()
    subprocess.run(["git", "show", "--stat", "--format=%H%n%an%n%n%B", res.sha],
                   cwd=root, env=_env())
    return 0
