"""The burst tools' side of the Datasets workspace: what they read, and what they write back.

A burst tool takes a **burst run** from the workspace -- a run of its photon dataset's analysis
container in the project (``<name>.pto/<run>``, shown under its photon stream;
:mod:`chisurf.core.project.analysis`) -- as an address (:mod:`chisurf.core.fio.address`), never from
a file dialog. What it computes per burst is a companion table of that run (``<run>/<table>``),
written into the same container and read back with the run by ndX's reader; it is not a dataset of
its own.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from chisurf.core.plugin.workspace_input import WorkspaceInputMixin

_log = logging.getLogger(__name__)

__all__ = [
    "NamedWorkspaceInput",
    "input_spec",
    "is_burst_source",
    "register_container",
    "run_of",
]


def is_burst_source(address) -> bool:
    """True for a legacy burst-analysis folder or a measurement container (or a run in one)."""
    from chisurf.core.fio.fluorescence import burst_tree

    path = Path(str(address))
    return path.is_dir() or burst_tree.is_container_path(path)


def run_of(address) -> str:
    """The run named by *address* (``m000.pto/<run>`` -> ``<run>``); empty for a folder or a bare container."""
    from chisurf.core.fio.address import split_address

    _container, member = split_address(str(address))
    return str(member or "").strip("/")


class NamedWorkspaceInput(WorkspaceInputMixin):
    """An Input section bound to one named ``accepts`` entry of the plugin.

    The generic mixin takes the plugin's first workspace entry (of a kind); a tool with several
    inputs of the same kind -- the bursts, a measured IRF and a measured background are all
    workspace data -- names the entry each section feeds (:attr:`workspace_input_handoff`).
    """

    workspace_input_handoff: str = ""

    def __init__(self, plugin: str = "", handoff: str = "", app: Any = None) -> None:
        if plugin:
            self.workspace_input_plugin = plugin
        if handoff:
            self.workspace_input_handoff = handoff
        self.workspace_input_app = app

    def _workspace_input(self):
        from chisurf.core.plugin.handoff import specs_of
        from chisurf.emtk.plugins import manifests

        for spec in specs_of(manifests().get(self.workspace_input_plugin)):
            if spec.name == self.workspace_input_handoff and spec.from_workspace is not None:
                return spec, spec.from_workspace
        return None


def input_spec(manifest_path, handoff: str = "", *, title: str = "Input") -> dict:
    """The generated Input section (an AutoForm spec) of the ``accepts`` entry *handoff* of the
    manifest at *manifest_path* (the first workspace entry when *handoff* is empty)."""
    import json

    from chisurf.core.plugin.handoff import specs_of
    from chisurf.core.plugin.workspace_input import input_section

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for spec in specs_of(manifest):
        if spec.from_workspace is not None and (not handoff or spec.name == handoff):
            return {"sections": [input_section(spec.from_workspace, title=title)]}
    return {"sections": []}


def register_container(container) -> list:
    """Put a measurement container into the workspace the way the drop does: its photon streams,
    and its burst runs as children of the stream (a demo the tool generated enters this way)."""
    from chisurf.core.fio.classify import container_entries
    from chisurf.core.plugin.workspace_input import register_result

    added, stream = [], None
    for kind, address in container_entries(container):
        if kind == "photons":
            stream = register_result(address, kind="photons")
            added.append(stream)
        elif kind == "bursts":
            added.append(
                register_result(
                    address,
                    kind="bursts",
                    result_of=getattr(stream, "unique_identifier", "") if stream else "",
                )
            )
    return added
