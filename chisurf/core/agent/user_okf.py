"""The user's OKF bundle: what the agent did, written where the user lives.

The agent keeps its knowledge in a standard Open Knowledge Format bundle in
the user's folder — ``~/.chisurf/okf/`` — and grows it as the user works:
``index.md`` maps it, ``log.md`` carries dated bullets, ``concepts/`` holds
one page per recurring topic. This replaces the in-repo LLM Wiki: knowledge
about the *user's* data and pipelines belongs beside the user's files, not
inside an application checkout, and it is the agent itself that populates it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

OKF_DIRNAME = "okf"
LOG_FILENAME = "log.md"
INDEX_FILENAME = "index.md"


def okf_root(home: Path | None = None) -> Path:
    """The user's OKF bundle root: ``~/.chisurf/okf`` (overridable for tests)."""
    return (home or Path.home()) / ".chisurf" / OKF_DIRNAME


def _ensure_bundle(root: Path) -> None:
    (root / "concepts").mkdir(parents=True, exist_ok=True)
    log = root / LOG_FILENAME
    if not log.exists():
        log.write_text(
            "# Changelog\n\nDated bullets, newest first — one per completed agent task.\n"
        )
    index = root / INDEX_FILENAME
    if not index.exists():
        index.write_text(
            "---\ntitle: ChiSurf Agent Knowledge\nstatus: living\ntype: index\n---\n\n"
            "# ChiSurf Agent Knowledge\n\n"
            "Written by the agent as you work. `log.md` is the changelog; "
            "`concepts/` collects one page per recurring topic.\n"
        )


def record_task(summary: str, *, root: Path | None = None, now: datetime | None = None) -> Path:
    """Append one dated bullet for a completed agent task; return the log path.

    Called by the runtime when a request ends in an answer: what was asked,
    what was done, where results went — the resume point a later session (or
    an MCP client) reads first.
    """
    bundle = root or okf_root()
    _ensure_bundle(bundle)
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    line = f"- {stamp} {summary.strip()}\n"
    log = bundle / LOG_FILENAME
    text = log.read_text()
    head, _, rest = text.partition("\n\n")
    log.write_text(f"{head}\n\n{line}{rest}" if rest else f"{head}\n\n{line}")
    return log


def concept_path(title: str, *, root: Path | None = None) -> Path:
    """The file for one concept page, slugified (no write)."""
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:64]
    return (root or okf_root()) / "concepts" / f"{slug or 'untitled'}.md"


def write_concept(title: str, body: str, *, root: Path | None = None) -> Path:
    """Write (or replace) one concept page and return its path."""
    bundle = root or okf_root()
    _ensure_bundle(bundle)
    path = concept_path(title, root=bundle)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path.write_text(
        f"---\ntitle: {title}\nstatus: living\ntype: concept\nupdated: {stamp}\n---\n\n{body.strip()}\n"
    )
    return path


def read_log(root: Path | None = None, limit: int = 20) -> list[str]:
    """The newest log bullets — what a fresh session (or MCP client) sees."""
    log = (root or okf_root()) / LOG_FILENAME
    if not log.exists():
        return []
    bullets = [ln.rstrip() for ln in log.read_text().splitlines() if ln.startswith("- ")]
    return bullets[:limit]


def as_context(root: Path | None = None, limit: int = 20) -> str:
    """The bundle's headline as injectable agent context (empty when absent)."""
    bullets = read_log(root, limit)
    if not bullets:
        return ""
    return "Recent work from the user's knowledge bundle:\n" + "\n".join(bullets)


def save_skill(title: str, body: str, triggers: str = "", *, directory=None) -> Path:
    """Write a learned procedure as a user skill; return the SKILL.md path.

    Skills live beside the built-ins in the user's ``agent_skills``
    directory and are picked up by every later session (user entries
    override built-ins of the same name) — this is how the agent learns
    what this user wants and keeps it. The file is a standard ``SKILL.md``
    (frontmatter ``name``/``description``/``triggers`` + markdown body), so
    it reads the same for any client.
    """
    from chisurf.core.agent import skills as agent_skills

    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:64]
    if not slug:
        raise ValueError("a skill needs a title")
    target = (directory or agent_skills.user_skill_directory()) / slug / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"name: {slug}\ndescription: {title.strip()}\n"
    if triggers.strip():
        frontmatter += f"triggers: [{', '.join(t.strip() for t in triggers.split(',') if t.strip())}]\n"
    target.write_text(f"---\n{frontmatter}---\n\n{body.strip()}\n")
    return target


def build_tool_handler(registry: Any) -> None:
    """Register ``record_finding`` — the agent's own pen in the bundle."""
    from chisurf.core.agent.spec import ToolError

    @registry.add(
        name="record_finding",
        description=(
            "Write a durable finding into the user's knowledge bundle "
            "(~/.chisurf/okf) so later sessions and other clients can pick "
            "it up. Use for conclusions worth keeping: chosen parameters, "
            "data quirks, pipeline recipes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What the finding is about."},
                "body": {"type": "string", "description": "What was measured, decided, and why."},
            },
            "required": ["title"],
        },
    )
    def record_finding(context, title: str, body: str = "") -> dict:
        """Record a durable finding in the user's knowledge bundle."""
        if not title.strip():
            raise ToolError("a finding needs a title")
        path = write_concept(title, body or title)
        record_task(f"recorded finding: {title.strip()}")
        return {"recorded": str(path)}

    @registry.add(
        name="save_skill",
        description=(
            "Save a learned procedure or preference as the user's own skill "
            "so every later session keeps it: how this user likes analyses "
            "run, which settings they choose, a pipeline recipe that worked. "
            "Skills load automatically when a future request matches."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What the skill is, e.g. 'Alice prefers E gating before fitting'."},
                "body": {"type": "string", "description": "The procedure or preference, as concrete steps."},
                "triggers": {"type": "string", "description": "Comma-separated words that should load it, e.g. 'burst, gate, smFRET'."},
            },
            "required": ["title", "body"],
        },
    )
    def save_skill_tool(context, title: str, body: str, triggers: str = "") -> dict:
        """Persist a learned procedure as the user's skill."""
        try:
            path = save_skill(title, body, triggers)
        except ValueError as err:
            raise ToolError(str(err)) from err
        record_task(f"learned skill: {title.strip()}")
        return {"saved": str(path)}
