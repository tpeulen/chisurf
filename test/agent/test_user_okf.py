"""The user's OKF bundle: the agent's own, self-populated knowledge.

Replaces the LLM Wiki: the bundle lives in the user's folder
(``~/.chisurf/okf``), grows as the user interacts, and is plain OKF
(index + dated log + concepts) so any client — a later agent session or an
MCP client such as Claude — reads the same record.
"""

from __future__ import annotations

from datetime import datetime

from chisurf.core.agent import user_okf


def test_record_task_appends_dated_bullets_newest_first(tmp_path):
    root = tmp_path / "okf"
    base = datetime(2026, 10, 25, 9, 30)
    user_okf.record_task("burstwise analysis of xy: 97 bursts", root=root, now=base)
    user_okf.record_task("fitted the distance distribution", root=root, now=base)
    bullets = user_okf.read_log(root)
    assert bullets[0].endswith("fitted the distance distribution")
    assert all(b.startswith("- 2026-10-25") for b in bullets)


def test_the_bundle_is_a_standard_okf(tmp_path):
    log = user_okf.record_task("did the thing", root=tmp_path / "okf")
    bundle = log.parent
    assert log.name == "log.md" and log.exists()
    assert (bundle / "index.md").exists()
    assert (bundle / "concepts").is_dir()


def test_write_concept_slugs_and_frontmatter(tmp_path):
    path = user_okf.write_concept(
        "Burst window choice (xy data)", "delta t = 0.5 ms keeps 90% of bursts",
        root=tmp_path,
    )
    text = path.read_text()
    assert text.startswith("---\ntitle: Burst window choice (xy data)")
    assert "delta t = 0.5 ms" in text


def test_record_finding_tool_registers_and_validates(tmp_path):
    from chisurf.core.agent.spec import ToolRegistry, ToolError
    from chisurf.core.agent import user_okf

    registry = ToolRegistry()
    user_okf.build_tool_handler(registry)
    spec = registry.get("record_finding")
    assert spec is not None and spec.parameters["required"] == ["title"]

    # An empty title raises before anything is written (and the real home is
    # never touched in tests: content paths are driven through `root=`).
    from chisurf.core.agent.spec import ToolError, call_handler

    try:
        call_handler(spec, None, {"title": "  "})
        raise AssertionError("empty title must raise")
    except ToolError:
        pass

    path = user_okf.write_concept("gamma = 1.05 for xy", "from the donor-only fit", root=tmp_path)
    assert path.exists()
    user_okf.record_task("recorded finding: gamma = 1.05 for xy", root=tmp_path)
    assert any("gamma = 1.05" in b for b in user_okf.read_log(tmp_path))


def test_context_injection_is_empty_until_there_is_history(tmp_path):
    assert user_okf.as_context(root=tmp_path) == ""
    user_okf.record_task("first finding", root=tmp_path)
    text = user_okf.as_context(root=tmp_path)
    assert "Recent work" in text and "first finding" in text
