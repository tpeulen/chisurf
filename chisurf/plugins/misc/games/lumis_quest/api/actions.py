"""What the world is allowed to do to you, as a registry rather than a switch.

Every consequence in the game -- a seal granted, a team restored, a filter
re-ground, a fight started, a crossing opened -- is a named action here, and the
scripts under ``data/`` select from this list by name. Nothing in the renderer
decides what a shrine does.

Two rules make this worth having rather than merely indirect:

* **An action is small, pure where it can be, and testable alone.** It takes the
  run and its arguments; it returns either nothing or one line to show. It never
  draws.
* **Anything the host must do is a request, not a call.** Starting a fight,
  opening a menu, moving the player between manifolds -- the action puts a
  :class:`.engine.Request` on the runner and returns. The engine stays Qt-free
  and the host stays in charge of its own loop.
"""

from __future__ import annotations

from typing import Callable

from . import tiers as tiers_api

#: Action name -> handler. A handler takes ``(context, args, runner)`` and may
#: return one line of text to show.
ACTIONS: dict[str, Callable] = {}


def action(name: str):
    """Register an action under a name scripts can use.

    Parameters
    ----------
    name : str
        The key that appears in a script's ``do`` step.

    Returns
    -------
    callable
        A decorator.
    """

    def register(function):
        ACTIONS[name] = function
        return function

    return register


def run(name: str, context, args: dict, runner) -> str:
    """Dispatch one action.

    Parameters
    ----------
    name : str
        Registered action name.
    context : object
        The run.
    args : dict
        Whatever the action takes.
    runner : chisurf.plugins.misc.games.lumis_quest.api.engine.Runner
        For posting host requests.

    Returns
    -------
    str
        A line to show, or empty.

    Raises
    ------
    chisurf.plugins.misc.games.lumis_quest.api.engine.ScriptError
        If no such action is registered. Loud, because a mistyped action in a
        story file is a consequence that silently never happens.
    """
    from .engine import ScriptError

    handler = ACTIONS.get(name)
    if handler is None:
        raise ScriptError(f"unknown action {name!r}")
    return handler(context, args or {}, runner) or ""


def _request(runner, kind: str, **args) -> None:
    """Ask the host to do something.

    Parameters
    ----------
    runner : Runner
        Where the request queues.
    kind : str
        What is wanted.
    **args
        Whatever that needs.
    """
    from .engine import Request

    runner.requests.append(Request(kind=kind, args=args))


# -- story ----------------------------------------------------------------

@action("flag")
def _set_flag(context, args, runner) -> str:
    """Record that a story beat has been witnessed."""
    context.flags.add(args["name"])
    return ""


@action("pledge")
def _pledge(context, args, runner) -> str:
    """Commit the run to one of the three orders."""
    context.pledge(args["order"])
    return ""


@action("seal")
def _grant_seal(context, args, runner) -> str:
    """Grant a Warden's seal, which is a licence tier."""
    key = args["warden"]
    context.grant_seal(key)
    warden = tiers_api.BY_KEY.get(key)
    if warden is None:
        return ""
    return (f"{warden.seal} is yours. You may now unbind up to "
            f"{tiers_api.TIER_NAMES[tiers_api.licence(context.seals)]}.")


@action("companion")
def _companion(context, args, runner) -> str:
    """The hound joins, which is its own beat."""
    context.has_lumi = True
    context.flags.add("the-hound")
    return ""


# -- services -------------------------------------------------------------

@action("restore")
def _restore(context, args, runner) -> str:
    """Bring the team back up, in full or in part."""
    fraction = float(args.get("fraction", 1.0))
    context.restore_team(fraction)
    return args.get("text", "Your team comes back up to full.")


@action("save")
def _save(context, args, runner) -> str:
    """Write the run down."""
    _request(runner, "save")
    return args.get("text", "")


@action("rumour")
def _rumour(context, args, runner) -> str:
    """Say something true about somewhere else.

    A rumour that points at nothing is worse than silence, so this reads the
    world rather than a list of flavour lines.
    """
    heard = context.rumours()
    if not heard:
        return "Quiet week."
    return heard[context.tick % len(heard)]


@action("supply")
def _supply(context, args, runner) -> str:
    """Hand over a piece of optical gear suited to the team."""
    part = context.offer_gear(args.get("kind", "match"))
    if part is None:
        return "Nothing here you cannot already see through."
    return f"You take {part.summary}."


@action("grind")
def _grind(context, args, runner) -> str:
    """Re-grind the fitted filter narrower: it passes less and sees better."""
    part = context.grind_filter()
    if part is None:
        return "Nothing fitted to grind."
    return f"Re-ground: {part.summary}."


# -- host requests --------------------------------------------------------

@action("rekindle")
def _rekindle(context, args, runner) -> str:
    """Give a shelved animal a label back, which is the inverse of unbinding."""
    given = context.rekindle(args.get("species", ""))
    if given is None:
        return "You have nothing to give it."
    species, label = given
    return (f"You fit {label.name}. The {species.name} comes back up out of "
            f"the ash, and follows you.")


@action("battle")
def _battle(context, args, runner) -> str:
    """Ask the host to start a fight."""
    _request(runner, "battle", **args)
    return ""


@action("cross")
def _cross(context, args, runner) -> str:
    """Ask the host to move the player between manifolds."""
    _request(runner, "cross", **args)
    return ""


@action("menu")
def _menu(context, args, runner) -> str:
    """Ask the host to open one of the menu tabs."""
    _request(runner, "menu", **args)
    return ""


@action("join")
def _join(context, args, runner) -> str:
    """Step into a conversation two people were having without you."""
    _request(runner, "join", **args)
    return ""


@action("read")
def _read(context, args, runner) -> str:
    """Ask the host to open the page a building holds."""
    _request(runner, "read", **args)
    return ""
