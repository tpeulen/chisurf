"""The export gate: a project that leaves the machine must carry its data, or say it does not.

A ChiSurf project links its large data files (:mod:`chisurf.core.project.links`). Copied to another
machine -- a deposit, a colleague -- those links point nowhere. Before an export that leaves the
machine, :func:`check` lists every project under a folder that still links data (or cannot find
it); a Zenodo deposit refuses to upload such a record until the projects are made self-contained
(:mod:`chisurf.core.project.link_repair`) or the user explicitly overrides the gate, and the
override is written into the deposit (:func:`override_note`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chisurf.core.project import links
from chisurf.core.project.pto import PROJECT_SUFFIX

__all__ = ["ProjectGate", "blocker_lines", "check", "make_self_contained", "override_note"]


@dataclass(frozen=True)
class ProjectGate:
    """A project that would leave without some of its data."""

    path: Path
    linked: list[links.LinkReport] = field(default_factory=list)

    @property
    def unresolved(self) -> list[links.LinkReport]:
        """The linked data files that are not even found here."""
        return [r for r in self.linked if not r.ok]

    @property
    def label(self) -> str:
        """The project's name without its file extension (deposit text never names the format)."""
        name = self.path.name
        return name[: -len(PROJECT_SUFFIX)] if name.endswith(PROJECT_SUFFIX) else self.path.stem


def _project_files(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if root.is_file():
        return [root] if root.name.endswith(PROJECT_SUFFIX) else []
    return sorted(p for p in root.rglob(f"*{PROJECT_SUFFIX}") if p.is_file())


def check(folder: str | Path) -> list[ProjectGate]:
    """Every project under *folder* (or the project *folder*) that is not self-contained."""
    from chisurf.core.project.project import Project

    out = []
    for path in _project_files(folder):
        try:
            project = Project.load(path)
        except Exception as exc:  # noqa: BLE001 - a broken project is a finding of its own
            out.append(
                ProjectGate(path, [links.LinkReport("", path.name, "missing", str(exc), False, "")])
            )
            continue
        reports = links.report(project.datasets, path.parent, project_path=path)
        linked = [r for r in reports if not r.embedded]
        if linked:
            out.append(ProjectGate(path, linked))
    return out


def blocker_lines(gates: list[ProjectGate]) -> list[str]:
    """One blocking line per project: which data it links, which of those are not found."""
    lines = []
    for gate in gates:
        names = ", ".join(r.name or Path(r.location).name for r in gate.linked[:4])
        more = f" and {len(gate.linked) - 4} more" if len(gate.linked) > 4 else ""
        line = (
            f"project {gate.label}: {len(gate.linked)} data file(s) only linked, not inside it "
            f"({names}{more}) -- make it self-contained, or override"
        )
        if gate.unresolved:
            line += f"; {len(gate.unresolved)} of them are not found here either"
        lines.append(line)
    return lines


def override_note(gates: list[ProjectGate]) -> str:
    """The sentence a deposit carries when its projects were uploaded without their data."""
    parts = []
    for gate in gates:
        names = ", ".join(Path(r.location).name or r.name for r in gate.linked)
        parts.append(f"{gate.label} ({names})")
    return (
        "Incomplete analysis projects: the following ChiSurf analysis projects reference data "
        "files that are not part of this deposit: " + "; ".join(parts) + "."
    )


def make_self_contained(gates: list[ProjectGate]) -> dict[str, list[str]]:
    """Embed every link of each project (each project file rewritten); what failed, by project."""
    from chisurf.core.project.link_repair import LinkRepairModel, ProjectFileSource

    failures: dict[str, list[str]] = {}
    for gate in gates:
        source = ProjectFileSource(gate.path)
        failed = LinkRepairModel(source).make_self_contained()
        if failed:
            failures[gate.label] = failed
        else:
            source.save()
    return failures
