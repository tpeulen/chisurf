"""Guided tours: what to press, in what order, pointed at in the viewport.

A demo script shows a finished result. A help page says what a control means.
Neither says **which control to touch first**, and that is where a viewer full
of correct, well-documented commands loses someone.

So a tour is a list of steps, each one pointing at a real control and *waiting
for the user to use it*. It never presses anything on their behalf: someone who
watched a button being pressed has not learned where it is. This is the same
contract as ChiSurf's ``guide.json`` tours
(:mod:`chisurf.gui.widgets.tools.guided_tour`), transposed onto a chrome that is
painted rather than built from widgets.

The transposition is what makes this its own module. A ChiSurf tour locates a
``QWidget`` and waits for its signal; there are no widgets here, so a step
locates a **painted rectangle** by name and waits for the **command** it asks
for to run. That second half turns out to be better rather than merely
different: every route through this viewer ends in a command -- the menu entries
issue commands, the toolbar buttons issue commands, the prompt is commands -- so
a step that waits for ``fetch EMD-3061`` is satisfied whichever way the user got
there, and the tour teaches the menu without forbidding the keyboard.

A tour file is JSON beside the demo scripts::

    {"title": "Fit a model into a map",
     "steps": [
       {"title": "What this does",
        "text": "...",
        "target": {}},
       {"title": "Fetch the map",
        "text": "...",
        "target": {"menu": "File"},
        "expect": "fetch EMD-3061",
        "hint": "Type <b>fetch EMD-3061</b> at the prompt."}
     ]}

``target`` names a painted control -- see :meth:`InternalGui.tour_target_rect`
for the vocabulary. ``expect`` is a command prefix; when it is present the step
waits, and ``hint`` says what to do. A step with no ``expect`` is read and
dismissed with **Next**.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

__all__ = ["Tour", "TourStep", "TOUR_DIR", "available_tours", "load_tour"]

#: Where the shipped tours live, beside the demo scripts they complement.
TOUR_DIR = pathlib.Path(__file__).resolve().parent / "demos" / "tours"


@dataclass
class TourStep:
    """One step: what to say, where to point, and what to wait for.

    Attributes
    ----------
    title : str
        The bubble's heading.
    text : str
        The body. Plain text; ``<b>`` and ``<i>`` are stripped rather than
        rendered, because the chrome's painter draws one font.
    target : dict
        Which painted control to ring. Empty means "no particular one", and the
        bubble is centred -- used for the opening step.
    expect : str
        A command prefix. Present, the step waits for a command that starts
        with it; absent, **Next** moves on.
    hint : str
        What to do, shown while waiting. Falls back to a sentence built from
        *expect*, so a step is never mute about what it is waiting for.
    setup : str
        A command run when the step is **shown**, to put on screen the thing
        it is about. A step that describes the Density panel and rings it must
        open it first, or it points at nothing and the panel it is describing
        is not there -- which is what "some windows do not seem to appear"
        was.

        Distinct from *run*, and the distinction is the tour's rule: *setup*
        reveals the subject, *run* performs the action the step is teaching,
        and only the second is something the user could have done themselves.
    run : str
        What the step's **Run** button executes. Defaults to *expect*, which is
        right when that is a whole command -- and is not when it is a prefix: a
        step matching any ``translate`` cannot run the word on its own, and
        pressing Run answered "missing required argument". A step whose
        ``expect`` is a prefix gives the command to run here.
    """

    title: str
    text: str = ""
    target: dict = field(default_factory=dict)
    expect: str = ""
    hint: str = ""
    run: str = ""
    setup: str = ""

    @property
    def command(self) -> str:
        """The command Run issues: *run* when given, else *expect*."""
        return self.run or self.expect

    @property
    def waits(self) -> bool:
        """Whether this step needs the user to do something."""
        return bool(self.expect)

    def prompt(self) -> str:
        """What to tell the user while waiting."""
        if self.hint:
            return self.hint
        return f"Run: {self.expect}"

    def satisfied_by(self, line: str) -> bool:
        """Whether *line* is the command this step is waiting for.

        Matched on the leading words of *expect*, not on the whole string, so a
        step that asks for ``isosurface dens, EMD-3061`` is also satisfied by
        ``isosurface dens, EMD-3061, 0.03`` -- the user tried a level of their
        own, which is the tour working, not a deviation from it.
        """
        if not self.expect:
            return False
        wanted = " ".join(str(self.expect).lower().split())
        got = " ".join(str(line).lower().split())
        return got.startswith(wanted)


@dataclass
class Tour:
    """A named sequence of steps, and where the user is in it."""

    name: str
    title: str
    steps: list[TourStep]
    index: int = 0

    @property
    def current(self) -> TourStep | None:
        """The step being shown, or ``None`` once the tour is over."""
        if 0 <= self.index < len(self.steps):
            return self.steps[self.index]
        return None

    @property
    def finished(self) -> bool:
        """Whether every step has been passed."""
        return self.index >= len(self.steps)

    def advance(self) -> None:
        """Move to the next step."""
        self.index += 1

    def observe(self, line: str) -> bool:
        """Take note of an executed command; return whether it advanced the tour.

        Only the *current* step is consulted. A tour that skipped ahead when a
        later step's command happened to run would teach a workflow nobody
        performed.
        """
        step = self.current
        if step is not None and step.satisfied_by(line):
            self.advance()
            return True
        return False


def _strip_markup(text: str) -> str:
    """Drop the inline HTML a ChiSurf tour would render, keeping code marked.

    The tours are written in the same dialect as the widget-based ones so the
    two can be read side by side, but this chrome paints one font: bold and
    italic have nowhere to go.

    **A command does, and it needs one.** A step that says *type translate
    [6, -4, 3], 5a63* runs the command into the prose around it, and the
    reader has to work out where the sentence stops and the thing they must
    type starts. So ``<code>`` spans become ```backticks```, which the painter
    draws in its own colour -- see :meth:`InternalGui._paint_tour`.

    ``<b>`` is **not** code. It is emphasis, and the tours use it on ordinary
    words -- "a map-to-map correlation", "0.49" -- so treating it as code put
    half the prose in a command's colour on its own line, which is worse than
    no styling at all.
    """
    text = str(text)
    for opening, closing in (("<code>", "</code>"), ("<tt>", "</tt>")):
        text = text.replace(opening, "`").replace(closing, "`")
    out, depth = [], 0
    for character in text:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(character)
    return "".join(out).replace("&nbsp;", " ").replace("&amp;", "&")


def _step_from(data: dict) -> TourStep:
    return TourStep(
        title=str(data.get("title", "")),
        text=_strip_markup(data.get("text", "")),
        target=dict(data.get("target") or {}),
        expect=str(data.get("expect", "")),
        hint=_strip_markup(data.get("hint", "")),
        run=str(data.get("run", "")),
        setup=str(data.get("setup", "")),
    )


def available_tours() -> list[tuple[str, str]]:
    """``(name, title)`` for every shipped tour, in name order."""
    found = []
    for path in sorted(TOUR_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken tour must not break the menu
            continue
        found.append((path.stem, str(data.get("title", path.stem))))
    return found


def load_tour(name: str) -> Tour:
    """Read a shipped tour by name.

    Raises
    ------
    FileNotFoundError
        If there is no such tour. Listing what there is belongs to the caller,
        which has somewhere to print it.
    ValueError
        If the file is unreadable or has no steps -- an empty tour would open
        an empty bubble and look like the feature is broken.
    """
    path = TOUR_DIR / f"{str(name).strip()}.json"
    if not path.exists():
        raise FileNotFoundError(f"no tour called '{name}'")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"tour '{name}' could not be read: {exc}") from exc
    steps = [_step_from(entry) for entry in data.get("steps") or []]
    if not steps:
        raise ValueError(f"tour '{name}' has no steps")
    return Tour(name=path.stem, title=str(data.get("title", path.stem)), steps=steps)
