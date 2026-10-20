"""Tests for ``build_tools.dev_utils.safe_commit``: a commit must never revert another agent's commit."""

from __future__ import annotations

import os
import subprocess

import pytest

from build_tools.dev_utils import safe_commit as sc
from build_tools.dev_utils import safe_edit as se


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                          capture_output=True, text=True).stdout


def _show(repo, rev, path):
    return _git(repo, "show", f"{rev}:{path}")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", "Agent")
    _git(r, "config", "user.email", "agent@example.org")
    _git(r, "config", "commit.gpgsign", "false")
    (r / "log.md").write_text("# Log\n\n- a\n")
    (r / "code.py").write_text("x = 1\n")
    (r / "data.bin").write_bytes(b"\x00\x01")
    _git(r, "add", "log.md", "code.py", "data.bin")
    _git(r, "commit", "-q", "-m", "init")
    monkeypatch.chdir(r)
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    return r


def test_commit_basic_no_trailer_and_index_synced(repo):
    (repo / "log.md").write_text("# Log\n\n- a\n- b\n")
    res = sc.commit(["Log: b", "Body line."], ["log.md"])
    assert _git(repo, "rev-parse", "HEAD").strip() == res.sha
    assert _git(repo, "log", "-1", "--format=%B").strip() == "Log: b\n\nBody line."
    assert _git(repo, "status", "--porcelain") == ""


def test_stale_blob_dropping_committed_line_is_refused(repo):
    # Agent A commits a bullet.
    (repo / "log.md").write_text("# Log\n\n- a\n- b\n")
    sc.commit("A: b", ["log.md"])
    # Agent B writes the file back from its stale buffer, plus its own bullet.
    (repo / "log.md").write_text("# Log\n\n- a\n- c\n")
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(sc.UnsafeCommitError, match=r"(?s)removes 1 line\(s\).*\| - b"):
        sc.commit("B: c", ["log.md"])
    assert _git(repo, "rev-parse", "HEAD") == head
    # With the base B started from (before A), the drop is still someone else's work.
    with pytest.raises(sc.UnsafeCommitError, match="after the base"):
        sc.commit("B: c", ["log.md"], base="HEAD~1")


def test_base_allows_own_edits_of_older_lines(repo):
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "code.py").write_text("x = 2\n")
    sc.commit("edit x", ["code.py"], base=base)
    assert _show(repo, "HEAD", "code.py") == "x = 2\n"


def test_concurrent_commit_triggers_retry_and_keeps_both(repo):
    (repo / "log.md").write_text("# Log\n\n- a\n- mine\n")
    other = repo / "other file.txt"

    def race(attempt):
        if attempt == 1:  # another agent lands a commit between build and update-ref
            other.write_text("theirs\n")
            sc.commit("Other agent", [str(other)])

    res = sc.commit("Mine", ["log.md"], _before_update_ref=race)
    assert res.attempts == 2
    assert _show(repo, "HEAD", "log.md").endswith("- mine\n")
    assert _show(repo, "HEAD", "other file.txt") == "theirs\n"
    assert _git(repo, "log", "--format=%s").split("\n")[:2] == ["Mine", "Other agent"]


def test_unlisted_deletion_refused_and_remove_allows_it(repo):
    os.unlink(repo / "data.bin")
    with pytest.raises(sc.UnsafeCommitError, match="--remove"):
        sc.commit("rm", ["data.bin"])
    # Unrelated deletions in the real index are never swept in.
    _git(repo, "rm", "-q", "--cached", "code.py")
    (repo / "log.md").write_text("# Log\n\n- a\n- b\n")
    res = sc.commit("log only", ["log.md"])
    assert _git(repo, "show", "--name-only", "--format=", res.sha).split() == ["log.md"]
    res = sc.commit("rm data", removes=["data.bin"])
    assert _git(repo, "show", "--name-status", "--format=", res.sha).split() == ["D", "data.bin"]
    with pytest.raises(sc.UnsafeCommitError, match="not tracked"):
        sc.commit("rm again", removes=["data.bin"])


def test_allow_drop_permits_intended_removal(repo):
    (repo / "log.md").write_text("# Log\n")
    with pytest.raises(sc.UnsafeCommitError):
        sc.commit("trim", ["log.md"])
    res = sc.commit("trim", ["log.md"], allow_drop=["log.md"])
    assert res.dropped == {"log.md": ["", "- a"]}
    assert _show(repo, "HEAD", "log.md") == "# Log\n"


def test_reordered_lines_are_not_a_drop(repo):
    (repo / "log.md").write_text("# Log\n\n- b\n- a\n")
    (repo / "log.md").write_text("- a\n# Log\n\n- new\n")
    sc.commit("reorder", ["log.md"])
    assert _show(repo, "HEAD", "log.md") == "- a\n# Log\n\n- new\n"


def test_binary_replacement_needs_allow_drop(repo):
    (repo / "data.bin").write_bytes(b"\x00\x02")
    with pytest.raises(sc.UnsafeCommitError, match="binary"):
        sc.commit("bin", ["data.bin"])
    sc.commit("bin", ["data.bin"], allow_drop=["data.bin"])


def test_empty_and_missing_refused(repo):
    with pytest.raises(sc.UnsafeCommitError, match="nothing to commit"):
        sc.commit("noop", ["log.md"])
    with pytest.raises(sc.UnsafeCommitError, match="does not exist"):
        sc.commit("x", ["nope.txt"])
    with pytest.raises(sc.UnsafeCommitError, match="no paths"):
        sc.commit("x", [])


def test_cli_paths_with_spaces(repo, capsys):
    d = repo / "dir with space"
    d.mkdir()
    (d / "a b.txt").write_text("1\n")
    (d / "c.txt").write_text("2\n")
    rc = se.main(["commit", "-m", "Spaces", "-m", "Body.",
                  "--file", "dir with space/a b.txt", "--file", str(d / "c.txt")])
    assert rc == 0
    names = _git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(names) == ["dir with space/a b.txt", "dir with space/c.txt"]
    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert sha in capsys.readouterr().out
    # A refusal is a non-zero exit with a message, not a traceback.
    (repo / "log.md").write_text("# Log\n")
    assert se.main(["commit", "-m", "bad", "--file", "log.md"]) == 1
    assert "refusing" in capsys.readouterr().err
