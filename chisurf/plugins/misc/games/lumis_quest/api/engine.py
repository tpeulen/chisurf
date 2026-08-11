"""The script engine: dialogue, conditions and effects, as data.

Everything a character says, every condition a story beat completes on, and
every consequence of talking to somebody lives in JSON under ``data/`` and is
run by this interpreter. Nothing in the game loop knows what a tavern is.

That is the point. The old shape was a chain of ``if role == "healer"`` in the
window class, which meant a new kind of building was a code change in the
renderer, a writer could not touch a line of dialogue without touching Python,
and none of it could be tested without a window. Here:

* a **scene** is a list of steps -- ``say``, ``choice``, ``do``, ``when``,
  ``goto`` -- and an NPC is a name and the id of the scene they run;
* a **condition** is a small data expression evaluated against the run
  (:func:`evaluate`), so a story beat's completion rule is a JSON object rather
  than a branch in a method;
* an **effect** is a named action looked up in a registry
  (:mod:`.actions`), so the set of things the world can do to you is an open
  list that the data selects from, never a switch statement.

The runner is a state machine the host pumps: it never blocks, never draws, and
never imports Qt. Anything it cannot do itself -- start a fight, open a menu,
move the player -- it puts on :attr:`Runner.requests` for the host to satisfy,
which keeps the engine honest about the boundary.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
from typing import Any, Callable

#: Where the shipped scripts live.
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"


class ScriptError(ValueError):
    """A script asked for something the engine does not have."""


# -- conditions -----------------------------------------------------------

#: Condition kinds, by name. Each takes ``(context, value)`` and answers a
#: bool. Registering rather than branching means a new kind of condition is a
#: function, and the data that uses it needs no engine change.
CONDITIONS: dict[str, Callable[[Any, Any], bool]] = {}


def condition(name: str):
    """Register a condition kind.

    Parameters
    ----------
    name : str
        The key scripts use.

    Returns
    -------
    callable
        A decorator.
    """

    def register(function):
        CONDITIONS[name] = function
        return function

    return register


def resolve(value: Any, context) -> Any:
    """Substitute a ``$name`` reference against the run.

    Scenes are shared: one ``warden`` scene serves all five of them, so it has
    to be able to say "the seal of whoever I am talking to". ``$subject`` is
    that, and it is the only indirection the script language has -- a template
    engine here would be a second language nobody asked for.

    Parameters
    ----------
    value : object
        A script value. Only strings beginning with ``$`` are touched.
    context : Context
        The run, whose attribute of that name is read.

    Returns
    -------
    object
        The substituted value, or the original.
    """
    if isinstance(value, str) and value.startswith("$"):
        return getattr(context, value[1:], value)
    return value


def evaluate(expression: Any, context) -> bool:
    """Answer a condition expression against a run.

    Parameters
    ----------
    expression : dict or bool or None
        ``None`` and ``True`` are always true. A dict holds exactly the keys
        that must all hold, so ``{"flag": "x", "order": "rigour"}`` reads as
        "and".
    context : Context
        The run being asked about.

    Returns
    -------
    bool
        Whether it holds.

    Raises
    ------
    ScriptError
        If the expression names a condition kind that is not registered --
        loudly, because a silently-false typo in a story file is a beat that
        can never complete and nobody can find out why.
    """
    if expression is None or expression is True:
        return True
    if expression is False:
        return False
    if not isinstance(expression, dict):
        raise ScriptError(f"not a condition: {expression!r}")
    for key, value in expression.items():
        if key == "not":
            if evaluate(value, context):
                return False
            continue
        if key == "all":
            if not all(evaluate(item, context) for item in value):
                return False
            continue
        if key == "any":
            if not any(evaluate(item, context) for item in value):
                return False
            continue
        handler = CONDITIONS.get(key)
        if handler is None:
            raise ScriptError(f"unknown condition {key!r}")
        if not handler(context, resolve(value, context)):
            return False
    return True


@condition("flag")
def _flag(context, value) -> bool:
    """Whether a story flag has been witnessed."""
    return value in context.flags


@condition("seals")
def _seals(context, value) -> bool:
    """Whether at least this many Warden seals are held."""
    return len(context.seals) >= int(value)


@condition("seal")
def _seal(context, value) -> bool:
    """Whether one named seal is held."""
    return value in context.seals


@condition("unbound")
def _unbound(context, value) -> bool:
    """Whether at least this many labels have been taken."""
    return context.unbound >= int(value)


@condition("order")
def _order(context, value) -> bool:
    """Whether the player has pledged to a given order."""
    return context.order == value


@condition("pledged")
def _pledged(context, value) -> bool:
    """Whether the player has pledged at all."""
    return (context.order is not None) is bool(value)


@condition("dark")
def _dark(context, value) -> bool:
    """Whether the player is in the dark manifold."""
    return bool(context.dark) is bool(value)


@condition("rooms")
def _rooms(context, value) -> bool:
    """Whether the corpus holds at least N rooms in a state.

    Parameters
    ----------
    context : Context
        The run.
    value : dict
        e.g. ``{"settled": 1}``.
    """
    counts = context.room_counts()
    return all(counts.get(state, 0) >= int(least) for state, least in value.items())


@condition("doctrine_work")
def _doctrine_work(context, value) -> bool:
    """Whether enough rooms in the pledged order's lands have been cleared."""
    return context.doctrine_work() >= int(value)


@condition("bodies")
def _bodies(context, value) -> bool:
    """Whether at least this many animals travel with you."""
    return len(context.bodies) >= int(value)


@condition("labels")
def _labels(context, value) -> bool:
    """Whether at least this many labels are held."""
    return len(context.labels) >= int(value)


# -- scenes ---------------------------------------------------------------

@dataclasses.dataclass
class Screen:
    """What the host should put in front of the player right now.

    Attributes
    ----------
    who : str
        Who is speaking, or empty for narration.
    text : str
        One screen of words.
    choices : tuple of str
        Options, empty when the screen is simply advanced.
    """

    who: str = ""
    text: str = ""
    choices: tuple[str, ...] = ()


@dataclasses.dataclass
class Request:
    """Something only the host can do.

    Attributes
    ----------
    kind : str
        e.g. ``battle``, ``menu``, ``cross``, ``save``.
    args : dict
        Whatever that kind needs.
    """

    kind: str
    args: dict = dataclasses.field(default_factory=dict)


class Runner:
    """Plays one scene, one screen at a time.

    Parameters
    ----------
    scenes : dict
        Scene id to list of steps.
    context : Context
        The run the scene reads and changes.
    """

    def __init__(self, scenes: dict[str, list], context) -> None:
        self.scenes = scenes
        self.context = context
        self.requests: list[Request] = []
        self._stack: list[tuple[list, int]] = []
        self._screen: Screen | None = None
        self._choices: list[list] = []
        self.speaker = ""
        self.lines: dict[str, tuple[str, ...]] = {}
        self.finished = True

    def start(self, scene_id: str, who: str = "", lines: dict | None = None,
              subject: str = "") -> Screen | None:
        """Begin a scene.

        Parameters
        ----------
        scene_id : str
            Key into the scene table.
        who : str, optional
            Name to attribute unattributed lines to.
        lines : dict, optional
            Named bundles of authored text this character brings with them --
            ``lines`` for their own screens, ``after`` for what they say once
            beaten, ``reply`` for what Iris says back. Kept out of the scene so
            one ``warden`` scene serves all five.
        subject : str, optional
            What is being talked to, resolved by ``$subject`` in the script.

        Returns
        -------
        Screen or None
            The first screen, or ``None`` for a scene that did nothing.

        Raises
        ------
        ScriptError
            If the scene does not exist.
        """
        if scene_id not in self.scenes:
            raise ScriptError(f"no such scene: {scene_id!r}")
        self.speaker = who
        self.lines = {key: tuple(value) for key, value in (lines or {}).items()}
        self.context.subject = subject
        self._stack = [(list(self.scenes[scene_id]), 0)]
        self._screen = None
        self._choices = []
        self.finished = False
        return self._pump()

    @property
    def screen(self) -> Screen | None:
        """The screen currently showing.

        Returns
        -------
        Screen or None
            ``None`` once the scene is done.
        """
        return self._screen

    def advance(self) -> Screen | None:
        """Move past the current screen.

        Returns
        -------
        Screen or None
            The next screen, or ``None`` when the scene ends.
        """
        if self.finished:
            return None
        self._screen = None
        return self._pump()

    def choose(self, index: int) -> Screen | None:
        """Take one of the offered options.

        Parameters
        ----------
        index : int
            Position in the current screen's choices.

        Returns
        -------
        Screen or None
            The next screen.
        """
        if not self._choices:
            return self.advance()
        branch = self._choices[max(0, min(index, len(self._choices) - 1))]
        self._choices = []
        self._screen = None
        self._stack.append((list(branch), 0))
        return self._pump()

    def take_requests(self) -> list[Request]:
        """Hand the host everything the scene asked it to do.

        Returns
        -------
        list of Request
            Drained; asking twice returns nothing the second time.
        """
        pending, self.requests = self.requests, []
        return pending

    def _pump(self) -> Screen | None:
        """Run steps until a screen is showing or the scene ends.

        Returns
        -------
        Screen or None
            The screen to show.
        """
        guard = 0
        while self._stack:
            guard += 1
            if guard > 10_000:
                raise ScriptError("scene did not terminate")
            steps, index = self._stack[-1]
            if index >= len(steps):
                self._stack.pop()
                continue
            self._stack[-1] = (steps, index + 1)
            screen = self._step(steps[index])
            if screen is not None:
                self._screen = screen
                return screen
        self.finished = True
        self._screen = None
        return None

    def _step(self, step: dict) -> Screen | None:
        """Run one step.

        Parameters
        ----------
        step : dict
            A scene step.

        Returns
        -------
        Screen or None
            A screen to show, or ``None`` to keep going.

        Raises
        ------
        ScriptError
            On an unknown step kind.
        """
        if "choice" in step:
            # Before the plain say: a step may carry *both*, and the say is
            # then the question the options answer. Testing "say" first made
            # every prompted choice in the shipped dialogue render as a line of
            # narration with its options silently dropped.
            options = [option for option in step["choice"]
                       if evaluate(option.get("when"), self.context)]
            if not options:
                return None
            self._choices = [option.get("then", []) for option in options]
            return Screen(
                who=step.get("who", self.speaker),
                text=step.get("say", ""),
                choices=tuple(option["text"] for option in options),
            )
        if "say" in step:
            return Screen(who=step.get("who", self.speaker), text=step["say"])
        if "say_from" in step:
            # The authored screens this character brought with them. Expanding
            # into ordinary say-steps means the rest of the runner never has to
            # know the difference.
            bundle = self.lines.get(step["say_from"], ())
            if bundle:
                self._stack.append(([{"say": line} for line in bundle], 0))
            return None
        if "when" in step:
            branch = step.get("then", []) if evaluate(step["when"], self.context) \
                else step.get("else", [])
            if branch:
                self._stack.append((list(branch), 0))
            return None
        if "goto" in step:
            target = step["goto"]
            if target not in self.scenes:
                raise ScriptError(f"no such scene: {target!r}")
            self._stack.append((list(self.scenes[target]), 0))
            return None
        if "do" in step:
            from . import actions

            args = {key: resolve(value, self.context)
                    for key, value in (step.get("args") or {}).items()}
            line = actions.run(step["do"], self.context, args, self)
            return Screen(who=self.speaker, text=line) if line else None
        raise ScriptError(f"unknown step: {step!r}")


# -- data -----------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def load(name: str, directory: str | None = None) -> dict:
    """Read one shipped data file.

    Parameters
    ----------
    name : str
        File stem, e.g. ``dialogue``.
    directory : str, optional
        Where to look. Defaults to the plugin's ``data/``.

    Returns
    -------
    dict
        Parsed JSON. An absent file gives an empty mapping rather than
        raising, so a stripped install still starts.
    """
    root = pathlib.Path(directory) if directory else DATA_DIR
    path = root / f"{name}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def scenes(directory: str | None = None) -> dict[str, list]:
    """Every dialogue scene the game ships.

    Parameters
    ----------
    directory : str, optional
        Where to look.

    Returns
    -------
    dict
        Scene id to steps.
    """
    return load("dialogue", directory).get("scenes", {})
