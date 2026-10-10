"""Exercise bundle validation against independent, isolated Git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from build_tools.okf import okf_lint


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """Create a bundle whose discovery obeys real Git ignore rules."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    root = tmp_path / "okf"
    root.mkdir()
    return root


def write(root: Path, name: str, text: str) -> Path:
    """Write a fixture while preserving exactly the supplied text."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def page(body: str, extra: str = "") -> str:
    """Return valid concept metadata followed by the supplied body."""
    return (
        "---\ntype: Reference\ntitle: Example\n"
        "description: A meaningful fixture description.\n"
        f"{extra}---\n\n{body}"
    )


def findings(root: Path, rule: str) -> list:
    """Select one rule without hiding other rules from the scanner."""
    return [finding for finding in okf_lint.scan(root) if finding.rule == rule]


def fix(root: Path, rule: str) -> int:
    """Run only a selected mechanical repair on the fixture repository."""
    return okf_lint.main(["--root", str(root), "--only", rule, "--fix"])


def commit_fixture(root: Path, path: Path) -> None:
    """Give protected shared ledgers a clean, explicitly owned Git baseline."""
    subprocess.run(["git", "-C", str(root.parent), "add", str(path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root.parent),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "Record isolated fixture",
        ],
        check=True,
    )


def test_frontmatter_stub_is_written_and_idempotent(bundle: Path) -> None:
    """Missing metadata is repaired without replacing substantive prose."""
    body = "# Meaningful heading\n\nA useful description of this particular report.\n"
    path = write(bundle, "plugins/emtk-ports/example/REPORT.md", body)
    assert findings(bundle, "FM")
    assert fix(bundle, "FM") == 0
    repaired = path.read_text()
    assert "type: Report" in repaired
    assert "Meaningful heading" in repaired
    assert repaired.endswith(body)
    assert not findings(bundle, "FM")
    assert fix(bundle, "FM") == 0
    assert path.read_text() == repaired


def test_frontmatter_requires_nonempty_fields_and_respects_reserved_names(bundle: Path) -> None:
    """Only explicitly reserved page names may omit concept metadata."""
    for name in ("index.md", "log.md", "agent-board.md"):
        write(bundle, name, "# Placeholder\n")
    write(bundle, "references/empty.md", page("# Empty\n").replace("title: Example", "title: ''"))
    result = findings(bundle, "FM")
    assert result
    assert all(str(item.path).endswith("empty.md") for item in result)


def test_bundle_root_link_resolves_and_absolute_link_is_rewritten(bundle: Path) -> None:
    """Bundle-root links and filesystem links have distinct resolution bases."""
    write(bundle, "references/target.md", page("# Target\n"))
    source = write(
        bundle, "plans/source.md", page("# Source\n\n[Good](/references/target.md#anchor)\n")
    )
    assert not findings(bundle, "LINK")
    target = write(bundle.parent, "docs/guide.md", "# Guide\n")
    source.write_text(source.read_text() + f"[Absolute]({target})\n[Repo](/docs/guide.md)\n")
    assert len(findings(bundle, "LINK")) == 2
    assert fix(bundle, "LINK") == 0
    text = source.read_text()
    assert "[Good](/references/target.md#anchor)" in text
    assert text.count("../../docs/guide.md") == 2
    assert not findings(bundle, "LINK")


def test_missing_link_is_unfixable_and_external_links_are_ignored(bundle: Path) -> None:
    """A repair cannot silently erase a missing local target."""
    path = write(
        bundle,
        "references/source.md",
        page(
            "# Links\n\n[Missing](lost.md) [Site](https://example.org/a) "
            "[Mail](mailto:example@example.org) [Here](#links)\n"
        ),
    )
    before = path.read_bytes()
    assert len(findings(bundle, "LINK")) == 1
    assert okf_lint.main(["--root", str(bundle), "--only", "LINK"]) == 1
    assert fix(bundle, "LINK") == 2
    assert path.read_bytes() == before


def test_wikilink_inside_code_is_not_a_finding(bundle: Path) -> None:
    """Inline, backtick and tilde fenced examples are excluded from prose rules."""
    path = write(
        bundle,
        "references/code.md",
        page(
            "# Examples\n\n`[[inline]] [bad](missing.md) PyMOL`\n\n"
            "```text\n[[fenced]] [bad](missing.md) PyMOL\n```\n\n"
            "~~~text\n[[tilde]] [bad](missing.md) PyMOL\n~~~\n\n"
            "``a ` [[nested]]``\n"
        ),
    )
    for rule in ("WIKI", "LINK", "NAMES"):
        assert not findings(bundle, rule)
    path.write_text(path.read_text() + "\n[[real link]]\n")
    result = findings(bundle, "WIKI")
    assert len(result) == 1
    assert result[0].line == len(path.read_text().splitlines())


def test_prd_glyph_follows_status_and_unindexed_prd_is_appended(bundle: Path) -> None:
    """Status aliases, glyphs and missing index entries are repaired together."""
    first = write(bundle, "prds/prd-1.md", page("# First\n", "status: Complete\n"))
    write(bundle, "prds/prd-2.md", page("# Second\n", "status: planned\n"))
    index = write(bundle, "prds/index.md", "# PRDs\n\n* 🚧 [First](prd-1.md)\n")
    assert findings(bundle, "PRD")
    assert fix(bundle, "PRD") == 0
    assert "status: done" in first.read_text()
    assert "* ✅ [First](prd-1.md)" in index.read_text()
    assert "prd-2.md" in index.read_text()
    assert "📋" in index.read_text()
    before = index.read_bytes()
    assert fix(bundle, "PRD") == 0
    assert index.read_bytes() == before


def test_unknown_prd_status_is_not_guessed(bundle: Path) -> None:
    """Unknown statuses remain visible for an owner to decide."""
    write(bundle, "prds/prd-1.md", page("# First\n", "status: uncertain\n"))
    write(bundle, "prds/index.md", "# PRDs\n\n* 🚧 [First](prd-1.md)\n")
    assert findings(bundle, "PRD")
    assert fix(bundle, "PRD") == 2


def test_known_issue_duplicates_are_dropped_only_when_identical(bundle: Path) -> None:
    """Deduplication preserves conflicting records sharing the same title."""
    block = "## Same issue\nstatus: open\n\nFound 2026-10-01. Original evidence.\n\n"
    other = block.replace("Original evidence", "Different evidence")
    path = write(
        bundle, "references/known-issues.md", page("# Known issues\n\n" + block + block + other)
    )
    commit_fixture(bundle, path)
    assert findings(bundle, "KI")
    assert fix(bundle, "KI") == 2
    text = path.read_text()
    assert text.count("## Same issue") == 2
    assert text.count("Original evidence") == 1
    assert "Different evidence" in text
    before = path.read_bytes()
    commit_fixture(bundle, path)
    assert fix(bundle, "KI") == 2
    assert path.read_bytes() == before


def test_known_issue_status_line_and_order(bundle: Path) -> None:
    """Explicit open statuses override titles and dated closures sort first."""
    path = write(
        bundle,
        "references/known-issues.md",
        page(
            "# Known issues\n\n## Old issue (2026-09-01)\n\nOld evidence.\n\n"
            "## ✅ FIXED New issue (2026-10-01)\n\nNew evidence.\n\n"
            "## Partly fixed (2026-09-20)\nstatus: open\n\nRemaining work.\n"
        ),
    )
    commit_fixture(bundle, path)
    assert findings(bundle, "KI")
    assert fix(bundle, "KI") == 0
    text = path.read_text()
    assert "status: resolved 2026-10-01" in text
    assert text.index("New issue") < text.index("Partly fixed") < text.index("Old issue")
    assert "## Partly fixed (2026-09-20)\nstatus: open" in text
    assert "Old evidence." in text and "Remaining work." in text


def test_board_done_entries_move_to_resolved_and_duplicate_id_is_a_finding(bundle: Path) -> None:
    """Completed blocks move intact while duplicate ticket IDs remain failures."""
    path = write(
        bundle,
        "agent-board.md",
        "# Board\n\n## Open\n\n"
        "- **T-1** ✅ Done\n  Evidence: retained.\n\n"
        "## Active\n\n- **T-2** 🔄 Running\n  Touching: example.py\n\n"
        "## Resolved\n\n- **T-2** ✅ Earlier\n",
    )
    assert findings(bundle, "BOARD")
    assert fix(bundle, "BOARD") == 2
    text = path.read_text()
    assert text.index("## Resolved") < text.index("- **T-1**")
    assert "Evidence: retained." in text
    assert text.count("**T-2**") == 2
    assert findings(bundle, "BOARD")


def test_board_active_ticket_requires_touching_scope(bundle: Path) -> None:
    """Every active ticket advertises its owned paths."""
    write(bundle, "agent-board.md", "# Board\n\n## Active\n\n- **T-1** 🔄 Running\n")
    assert findings(bundle, "BOARD")
    assert fix(bundle, "BOARD") == 2


def test_log_tail_bullets_are_folded_into_date_sections_and_nothing_is_lost(bundle: Path) -> None:
    """Normalisation preserves multiline evidence and removes only exact repeats."""
    path = write(
        bundle,
        "log.md",
        "# Log\n\n"
        "- **2026-10-03** — Tail evidence.\n  Continued evidence.\n\n"
        "## 2026-10-01\n\n- First evidence.\n\n"
        "## 2026-10-02 (evening)\n\n- Second evidence.\n\n"
        "## 2026-10-02\n\n- Second evidence.\n\n"
        "- 2026-10-04: Final tail evidence.\n",
    )
    commit_fixture(bundle, path)
    assert findings(bundle, "LOG")
    assert fix(bundle, "LOG") == 0
    text = path.read_text()
    assert text.index("## 2026-10-04") < text.index("## 2026-10-03")
    assert text.index("## 2026-10-03") < text.index("## 2026-10-02") < text.index("## 2026-10-01")
    for evidence in (
        "Tail evidence.",
        "Continued evidence.",
        "First evidence.",
        "Second evidence.",
        "Final tail evidence.",
    ):
        assert text.count(evidence) == 1
    assert "(evening)" not in text
    before = path.read_bytes()
    commit_fixture(bundle, path)
    assert fix(bundle, "LOG") == 0
    assert path.read_bytes() == before


def test_convention_exempt_key_silences_names_rule(bundle: Path) -> None:
    """Names are whole prose words and explicit exemptions are respected."""
    path = write(bundle, "references/ordinary.md", page("# Names\n\nPyMOL and Orange3.\n"))
    assert findings(bundle, "NAMES")
    path.write_text(page("# Names\n\nPyMOL and Orange3.\n", "convention-exempt: true\n"))
    write(bundle, "references/example-parity.md", page("# Parity\n\nPyMOL.\n"))
    assert not findings(bundle, "NAMES")


def test_names_ignore_link_destinations_but_not_link_text(bundle: Path) -> None:
    """A file name in a link target is a path; the visible link text is still prose."""
    write(bundle, "references/a.md", page("# A\n\nSee [the parity index](../plugins/pymol-parity.md).\n"))
    assert not findings(bundle, "NAMES")
    write(bundle, "references/b.md", page("# B\n\nSee [PyMOL parity](../plugins/pymol-parity.md).\n"))
    assert findings(bundle, "NAMES")


def test_pickup_requires_action_prefixes_and_bounded_list(bundle: Path) -> None:
    """Resume sections reject history and more than twelve actionable bullets."""
    path = write(
        bundle,
        "references/resume.md",
        page("# Example\n\n# Where to pick this up\n\n- Historical receipt.\n"),
    )
    assert findings(bundle, "PICKUP")
    path.write_text(
        page("# Example\n\n# Where to pick this up\n\n" + "- Open: Check the fixture.\n" * 13)
    )
    assert findings(bundle, "PICKUP")
    path.write_text(
        page(
            "# Example\n\n# Where to pick this up\n\n"
            "- Open: Verify values.\n- Blocked: Need data.\n"
            "- Measure: Count outputs.\n- Tried and reverted: Scaling lost units.\n"
            "\n# History\n\n- Earlier receipt.\n"
        )
    )
    assert not findings(bundle, "PICKUP")


def test_discovery_includes_untracked_but_excludes_ignored_markdown(bundle: Path) -> None:
    """Git discovery includes new source without traversing ignored artefacts."""
    write(bundle.parent, ".gitignore", "okf/ignored/\n")
    write(bundle, "ignored/bad.md", "# Ignored\n")
    tracked = write(bundle, "references/tracked.md", "# Tracked\n")
    subprocess.run(["git", "-C", str(bundle.parent), "add", str(tracked)], check=True)
    write(bundle, "references/untracked.md", "# Untracked\n")
    result = findings(bundle, "FM")
    assert {Path(item.path).name for item in result} == {"tracked.md", "untracked.md"}


def test_symlink_board_is_read_but_never_mutated_across_repositories(
    bundle: Path, tmp_path: Path
) -> None:
    """A linked coordination board is validated without editing its owning repo."""
    outside = tmp_path / "other-repo" / "board.md"
    outside.parent.mkdir()
    subprocess.run(["git", "init", "-q", str(outside.parent)], check=True)
    outside.write_text("# Board\n\n## Open\n\n- **T-1** ✅ Done\n\n## Resolved\n")
    (bundle / "agent-board.md").symlink_to(outside)
    original = outside.read_bytes()
    assert findings(bundle, "BOARD")
    assert fix(bundle, "BOARD") == 2
    assert outside.read_bytes() == original
    assert (bundle / "agent-board.md").is_symlink()


def test_repo_bundle_has_no_new_or_stale_findings() -> None:
    """Keep existing W0b debt explicit while rejecting new or stale records."""
    from build_tools.okf import baseline

    repo = Path(__file__).resolve().parent.parent
    assert (
        baseline.main(
            [
                "--root",
                str(repo / "okf"),
                "--baseline",
                str(repo / "test" / "okf_bundle_baseline.json"),
            ]
        )
        == 0
    )


@pytest.mark.parametrize("name,rule", [("log.md", "LOG"), ("references/known-issues.md", "KI")])
def test_dirty_shared_ledgers_are_not_rewritten(bundle: Path, name: str, rule: str) -> None:
    """Mechanical fixes must preserve another writer's pending ledger edits."""
    path = write(bundle, name, "# Ledger\n")
    commit_fixture(bundle, path)
    body = (
        "# Ledger\n\n- **2026-10-01** — Pending work.\n"
        if rule == "LOG"
        else page("# Ledger\n\n## Pending issue (2026-10-01)\n\nPending work.\n")
    )
    path.write_text(body)
    assert findings(bundle, rule)
    assert fix(bundle, rule) == 2
    assert path.read_text() == body


def test_board_repeated_resolved_sections_do_not_duplicate_moved_tickets(bundle: Path) -> None:
    """An imperfect board cannot multiply evidence during a mechanical move."""
    path = write(
        bundle,
        "agent-board.md",
        "# Board\n\n## Open\n\n"
        "- **T-1** ✅ Done\n  Evidence: retained once.\n\n"
        "## Resolved\n\n- **T-2** ✅ Earlier\n\n"
        "## Resolved\n\n- **T-3** ✅ Oldest\n",
    )
    assert fix(bundle, "BOARD") == 0
    text = path.read_text()
    assert text.count("**T-1**") == 1
    assert text.count("Evidence: retained once.") == 1
    assert text.index("## Resolved") < text.index("**T-1**")


@pytest.mark.parametrize("field", ["type", "title", "description"])
@pytest.mark.parametrize("value", ["[not, text]", "42", "true", "{key: value}"])
def test_frontmatter_rejects_nonstring_fields(bundle: Path, field: str, value: str) -> None:
    """Required concept fields are text, not merely truthy YAML values."""
    values = {"type": "Reference", "title": "Example", "description": "Useful description."}
    values[field] = value
    metadata = "\n".join(f"{key}: {item}" for key, item in values.items())
    write(bundle, "references/types.md", f"---\n{metadata}\n---\n\n# Example\n")
    assert findings(bundle, "FM")


@pytest.mark.parametrize("existing_file", [False, True])
def test_scan_rejects_absent_or_nondirectory_root(tmp_path: Path, existing_file: bool) -> None:
    """A mistaken bundle root cannot yield a false clean result."""
    root = tmp_path / "not-a-bundle"
    if existing_file:
        root.write_text("A file is not a bundle directory.\n")
    with pytest.raises(ValueError):
        okf_lint.scan(root)


def test_log_same_bullet_on_different_days_is_preserved(bundle: Path) -> None:
    """Identical evidence on distinct dates represents two separate events."""
    path = write(
        bundle,
        "log.md",
        "# Log\n\n"
        "## 2026-10-01\n\n- Repeated measurement.\n\n"
        "## 2026-10-02\n\n- Repeated measurement.\n\n"
        "- Repeated measurement.\n",
    )
    commit_fixture(bundle, path)
    assert findings(bundle, "LOG")
    assert fix(bundle, "LOG") == 0
    text = path.read_text()
    assert text.count("- Repeated measurement.") == 2
    newest, oldest = text.split("## 2026-10-01")
    assert "## 2026-10-02" in newest
    assert newest.count("- Repeated measurement.") == 1
    assert oldest.count("- Repeated measurement.") == 1


def test_frontmatter_repair_preserves_typed_metadata(bundle: Path) -> None:
    """Filling a missing title must retain boolean and structured author data."""
    from build_tools.docs.okf import read_front_matter

    body = "# A proper title\n\nScientific evidence remains untouched.\n"
    path = write(
        bundle,
        "references/metadata.md",
        "---\n"
        "type: Reference\ndescription: Existing description.\n"
        "convention-exempt: true\n"
        "details:\n  samples: [1, 2]\n  enabled: false\n"
        "---\n\n" + body,
    )
    before = read_front_matter(path.read_text())
    assert fix(bundle, "FM") == 0
    after = read_front_matter(path.read_text())
    assert after["convention-exempt"] is True
    assert after["details"] == {"samples": [1, 2], "enabled": False}
    assert all(after[key] == value for key, value in before.items())
    assert after["title"] == "A proper title"
    assert path.read_text().endswith(body)


@pytest.mark.parametrize("absolute_filesystem", [False, True])
def test_link_repair_preserves_encoded_spaces(bundle: Path, absolute_filesystem: bool) -> None:
    """Repair a link to a spaced filename into valid, still-resolvable Markdown."""
    import re
    from urllib.parse import quote, unquote

    target = write(bundle.parent, "docs/a b.md", "# Target\n")
    original = quote(str(target), safe="/") if absolute_filesystem else "/docs/a%20b.md"
    path = write(bundle, "references/space.md", page(f"# Source\n\n[Target]({original})\n"))
    assert findings(bundle, "LINK")
    assert fix(bundle, "LINK") == 0
    repaired = path.read_text()
    match = re.search(r"\[Target\]\((<[^>]+>|[^\s)]+)\)", repaired)
    assert match is not None, "The repaired target must be valid Markdown"
    relative = unquote(match.group(1).strip("<>"))
    assert not relative.startswith("/")
    assert (path.parent / relative).resolve() == target.resolve()
    assert not findings(bundle, "LINK")


def test_log_undated_heading_cannot_assign_evidence_to_preceding_day(bundle: Path) -> None:
    """An undated section requires author input before its events get a date."""
    path = write(
        bundle,
        "log.md",
        "# Log\n\n## 2026-10-01\n\n- evidence\n\n# Undated section\n\n- other evidence\n",
    )
    commit_fixture(bundle, path)
    before = path.read_bytes()
    assert findings(bundle, "LOG")
    assert fix(bundle, "LOG") == 2
    assert path.read_bytes() == before


def test_pickup_stops_at_next_heading_even_when_subordinate(bundle: Path) -> None:
    """Numbered design steps after the resume section are not pickup actions."""
    write(
        bundle,
        "references/resume-boundary.md",
        page(
            "# Where to pick this up\n\n1. Open: Verify the pending measurement.\n\n"
            "## Context\n\n1. Existing design step.\n"
        ),
    )
    assert not findings(bundle, "PICKUP")


def test_revision_scan_uses_committed_text_and_excludes_untracked_pages(bundle: Path) -> None:
    """Publication checks ignore pending edits and files absent from the revision."""
    path = write(bundle, "references/committed.md", page("# Committed\n"))
    commit_fixture(bundle, path)
    path.write_text("# Dirty metadata-free replacement\n")
    write(bundle, "references/untracked.md", "# Untracked metadata-free page\n")
    assert len(findings(bundle, "FM")) == 2
    assert not [item for item in okf_lint.scan(bundle, revision="HEAD") if item.rule == "FM"]


def test_revision_links_cannot_resolve_against_untracked_worktree_targets(bundle: Path) -> None:
    """A locally available target is still missing from a published snapshot."""
    source = write(bundle, "references/source.md", page("# Source\n\n[Target](target.md)\n"))
    commit_fixture(bundle, source)
    write(bundle, "references/target.md", page("# Pending target\n"))
    assert not findings(bundle, "LINK")
    missing = [item for item in okf_lint.scan(bundle, revision="HEAD") if item.rule == "LINK"]
    assert len(missing) == 1
    assert missing[0].path == "references/source.md"


def test_revision_board_reads_companion_commit_not_dirty_worktree(
    bundle: Path, tmp_path: Path
) -> None:
    """Linked board validation uses its owner's published state in revision mode."""
    companion = tmp_path / "companion"
    subprocess.run(["git", "init", "-q", str(companion)], check=True)
    companion_bundle = companion / "okf"
    board = write(
        companion_bundle,
        "agent-board.md",
        "# Board\n\n## Open\n\n- **T-1** ✅ Done\n\n## Resolved\n",
    )
    commit_fixture(companion_bundle, board)
    link = bundle / "agent-board.md"
    link.symlink_to(board)
    commit_fixture(bundle, link)
    board.write_text("# Board\n\n## Open\n\n## Resolved\n\n- **T-1** ✅ Done\n")
    assert not findings(bundle, "BOARD")
    committed = [item for item in okf_lint.scan(bundle, revision="HEAD") if item.rule == "BOARD"]
    assert committed
    assert all(item.path == "agent-board.md" for item in committed)


def test_revision_fix_is_rejected_without_worktree_mutation(bundle: Path) -> None:
    """A historical validation mode must never write to current source files."""
    path = write(bundle, "references/missing.md", "# Missing metadata\n")
    commit_fixture(bundle, path)
    path.write_text("# User's pending replacement\n")
    before = path.read_bytes()
    try:
        result = okf_lint.main(["--root", str(bundle), "--revision", "HEAD", "--fix"])
    except SystemExit as error:
        result = error.code
    assert result == 2
    assert path.read_bytes() == before


def test_committed_baseline_detects_new_defect_only_after_commit(bundle: Path) -> None:
    """The publication guard rejects new committed debt without claiming dirty work."""
    from build_tools.okf import baseline

    path = write(bundle, "references/published.md", page("# Published\n"))
    commit_fixture(bundle, path)
    expected, _ = baseline.collect(bundle)
    path.write_text(page("# Published\n\n[[new unsupported wiki link]]\n"))
    dirty, _ = baseline.collect(bundle)
    assert baseline.compare(dirty, expected) == {"new": [], "stale": []}
    commit_fixture(bundle, path)
    published, _ = baseline.collect(bundle)
    difference = baseline.compare(published, expected)
    assert len(difference["new"]) == 1
    assert '"WIKI"' in difference["new"][0]
    assert not difference["stale"]


def test_revision_missing_companion_is_explicit_failure(bundle: Path, tmp_path: Path) -> None:
    """A missing linked provider must never silently produce a clean snapshot."""
    link = bundle / "agent-board.md"
    link.symlink_to(tmp_path / "unavailable-companion" / "okf" / "agent-board.md")
    commit_fixture(bundle, link)
    with pytest.raises(ValueError):
        okf_lint.scan(bundle, revision="HEAD")
