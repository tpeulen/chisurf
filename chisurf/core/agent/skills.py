"""Skills: the agent's procedural knowledge, loaded on demand.

A tool says *what can be done*; a skill says *how this kind of job is done
properly*.  "Attach the IRF, then add lifetime components until chi-square
stops improving" is not a tool — it is the procedure a spectroscopist follows,
and it is exactly the knowledge a general-purpose model lacks.

Keeping that knowledge in the system prompt does not scale: every experiment
type would add a section that is dead weight for every other request.  Skills
are separate documents with their own metadata; only the ones relevant to the
question are loaded, and the rest cost a single catalogue line each.

A skill is a ``SKILL.md`` file with YAML frontmatter::

    ---
    name: fit-decay
    description: Fit time-resolved fluorescence decays. Use when ...
    triggers: [decay, lifetime, tcspc, irf]
    experiments: [TCSPC]
    tools: [load_data, set_irf, auto_fit_decay]
    ---

    # Fitting a fluorescence decay
    ...the procedure...

Skills are discovered from three places, later ones overriding earlier:

1. the built-in library shipped with ChiSurf,
2. plugin directories (a plugin can teach the agent its own workflow),
3. ``<settings>/agent_skills/``, where a user can add or override one.
"""

from __future__ import annotations

import logging
import pathlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Name of the document that defines a skill inside a skill directory.
SKILL_FILENAME = "SKILL.md"

#: Score a skill must reach before it is auto-loaded for a question.
MATCH_THRESHOLD = 2.0

#: How many skills are injected into one request at most. Skills a matched
#: skill is composed of do not count against this — they are pulled in by
#: :meth:`SkillLibrary.compose` after the cut, so decomposing a procedure into
#: reusable parts never costs it a slot.
MAX_AUTO_SKILLS = 3


#: How many words may sit between the words of a multi-word trigger.
_TRIGGER_GAP = 2


def trigger_pattern(trigger: str) -> re.Pattern[str]:
    """Compile a trigger phrase into a forgiving regular expression.

    People do not phrase requests the way a keyword list is written: "fit all
    20 files" should match the trigger ``all files``, and "each of the decays"
    should match ``decay``. Words of a multi-word trigger are therefore
    allowed to sit up to :data:`_TRIGGER_GAP` words apart, and a trailing
    plural is optional.

    A ``*`` in a trigger stands for any single word, so ``every *`` covers
    "every decay", "every file" and "every measurement" without listing the
    nouns a user might reach for.

    Parameters
    ----------
    trigger : str
        The trigger phrase from a skill's frontmatter.

    Returns
    -------
    re.Pattern
        Compiled, case-insensitive pattern.

    Examples
    --------
    >>> bool(trigger_pattern("all files").search("fit all 20 files please"))
    True
    >>> bool(trigger_pattern("decay").search("these decays"))
    True
    >>> bool(trigger_pattern("decay").search("decayed sample"))
    False
    >>> bool(trigger_pattern("every *").search("fit every decay"))
    True
    """
    words = [word for word in re.split(r"[^\w*]+", trigger.strip().lower()) if word]
    if not words:
        return re.compile(r"(?!x)x")  # matches nothing
    parts = [r"\w+" if word == "*" else re.escape(word) for word in words]
    if words[-1] != "*":
        parts[-1] += "s?"
    joined = (r"\W+(?:\w+\W+){0," + str(_TRIGGER_GAP) + r"}").join(parts)
    return re.compile(r"\b" + joined + r"\b", flags=re.IGNORECASE)


@dataclass
class Skill:
    """One packaged procedure.

    Parameters
    ----------
    name : str
        Identifier used by ``load_skill`` (``kebab-case``).
    description : str
        One or two sentences: what the skill covers *and when to use it*.
        This is the only part the model sees until the skill is loaded, so it
        carries the whole routing decision.
    body : str
        The procedure itself, in markdown.
    triggers : list of str
        Words or phrases in a request that make this skill relevant.
    experiments : list of str
        ChiSurf experiment types this skill applies to; a loaded dataset of
        that type makes the skill relevant even when the wording does not.
    tools : list of str
        Tools the procedure uses. Informational — it does not grant access.
    uses : list of str
        Names of skills this procedure is built out of. They are loaded with
        it, transitively, so a skill can be a composition of smaller ones
        instead of repeating them.
    source : str
        Where the skill was read from.
    """

    name: str
    description: str
    body: str = ""
    triggers: list[str] = field(default_factory=list)
    experiments: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    uses: list[str] = field(default_factory=list)
    source: str = ""

    def catalogue_line(self) -> str:
        """Return the one-line entry shown in the skill catalogue."""
        return f"- **{self.name}** — {self.description.strip()}"

    def rendered(self) -> str:
        """Return the full skill text as injected into the conversation."""
        header = f"# Skill: {self.name}\n\n{self.description.strip()}"
        return f"{header}\n\n{self.body.strip()}"

    def score(self, question: str, experiments: Iterable[str] = ()) -> float:
        """Return how relevant this skill is to a request.

        Parameters
        ----------
        question : str
            The user's message.
        experiments : iterable of str
            Experiment types present in the session.

        Returns
        -------
        float
            Higher is more relevant; 0 means "no signal".
        """
        text = (question or "").lower()
        score = 0.0
        for trigger in self.triggers:
            if trigger_pattern(trigger).search(text):
                score += 2.0
        if self.name.lower().replace("-", " ") in text:
            score += 3.0
        session_experiments = {str(name).lower() for name in experiments}
        if session_experiments & {str(name).lower() for name in self.experiments}:
            # A weak signal on its own: it says the skill *could* apply, not
            # that this request is about it.
            score += 1.0
        return score


def parse_skill(text: str, source: str = "") -> Skill | None:
    """Parse a ``SKILL.md`` document.

    Parameters
    ----------
    text : str
        File contents, with or without YAML frontmatter.
    source : str
        Path recorded on the skill for diagnostics.

    Returns
    -------
    Skill or None
        ``None`` when the document has no usable ``name``.
    """
    import yaml

    metadata: dict[str, Any] = {}
    body = text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1)) or {}
            if isinstance(loaded, dict):
                metadata = loaded
            body = match.group(2)
        except Exception:
            logger.warning("skill %s has invalid frontmatter", source or "<inline>")

    name = str(metadata.get("name", "") or "").strip()
    if not name and source:
        name = pathlib.Path(source).parent.name
    if not name:
        return None

    def _as_list(value: Any) -> list[str]:
        """Return *value* as a list of strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    return Skill(
        name=name,
        description=str(metadata.get("description", "") or "").strip(),
        body=body.strip(),
        triggers=_as_list(metadata.get("triggers")),
        experiments=_as_list(metadata.get("experiments")),
        tools=_as_list(metadata.get("tools")),
        uses=_as_list(metadata.get("uses")),
        source=source,
    )


def builtin_skill_directory() -> pathlib.Path:
    """Return the directory holding the skills shipped with ChiSurf."""
    return pathlib.Path(__file__).parent / "skills_builtin"


def user_skill_directory() -> pathlib.Path:
    """Return the per-user skill directory (may not exist)."""
    from chisurf.core.settings import get_path

    return pathlib.Path(get_path("settings")) / "agent_skills"


def plugin_skill_directories() -> list[pathlib.Path]:
    """Return ``agent_skills`` directories shipped by plugins.

    A plugin teaches the agent its own workflow by adding an
    ``agent_skills/<name>/SKILL.md`` next to its ``manifest.json``.

    Returns
    -------
    list of pathlib.Path
    """
    import chisurf.plugins

    root = pathlib.Path(chisurf.plugins.__file__).parent
    try:
        return sorted(path for path in root.rglob("agent_skills") if path.is_dir())
    except Exception:
        logger.debug("plugin skill discovery failed", exc_info=True)
        return []


@dataclass
class SkillLibrary:
    """The set of skills available to a session."""

    skills: dict[str, Skill] = field(default_factory=dict)

    # ── construction ──────────────────────────────────────────────────

    def add(self, skill: Skill) -> Skill:
        """Add *skill*, replacing any skill of the same name."""
        self.skills[skill.name] = skill
        return skill

    def load_directory(self, directory: pathlib.Path) -> int:
        """Load every ``SKILL.md`` under *directory*.

        Parameters
        ----------
        directory : pathlib.Path
            Directory to scan recursively.

        Returns
        -------
        int
            Number of skills loaded.
        """
        if not directory or not directory.is_dir():
            return 0
        count = 0
        for path in sorted(directory.rglob(SKILL_FILENAME)):
            try:
                skill = parse_skill(path.read_text(encoding="utf-8"), source=str(path))
            except Exception:
                logger.warning("could not read skill %s", path, exc_info=True)
                continue
            if skill is None:
                logger.warning("skill %s has no name", path)
                continue
            self.add(skill)
            count += 1
        return count

    @classmethod
    def discover(cls, extra_directories: Iterable[pathlib.Path] = ()) -> SkillLibrary:
        """Build a library from the built-in, plugin and user directories.

        Later sources override earlier ones, so a user can replace a built-in
        skill by giving their own the same ``name``.

        Parameters
        ----------
        extra_directories : iterable of pathlib.Path
            Additional directories to scan last.

        Returns
        -------
        SkillLibrary
        """
        library = cls()
        library.load_directory(builtin_skill_directory())
        for directory in plugin_skill_directories():
            library.load_directory(directory)
        library.load_directory(user_skill_directory())
        for directory in extra_directories:
            library.load_directory(pathlib.Path(directory))
        return library

    # ── access ────────────────────────────────────────────────────────

    def get(self, name: str) -> Skill | None:
        """Return the skill called *name*, or ``None``."""
        return self.skills.get(str(name).strip())

    def names(self) -> list[str]:
        """Return every skill name, sorted."""
        return sorted(self.skills)

    def catalogue(self, exclude: Iterable[str] = ()) -> str:
        """Return the one-line-per-skill catalogue for the system prompt.

        Parameters
        ----------
        exclude : iterable of str
            Names to leave out (typically the already-loaded skills).

        Returns
        -------
        str
        """
        skipped = {str(name) for name in exclude}
        lines = [
            skill.catalogue_line()
            for name, skill in sorted(self.skills.items())
            if name not in skipped
        ]
        return "\n".join(lines)

    def match(
        self,
        question: str,
        experiments: Iterable[str] = (),
        limit: int = MAX_AUTO_SKILLS,
        threshold: float = MATCH_THRESHOLD,
    ) -> list[Skill]:
        """Return the skills worth loading for a request, best first.

        Parameters
        ----------
        question : str
            The user's message.
        experiments : iterable of str
            Experiment types present in the session.
        limit : int
            Maximum number of skills to return.
        threshold : float
            Minimum score required.

        Returns
        -------
        list of Skill
        """
        scored = [(skill.score(question, experiments), skill) for skill in self.skills.values()]
        relevant = [(score, skill) for score, skill in scored if score >= threshold]
        relevant.sort(key=lambda item: (-item[0], item[1].name))
        chosen = [skill for _, skill in relevant[: max(0, int(limit))]]
        # A composed skill is not usable without its parts, so they come along
        # rather than competing with it for the limited slots.
        return self.compose(chosen)

    def compose(self, skills: Iterable[Skill]) -> list[Skill]:
        """Return *skills* followed by everything they are built out of.

        A skill declares the smaller procedures it composes in its ``uses``
        frontmatter. Those are loaded transitively: asking for a distance from
        single-molecule bursts pulls in burst selection and sub-ensemble decay
        construction, because the composed procedure only says how they fit
        together.

        Parameters
        ----------
        skills : iterable of Skill
            The skills selected for a request.

        Returns
        -------
        list of Skill
            The selected skills first, then their dependencies in the order
            they were reached. Each appears once; cycles terminate.
        """
        ordered: list[Skill] = []
        seen: set[str] = set()

        def visit(skill: Skill) -> None:
            """Add *skill*, then the skills it uses."""
            if skill.name in seen:
                return
            seen.add(skill.name)
            ordered.append(skill)
            for name in skill.uses:
                dependency = self.skills.get(str(name).strip())
                if dependency is None:
                    logger.warning("skill %r uses unknown skill %r", skill.name, name)
                    continue
                visit(dependency)

        for skill in skills:
            visit(skill)
        return ordered


def session_experiments(datasets: Iterable[Any]) -> list[str]:
    """Return the distinct experiment names of the loaded datasets.

    Parameters
    ----------
    datasets : iterable
        Loaded datasets.

    Returns
    -------
    list of str
    """
    names: list[str] = []
    for dataset in datasets:
        experiment = getattr(dataset, "experiment", None)
        name = str(getattr(experiment, "name", "") or experiment or "").strip()
        if name and name not in names:
            names.append(name)
    return names
