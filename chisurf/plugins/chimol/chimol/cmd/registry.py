"""Declarative command registry for the ChiMOL command language.

A command is any method decorated with :func:`command`; the decorator tags the
function with a :class:`CommandInfo`. At ``Cmd`` construction,
:func:`collect_commands` walks the instance's class hierarchy, binds every tagged
method, and returns a ``{name -> CommandSpec}`` registry plus an abbreviation
index. This mirrors PyMOL's ``keyword`` table (name -> callable + parse mode) but
uses ordinary Python method signatures instead of per-command metadata.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandInfo:
    """Static registration info attached to a decorated command function."""

    name: str
    aliases: tuple[str, ...] = ()
    mode: str = "normal"  # "normal" | "raw1" | "raw2"


@dataclass
class CommandSpec:
    """A bound, dispatchable command."""

    name: str
    func: Callable[..., object]  # bound method
    mode: str
    aliases: tuple[str, ...] = ()
    doc: str = ""


def command(
    name: str,
    *,
    aliases: Sequence[str] = (),
    mode: str = "normal",
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Register the decorated method as the command ``name``.

    Parameters
    ----------
    name:
        The primary command name (e.g. ``"zoom"``).
    aliases:
        Alternative names dispatching to the same function (e.g. ``bg_colour``).
    mode:
        Argument-parsing mode: ``"normal"`` (comma/keyword split) or
        ``"raw1"``/``"raw2"`` (after 1 or 2 normal args, the rest of the line is a
        single verbatim string — for ``alter``/``iterate``/``set``/``label``).
    """
    info = CommandInfo(name=name, aliases=tuple(aliases), mode=mode)

    def _decorate(fn: Callable[..., object]) -> Callable[..., object]:
        fn._command_info = info  # type: ignore[attr-defined]
        return fn

    return _decorate


class Shortcut:
    """Minimal-unique-prefix name index (PyMOL ``Shortcut`` equivalent).

    ``interpret("zo")`` returns ``"zoom"`` when unambiguous, the exact name when
    it is a full match, a list of candidates when ambiguous, or ``None``.
    """

    def __init__(self, names: Sequence[str] = ()) -> None:
        self._names: set[str] = set()
        for n in names:
            self.add(n)

    def add(self, name: str) -> None:
        """Register ``name`` as a resolvable command name."""
        self._names.add(name)

    def interpret(self, key: str):
        """Resolve ``key`` to a full name, a candidate list, or ``None``."""
        if key in self._names:
            return key
        candidates = [n for n in self._names if n.startswith(key)]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            return None
        return sorted(candidates)


@dataclass
class Registry:
    """Holds the command specs and the abbreviation index."""

    specs: dict[str, CommandSpec] = field(default_factory=dict)
    shortcut: Shortcut = field(default_factory=Shortcut)

    def names(self) -> list[str]:
        """Return every registered command name and alias, sorted."""
        return sorted(self.specs.keys())

    def resolve(self, name: str):
        """Return the CommandSpec for ``name`` (exact, alias or unique prefix)."""
        key = name.lower()
        spec = self.specs.get(key)
        if spec is not None:
            return spec
        hit = self.shortcut.interpret(key)
        if isinstance(hit, str):
            return self.specs.get(hit)
        return None


def collect_commands(instance: object) -> Registry:
    """Build a :class:`Registry` from all ``@command``-decorated methods.

    Walks the instance's MRO; a name defined by a more-derived class wins, and
    aliases register additional keys pointing at the same spec.
    """
    registry = Registry()
    seen: set[str] = set()
    for klass in type(instance).__mro__:
        for attr_name, attr in list(vars(klass).items()):
            info = getattr(attr, "_command_info", None)
            if info is None or attr_name in seen:
                continue
            seen.add(attr_name)
            bound = getattr(instance, attr_name)
            spec = CommandSpec(
                name=info.name,
                func=bound,
                mode=info.mode,
                aliases=info.aliases,
                doc=(attr.__doc__ or "").strip(),
            )
            for key in (info.name, *info.aliases):
                lk = key.lower()
                # Do not clobber a name already registered by a more-derived class.
                registry.specs.setdefault(lk, spec)
                registry.shortcut.add(lk)
    return registry


__all__ = [
    "CommandInfo",
    "CommandSpec",
    "Registry",
    "Shortcut",
    "command",
    "collect_commands",
]
