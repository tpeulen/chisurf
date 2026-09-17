"""Resolve declared plugin dependencies into a boot order.

Plugin registration used to run in filesystem order, which meant a plugin whose
sibling had not been imported yet failed inside a ``try`` and vanished -- from a
menu, from the service dispatcher, from the CLI -- with nothing naming the
cause. This module turns the ``requires`` maps in the manifests into an order
that puts a dependency before its dependants, and reports what does not add up.

**It never raises.** A missing dependency, a bound that does not hold, even a
cycle: each is recorded and the boot continues in a deterministic order. The
application is a desktop tool that must start even when a plugin in
``~/.chisurf/plugins`` is wrong, so runtime degrades and *the guardrail test* is
where these become failures.

Ordering uses ``requires`` only. ``optional_requires`` records coupling that
fires after boot -- a click, a lazy import -- so it constrains nothing, and
leaving it out is what keeps the graph acyclic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from chisurf.core.plugin.manifest import ANY_VERSION, is_satisfied_by

_log = logging.getLogger(__name__)


@dataclass
class DependencyReport:
    """The resolved order, and everything that did not add up.

    Attributes
    ----------
    order : list of str
        Plugin ids, dependencies before dependants.
    missing : dict
        ``{plugin_id: [required ids that are not installed]}``.
    out_of_bounds : dict
        ``{plugin_id: ["target 1.0.0 does not satisfy >=2.0", ...]}``.
    cycles : list of list of str
        Each entry is a set of ids that mutually depend, in id order. Empty in a
        healthy tree.
    unknown : dict
        ``{plugin_id: [ids named in optional_requires that do not exist]}``.
        Separate from ``missing`` because an absent optional target is only worth
        a warning when it is also not a typo -- and a typo is indistinguishable
        from an uninstalled plugin, so both land here.

    """

    order: list[str] = field(default_factory=list)
    missing: dict[str, list[str]] = field(default_factory=dict)
    out_of_bounds: dict[str, list[str]] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)
    unknown: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether the graph resolved with nothing to report."""
        return not (self.missing or self.out_of_bounds or self.cycles or self.unknown)

    def problems(self) -> list[str]:
        """Every problem as a human-readable line, in a stable order."""
        lines: list[str] = []
        for plugin_id, targets in sorted(self.missing.items()):
            for target in targets:
                lines.append(f"{plugin_id}: requires {target!r}, which is not installed")
        for plugin_id, notes in sorted(self.out_of_bounds.items()):
            for note in notes:
                lines.append(f"{plugin_id}: {note}")
        for cycle in self.cycles:
            lines.append("dependency cycle: " + " -> ".join(cycle + [cycle[0]]))
        for plugin_id, targets in sorted(self.unknown.items()):
            for target in targets:
                lines.append(f"{plugin_id}: optionally requires {target!r}, which is not installed")
        return lines


def _requirement_maps(manifest: Any) -> tuple[dict[str, str], dict[str, str]]:
    """The ``(requires, optional_requires)`` pair of a manifest or plain dict."""
    if isinstance(manifest, dict):
        return manifest.get("requires") or {}, manifest.get("optional_requires") or {}
    return getattr(manifest, "requires", {}) or {}, getattr(manifest, "optional_requires", {}) or {}


def _identity(manifest: Any) -> tuple[str, str]:
    """The ``(id, version)`` pair of a manifest or plain dict."""
    if isinstance(manifest, dict):
        return str(manifest.get("id", "")), str(manifest.get("version", ""))
    return str(getattr(manifest, "id", "")), str(getattr(manifest, "version", ""))


def resolve(manifests: Iterable[Any]) -> DependencyReport:
    """Order plugins so every hard dependency precedes its dependants.

    Parameters
    ----------
    manifests : iterable
        :class:`~chisurf.core.plugin.manifest.PluginManifest` objects, or the
        plain dicts they parse from.

    Returns
    -------
    DependencyReport
        The order plus every problem found. Never raises: an unresolvable graph
        still yields a complete, deterministic ``order``.

    """
    by_id: dict[str, Any] = {}
    for manifest in manifests:
        plugin_id, _ = _identity(manifest)
        if plugin_id:
            by_id[plugin_id] = manifest

    report = DependencyReport()
    hard: dict[str, set[str]] = {}

    for plugin_id, manifest in by_id.items():
        requires, optional = _requirement_maps(manifest)
        satisfied: set[str] = set()

        for target, specifier in sorted(requires.items()):
            if target not in by_id:
                report.missing.setdefault(plugin_id, []).append(target)
                continue
            satisfied.add(target)
            _, target_version = _identity(by_id[target])
            if not is_satisfied_by(specifier, target_version):
                report.out_of_bounds.setdefault(plugin_id, []).append(
                    f"requires {target} {specifier}, but {target} is {target_version}"
                )

        for target, specifier in sorted(optional.items()):
            if target not in by_id:
                report.unknown.setdefault(plugin_id, []).append(target)
                continue
            _, target_version = _identity(by_id[target])
            if specifier != ANY_VERSION and not is_satisfied_by(specifier, target_version):
                report.out_of_bounds.setdefault(plugin_id, []).append(
                    f"optionally requires {target} {specifier}, but {target} is {target_version}"
                )

        hard[plugin_id] = satisfied

    report.order = _kahn(hard, report)
    return report


def _kahn(hard: dict[str, set[str]], report: DependencyReport) -> list[str]:
    """Topological order of *hard*, degrading rather than raising on a cycle.

    Ties are broken by id so the order is reproducible across machines and runs;
    filesystem order is what this replaces, so inheriting any of it would defeat
    the point.
    """
    ordered: list[str] = []
    remaining = set(hard)
    completed: set[str] = set()

    while remaining:
        ready = sorted(plugin_id for plugin_id in remaining if hard[plugin_id] <= completed)
        if not ready:
            # Everything left is in, or behind, a cycle. Record the strongly
            # blocked set and release it in id order so boot still finishes.
            blocked = sorted(remaining)
            report.cycles.append(blocked)
            ordered.extend(blocked)
            break
        for plugin_id in ready:
            ordered.append(plugin_id)
            completed.add(plugin_id)
            remaining.discard(plugin_id)

    return ordered


def log_problems(report: DependencyReport, logger: logging.Logger | None = None) -> None:
    """Emit one warning per problem.

    A plugin that quietly does not work is the failure this whole mechanism
    exists to end, so every problem gets its own line naming the plugin, the
    target and the reason -- never a single summary count.
    """
    log = logger or _log
    for line in report.problems():
        log.warning("plugin dependencies -- %s", line)


def ordered_manifests(manifests: Iterable[Any]) -> tuple[list[Any], DependencyReport]:
    """Sort *manifests* into boot order.

    Returns
    -------
    tuple
        ``(sorted manifests, report)``. Manifests whose id is empty or duplicated
        keep their relative input order at the end, so nothing is ever dropped by
        sorting.

    """
    items = list(manifests)
    report = resolve(items)
    rank = {plugin_id: index for index, plugin_id in enumerate(report.order)}
    return (
        sorted(items, key=lambda m: rank.get(_identity(m)[0], len(rank))),
        report,
    )
