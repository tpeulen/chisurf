"""One registry of what the compiled libraries and chisurf can do.

tttrlib and IMP.bff each publish a registry with the same mechanism and the same
entry shape (``tttrlib.registry()``, ``IMP.bff.registry()``: ``{category: {name:
entry}}``, every entry with ``name``, ``label``, ``summary``, ``description``, a
JSON Schema ``params_schema``, ``capability`` and ``provider``). chisurf adds the
few things only it implements -- a Python sampler with no compiled kernel, say --
by registering entries of that same shape next to the code (:func:`register`).
This module merges the three, so a selector, a form or a dispatcher reads one
table and nothing is listed by hand: a capability added to either library appears
here on upgrade.

Merging: providers are read in the order tttrlib, IMP.bff, chisurf. A key already
present in a category keeps its first entry, except that a chisurf registration
may *extend* a compiled entry it names in ``"kernel"`` -- see
:func:`register`.

Written 2026-09-15.
"""

from __future__ import annotations

import copy
import difflib
import functools
import typing

#: chisurf's own registrations: category -> {key: entry}, in registration order.
_LOCAL: typing.Dict[str, typing.Dict[str, dict]] = {}


@functools.lru_cache(maxsize=None)
def _compiled() -> typing.Tuple[typing.Tuple[str, typing.Dict[str, typing.Dict[str, dict]]], ...]:
    """The compiled libraries' registries, read once per process."""
    out = []
    try:
        import tttrlib
        getter = getattr(tttrlib, "registry", None)
        if getter is not None:
            out.append(("tttrlib", getter()))
        else:
            legacy = getattr(getattr(tttrlib, "TTTR", None), "burst_search_algorithms", None)
            if legacy is not None:
                # tttrlib older than the general registry published burst searches only
                out.append(("tttrlib", {"burst_search": legacy()}))
    except Exception:
        pass
    try:
        import IMP.bff as bff
        getter = getattr(bff, "registry", None)
        if getter is not None:
            out.append(("imp.bff", getter()))
    except Exception:
        pass
    return tuple(out)


def refresh() -> None:
    """Forget the cached compiled registries (after a plugin loaded, say)."""
    _compiled.cache_clear()


def register(category: str, key: str, entry: typing.Mapping[str, typing.Any]) -> dict:
    """Register one chisurf entry, next to the code it describes.

    The entry has the shape the compiled registries use (``label``, ``summary``,
    ``description``, ``params_schema``, ...); ``provider`` is ``"chisurf"``.

    An entry that names a compiled entry of the same category in ``"kernel"`` is
    an implementation of it: the merged entry starts from the compiled one (its
    requirements, schema, references, default warm-up ...) and the keys given here
    override or add to it. Its ``aliases`` are its own plus the kernel's key and
    aliases, so a name either library uses resolves to it.

    Returns the entry as registered. Raises ``ValueError`` on a duplicate key.
    """
    table = _LOCAL.setdefault(category, {})
    if key in table:
        raise ValueError(f"{category} {key!r} is already registered")
    e = dict(entry)
    e.setdefault("name", key)
    e.setdefault("capability", category)
    e.setdefault("provider", "chisurf")
    table[key] = e
    return e


def _merged() -> typing.Dict[str, typing.Dict[str, dict]]:
    root: typing.Dict[str, typing.Dict[str, dict]] = {}
    implemented: typing.Dict[str, typing.Set[str]] = {}
    for category, local in _LOCAL.items():
        implemented[category] = {e["kernel"] for e in local.values() if e.get("kernel")}
    for _, reg in _compiled():
        for category, entries in reg.items():
            target = root.setdefault(category, {})
            for key, entry in entries.items():
                if key in target or key in implemented.get(category, ()):
                    continue
                target[key] = entry
    compiled_all = {}
    for _, reg in _compiled():
        for category, entries in reg.items():
            for key, entry in entries.items():
                compiled_all.setdefault((category, key), entry)
    for category, local in _LOCAL.items():
        target = root.setdefault(category, {})
        for key, entry in local.items():
            if key in target:
                continue
            kernel = entry.get("kernel")
            base = compiled_all.get((category, kernel)) if kernel else None
            if base is not None:
                merged = copy.deepcopy(base)
                merged.update(entry)
                aliases = list(entry.get("aliases", ()))
                for a in [kernel] + list(base.get("aliases", ())):
                    if a != key and a not in aliases:
                        aliases.append(a)
                merged["aliases"] = aliases
                merged["name"] = key
                merged["kernel_provider"] = base.get("provider")
                target[key] = merged
            elif kernel:
                # the kernel is not in this build: the Python implementation stands alone
                target[key] = dict(entry, kernel_missing=True)
            else:
                target[key] = dict(entry)
    return root


def registry(category: typing.Optional[str] = None):
    """The merged registry, ``{category: {name: entry}}``, or one category.

    An unknown category is an empty dict, so a caller can test availability
    without catching.
    """
    root = _merged()
    if category is None:
        return root
    return root.get(category, {})


def resolve(category: str, name: str) -> str:
    """The key of an entry named by its key or any of its aliases.

    Raises ``ValueError`` naming the closest matches.
    """
    entries = registry(category)
    key = str(name or "").strip()
    if key in entries:
        return key
    lowered = key.lower()
    for k, e in entries.items():
        if k.lower() == lowered or lowered in [str(a).lower() for a in e.get("aliases", ())]:
            return k
    known = sorted(set(entries) | {a for e in entries.values() for a in e.get("aliases", ())})
    close = difflib.get_close_matches(key, known, n=4)
    raise ValueError(
        f"unknown {category.replace('_', ' ')} {name!r}"
        + (f"; did you mean: {', '.join(close)}?" if close else f"; available: {sorted(entries)}")
    )


def describe(category: str, name: str) -> dict:
    """One entry, by key or alias."""
    return registry(category)[resolve(category, name)]


def defaults(category: str, name: str) -> dict:
    """The ``params_schema`` defaults of an entry, ``{parameter: value}``."""
    schema = describe(category, name).get("params_schema") or {}
    return {
        prop: spec["default"]
        for prop, spec in (schema.get("properties") or {}).items()
        if isinstance(spec, dict) and "default" in spec
    }
