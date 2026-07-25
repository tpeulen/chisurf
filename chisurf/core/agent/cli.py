"""Command-line driver for the ChiSurf agent.

Run one request and exit::

    python -m chisurf.core.agent "fit every decay in ./data with Lifetime (new)"

or hold a conversation::

    python -m chisurf.core.agent --interactive

The command line is the headless path through the same harness the GUI panel
uses, which is what makes the agent testable and scriptable.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.llm import LLMError
from chisurf.core.agent.runtime import AgentConfig, AgentSession, build_session
from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_READ, SAFETY_WRITE
from chisurf.core.agent.tools import build_default_registry


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``python -m chisurf.core.agent``."""
    parser = argparse.ArgumentParser(
        prog="chisurf-agent",
        description="Operate ChiSurf in plain language.",
    )
    parser.add_argument("request", nargs="*", help="What you want done.")
    parser.add_argument(
        "--provider", default=None, help="AI provider key (default: the selected one)."
    )
    parser.add_argument("--model", default=None, help="Model identifier override.")
    parser.add_argument(
        "--directory", "-C", default=".", help="Working directory for relative paths."
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Keep the conversation open."
    )
    parser.add_argument(
        "--safety",
        choices=[SAFETY_READ, SAFETY_WRITE, SAFETY_DANGEROUS],
        default=SAFETY_DANGEROUS,
        help="Highest tool tier the model may use (default: all tools).",
    )
    parser.add_argument("--max-steps", type=int, default=24, help="Model turns per request.")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Approve dangerous tools without asking."
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Only print the final answer.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument(
        "--list-tools", action="store_true", help="Print the tool catalogue and exit."
    )
    parser.add_argument(
        "--list-skills", action="store_true", help="Print the skill catalogue and exit."
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="Do not auto-load skills (they stay reachable through load_skill).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    parser.add_argument(
        "--no-qt",
        action="store_true",
        help="Do not create an off-screen Qt application (fewer readers and models).",
    )
    return parser


def _print_event(name: str, payload: dict[str, Any]) -> None:
    """Render a runtime event as a single readable console line."""
    if name == "tool.started":
        arguments = json.dumps(payload.get("arguments", {}), default=str)
        print(f"  → {payload.get('tool')} {arguments[:160]}", file=sys.stderr)
    elif name == "tool.completed":
        status = "ok" if payload.get("ok") else "failed"
        print(
            f"  ← {payload.get('tool')} {status} ({payload.get('elapsed_ms')} ms)", file=sys.stderr
        )
    elif name in ("tool.failed", "tool.denied"):
        print(f"  ! {payload.get('tool')}: {payload.get('error')}", file=sys.stderr)
    elif name == "skill.loaded":
        print(
            f"  * skill: {payload.get('skill')} ({payload.get('trigger')})",
            file=sys.stderr,
        )


def _confirm(tool: str, arguments: dict[str, Any]) -> bool:
    """Ask on the terminal before running a dangerous tool."""
    print(f"\nThe agent wants to run '{tool}':", file=sys.stderr)
    print(json.dumps(arguments, indent=2, default=str)[:2000], file=sys.stderr)
    try:
        answer = input("Allow? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def build_cli_session(arguments: argparse.Namespace) -> AgentSession:
    """Create the agent session described by parsed command-line *arguments*."""
    if not arguments.no_qt:
        from chisurf.core.experiments.bootstrap import ensure_qt_application

        ensure_qt_application()
    context = AgentContext(
        working_directory=arguments.directory,
        allow_code_execution=arguments.safety == SAFETY_DANGEROUS,
        confirm=None if arguments.yes else _confirm,
        event_callback=None if arguments.quiet else _print_event,
    )
    return build_session(
        provider=arguments.provider,
        model=arguments.model,
        working_directory=arguments.directory,
        context=context,
        config=AgentConfig(
            max_steps=arguments.max_steps,
            max_safety=arguments.safety,
            auto_load_skills=not arguments.no_skills,
        ),
    )


def _report(result: Any, as_json: bool) -> None:
    """Print an :class:`AgentResult` in the requested format."""
    if as_json:
        print(
            json.dumps(
                {
                    "text": result.text,
                    "ok": result.ok,
                    "stop_reason": result.stop_reason,
                    "steps": result.steps,
                    "tools": result.tool_names(),
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        print(result.text)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m chisurf.core.agent``.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments; ``sys.argv[1:]`` when omitted.

    Returns
    -------
    int
        Process exit status.
    """
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if arguments.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if arguments.list_tools:
        print(build_default_registry().describe(arguments.safety))
        return 0

    if arguments.list_skills:
        from chisurf.core.agent.skills import SkillLibrary

        library = SkillLibrary.discover()
        for name in library.names():
            skill = library.get(name)
            print(f"{name}\n    {skill.description.strip()}")
            if skill.triggers:
                print(f"    triggers: {', '.join(skill.triggers)}")
        return 0

    request = " ".join(arguments.request).strip()
    if not request and not arguments.interactive:
        build_parser().print_help()
        return 2

    try:
        session = build_cli_session(arguments)
    except LLMError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3

    if request:
        result = session.ask(request)
        _report(result, arguments.json)
        if not arguments.interactive:
            return 0 if result.ok else 1

    while arguments.interactive:
        try:
            question = input("\nchisurf> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break
        if not question:
            continue
        if question in ("exit", "quit"):
            break
        try:
            result = session.ask(question)
        except KeyboardInterrupt:
            session.cancel()
            print("cancelled", file=sys.stderr)
            continue
        _report(result, arguments.json)
    return 0
