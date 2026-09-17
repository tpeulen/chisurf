"""The generated spec copy must not drift from the spec.

PTO.MFDB is normative and lives in two places: ``okf/specs/`` for agents, and a
reStructuredText copy beside the container's own format documentation for
people. Two copies of a normative document is exactly the failure the profile
exists to prevent, so only one is written by hand and the other is generated.
These tests are what makes that true rather than merely intended: an edit to the
markdown that is not regenerated fails here, not silently in a docs build
nobody runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "build_tools" / "docs" / "generate_spec_rst.py"

sys.path.insert(0, str(REPO_ROOT / "build_tools" / "docs"))

from generate_spec_rst import SPECS, UnsupportedMarkdown, render  # noqa: E402


@pytest.mark.parametrize("src_rel, dst_rel", SPECS)
def test_the_generated_copy_is_current(src_rel: str, dst_rel: str) -> None:
    source = REPO_ROOT / src_rel
    target = REPO_ROOT / dst_rel
    assert source.exists(), f"spec source missing: {src_rel}"
    assert target.exists(), f"generated spec missing: {dst_rel} — run: pixi run docs-specs"
    assert target.read_text(encoding="utf-8") == render(source), (
        f"{dst_rel} is stale relative to {src_rel} — run: pixi run docs-specs"
    )


@pytest.mark.parametrize("_src_rel, dst_rel", SPECS)
def test_the_generated_copy_says_it_is_generated(_src_rel: str, dst_rel: str) -> None:
    """Otherwise the first person to find a typo fixes it in the wrong file."""
    head = (REPO_ROOT / dst_rel).read_text(encoding="utf-8")[:400]
    assert "GENERATED" in head and "do not edit" in head


def test_check_mode_exits_non_zero_when_stale(tmp_path: Path) -> None:
    """The mode CI runs. Proved by making a copy stale on purpose rather than
    by trusting that the flag is wired up.
    """
    _src_rel, dst_rel = SPECS[0]
    target = REPO_ROOT / dst_rel
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(original + "\nan edit made in the generated file\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "--check passed on a stale generated file"
        assert "stale" in (result.stdout + result.stderr).lower()
    finally:
        target.write_text(original, encoding="utf-8")


def test_an_unhandled_construct_raises_rather_than_guessing(tmp_path: Path) -> None:
    """A permissive converter renders what it does not understand as something
    plausible, and a silently mangled normative table is worse than a build
    failure.
    """
    bad = tmp_path / "bad.md"
    bad.write_text("---\ntitle: T\n---\n\n| a | b |\n| 1 | 2 |\n", encoding="utf-8")
    with pytest.raises(UnsupportedMarkdown):
        render(bad)


@pytest.mark.parametrize("_src_rel, dst_rel", SPECS)
def test_the_generated_rest_parses(_src_rel: str, dst_rel: str) -> None:
    """Generating text that sphinx cannot read would defeat the point."""
    core = pytest.importorskip("docutils.core")
    from docutils.utils import SystemMessage

    text = (REPO_ROOT / dst_rel).read_text(encoding="utf-8")
    try:
        core.publish_doctree(
            text,
            settings_overrides={"report_level": 2, "halt_level": 3, "warning_stream": False},
        )
    except SystemMessage as exc:  # pragma: no cover - only on a real defect
        pytest.fail(f"{dst_rel} is not valid reStructuredText: {exc}")


@pytest.mark.parametrize("_src_rel, dst_rel", SPECS)
def test_the_generated_copy_is_in_a_toctree(_src_rel: str, dst_rel: str) -> None:
    """An unreferenced page builds clean and is unreachable."""
    target = REPO_ROOT / dst_rel
    index = target.parent / "index.rst"
    assert index.exists(), f"no index beside {dst_rel}"
    assert target.stem in index.read_text(encoding="utf-8"), (
        f"{target.stem} is not listed in {index.relative_to(REPO_ROOT)}"
    )
