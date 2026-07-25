"""The catalogue of example prompts for the ChiSurf assistant.

The examples in ``examples/prompts.yaml`` are documentation, starter prompts
in the assistant panel, **and** the live end-to-end tests -- one source, three
consumers.  Keeping them together is what stops the three from drifting: an
example that only lives in the documentation is never checked, and a test
nobody reads teaches nobody how to use the program.

Each example carries what it needs to be run unattended: the sample data it
expects, the tools that must be used, the skills the wording should pull in,
and the files it should leave behind.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Where the shipped catalogue lives.
CATALOGUE_PATH = pathlib.Path(__file__).parent / "examples" / "prompts.yaml"


@dataclass
class ExamplePrompt:
    """One documented way of asking the assistant for something.

    Parameters
    ----------
    id : str
        Stable identifier.
    title : str
        Short label for menus and tables.
    prompt : str
        The text a user would type.
    explanation : str
        What the assistant is expected to do, in prose.
    data : str
        Sample directory (under ``test/data``) the example needs.
    needs : str
        ``"session"`` when the prompt needs data loaded, ``"fitted-session"``
        when it also needs a fit to exist, otherwise empty.
    must_call : list of str
        Tools that have to be used; a miss is a defect in the harness.
    should_call : list of str
        Tools that are the natural choice but not the only reasonable one.
    expect_skills : list of str
        Skills the wording must pull in.  Routing is deterministic, so this
        is a hard expectation.
    writes : list of str
        Glob patterns for files the prompt should leave behind.
    safety : str
        Highest tool tier the example needs.
    """

    id: str
    title: str
    prompt: str
    explanation: str = ""
    data: str = ""
    needs: str = ""
    must_call: list[str] = field(default_factory=list)
    should_call: list[str] = field(default_factory=list)
    expect_skills: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    safety: str = "write"

    @property
    def needs_session(self) -> bool:
        """Whether the example expects data to be loaded already."""
        return self.needs.strip().lower() in ("session", "fitted-session")

    @property
    def needs_fit(self) -> bool:
        """Whether the example expects a fit to exist already.

        "Is this fit any good?" is not a question you can ask of a session
        that only holds raw data.
        """
        return self.needs.strip().lower() == "fitted-session"

    def one_line(self) -> str:
        """Return the example as a single line for a terminal listing."""
        return f"{self.id}: {self.prompt.strip()}"


def load_examples(path: pathlib.Path | None = None) -> list[ExamplePrompt]:
    """Read the example catalogue.

    Parameters
    ----------
    path : pathlib.Path, optional
        Catalogue to read.  Defaults to the shipped one.

    Returns
    -------
    list of ExamplePrompt
        In file order, which is the order they are shown in.

    Examples
    --------
    >>> examples = load_examples()
    >>> any(example.id == "fit-one-decay" for example in examples)
    True
    """
    import yaml

    source = path or CATALOGUE_PATH
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("could not read the example catalogue at %s", source, exc_info=True)
        return []

    examples: list[ExamplePrompt] = []
    for entry in document.get("examples", []) or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        fields = {key: entry.get(key) for key in ExamplePrompt.__dataclass_fields__}
        cleaned: dict[str, Any] = {}
        for key, value in fields.items():
            if value is None:
                continue
            if key in ("must_call", "should_call", "expect_skills", "writes"):
                cleaned[key] = [str(item) for item in (value or [])]
            else:
                cleaned[key] = str(value).strip()
        examples.append(ExamplePrompt(**cleaned))
    return examples


def get_example(identifier: str, path: pathlib.Path | None = None) -> ExamplePrompt | None:
    """Return the example with *identifier*, or ``None``."""
    wanted = str(identifier).strip()
    for example in load_examples(path):
        if example.id == wanted:
            return example
    return None


def starter_prompts(limit: int = 6) -> list[ExamplePrompt]:
    """Return examples suitable as one-click starters in the GUI.

    Prompts that need a loaded session are listed after the ones that work
    from a cold start, because an empty session is what a new user has.

    Parameters
    ----------
    limit : int
        Maximum number of prompts to return.

    Returns
    -------
    list of ExamplePrompt
    """
    examples = load_examples()
    cold = [example for example in examples if not example.needs_session]
    warm = [example for example in examples if example.needs_session]
    return (cold + warm)[: max(0, int(limit))]


def describe_examples() -> str:
    """Return the catalogue as text for ``--list-examples``."""
    lines: list[str] = []
    for example in load_examples():
        lines.append(f'{example.id}\n    "{example.prompt.strip()}"')
        if example.explanation:
            lines.append(f"    {' '.join(example.explanation.split())}")
        details = []
        if example.data:
            details.append(f"data: test/data/{example.data}")
        if example.needs_session:
            details.append("needs a loaded session")
        if example.safety != "write":
            details.append(f"safety: {example.safety}")
        if details:
            lines.append("    (" + "; ".join(details) + ")")
    return "\n".join(lines)


def markdown_table() -> str:
    """Return the catalogue as a markdown table for the user guide."""
    rows = ["| Ask it | What it does |", "| --- | --- |"]
    for example in load_examples():
        prompt = " ".join(example.prompt.split())
        explanation = " ".join(example.explanation.split())
        rows.append(f"| *“{prompt}”* | {explanation} |")
    return "\n".join(rows)
