"""The photon tools' side of the Datasets workspace: what they take and what they give back.

The tools of this family take their photon streams from the workspace (manifest
``accepts[].from_workspace``, :mod:`chisurf.core.plugin.workspace_input`) and never ask for an
input file. Three things repeat across them and live here:

* :func:`example_into_workspace` -- *Load example* writes the demo file, adds it to the workspace
  like a dropped file, and hands it to the tool through its own receive hook, so the example is
  used exactly as the user's data is;
* :func:`register_outputs` -- what a tool wrote (a ``.pto``, vendor photon files, tables) enters
  the workspace as children of the dataset it came from;
* :func:`container_files` -- the files behind a list of addresses (a container member
  ``m000.pto/m000.spc`` is read through its container).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from chisurf.core.plugin.workspace_input import WorkspaceInputMixin

_log = logging.getLogger(__name__)


class NamedWorkspaceInput(WorkspaceInputMixin):
    """The model of one Input section that feeds the ``accepts`` entry *name* of *plugin*.

    :class:`~chisurf.core.plugin.workspace_input.WorkspaceInputMixin` picks a plugin's declaration
    by data kind; a tool with two inputs of the same kind (the stream to split, and a batch queue
    of them) names which one each section feeds. ``spec`` is the section to draw, ``form`` its
    state.
    """

    def __init__(
        self,
        plugin: str,
        name: str,
        app: Any,
        *,
        height: float | None = None,
        filter_box: bool = True,
    ) -> None:
        import json

        from emtk.view_form import FormState

        from chisurf.core.plugin.workspace_input import input_section, parse

        self.workspace_input_plugin = plugin
        self.workspace_input_app = app
        self.name = name
        self._found = None
        manifest = json.loads((_plugin_dir(plugin) / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest.get("accepts") or []:
            if entry.get("name") == name and entry.get("from_workspace"):
                self._raw = entry
                section = input_section(parse(entry["from_workspace"]), title="")
                for part in section.get("sections", []):
                    if (part.get("options") or {}).get("source") == "workspace_input_rows":
                        if height is not None:
                            part["options"]["height"] = height
                        if not filter_box:  # a compact list too short for a filter box
                            part["options"]["filter"] = False
                self.spec = {"sections": [section]}
                break
        else:
            raise KeyError(f"{plugin} declares no workspace input named {name!r}")
        self.form = FormState()

    def _workspace_input(self):
        if self._found is None:
            from chisurf.core.plugin.handoff import specs_of
            from chisurf.emtk.plugins import manifest

            for spec in specs_of(manifest(self.workspace_input_plugin)):
                if spec.name == self.name and spec.from_workspace is not None:
                    self._found = (spec, spec.from_workspace)
                    break
        return self._found


@functools.cache
def _plugin_dir(plugin: str) -> Path:
    """The folder of the plugin whose manifest ``id`` is *plugin* (its folder name may differ)."""
    import json

    plugins = Path(__file__).resolve().parents[1]
    # Plugins live one or two folders deep (chisurf/plugins/pch, chisurf/plugins/tttr/audifier).
    for manifest in [*plugins.glob("*/manifest.json"), *plugins.glob("*/*/manifest.json")]:
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("id") == plugin:
                return manifest.parent
        except (OSError, ValueError):
            continue
    raise KeyError(plugin)


def container_files(addresses: Iterable[str]) -> list[str]:
    """The distinct files behind *addresses*, in order (a member's container, a file itself)."""
    from chisurf.core.fio.address import container_of

    return list(dict.fromkeys(str(container_of(str(a))) for a in addresses if str(a)))


def add_photons(address: str, *, result_of: str = "", name: str = "") -> Any:
    """Add the photon stream at *address* to the workspace; returns the dataset (``None`` on
    failure, which is logged: the file is there, the row is a convenience)."""
    from chisurf.core.plugin.workspace_input import register_result

    try:
        return register_result(str(address), kind="photons", result_of=result_of, name=name)
    except Exception:  # noqa: BLE001 - never break the tool over the workspace row
        _log.exception("adding %s to the workspace failed", address)
        return None


def photon_addresses(path: str | Path) -> list[str]:
    """The photon streams *path* holds: each stream of a ``.pto`` (``path/<member>``), or the
    vendor file itself; nothing for anything else (a table, a sidecar)."""
    from chisurf.core.fio import staging
    from chisurf.core.fio.pto import SUFFIX as PTO_SUFFIX
    from chisurf.core.fio.pto import Measurement

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == PTO_SUFFIX:
        try:
            with Measurement.open(path, writable=False) as m:
                return [f"{path}/{name}" for name in m.photon_member_names()]
        except Exception:  # noqa: BLE001 - an unreadable container gives no rows
            _log.exception("listing the photon streams of %s failed", path)
            return []
    if suffix in staging.VENDOR_EXTENSIONS:
        return [str(path)]
    return []


def register_outputs(paths: Iterable[str | Path], *, result_of: str = "") -> list[Any]:
    """Register the photon streams among *paths* (a written ``.pto`` or vendor files) in the
    workspace as children of *result_of*; returns the datasets added."""
    from chisurf.core.fio.address import container_of

    added = []
    for path in paths:
        for address in photon_addresses(path):
            # A stream inside a container is named by it (m000.pto/m000.spc), so it never reads
            # like the vendor file it was packed from.
            container = container_of(address)
            name = (
                f"{container.name}/{address[len(str(container)) + 1 :]}"
                if (str(container) != address)
                else ""
            )
            dataset = add_photons(address, result_of=result_of, name=name)
            if dataset is not None:
                added.append(dataset)
    return added


def read_setup(address: str) -> dict:
    """The detector setup a workspace ``setup`` row holds: its JSON object (the definition the
    shared detector editor works on). A file of several named setups (``{"setups": {...}}``)
    gives its first."""
    import json

    from chisurf.core.plugin.workspace_input import read_address

    data = json.loads(Path(read_address(str(address))).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{address} does not hold a detector setup")
    named = data.get("setups")
    if "detectors" not in data and isinstance(named, dict) and named:
        data = next(iter(named.values()))
    return dict(data)


def add_setup(path: str | Path, setup: dict) -> str:
    """Write the detector *setup* to *path* and add it to the workspace as a ``setup`` row;
    returns its address (the path itself when the workspace refused it -- the file still holds it)."""
    import json

    from chisurf.core.plugin.workspace_input import register_result

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(setup, indent=2), encoding="utf-8")
    try:
        row = register_result(str(path), kind="setup")
        return str(getattr(row, "address", "") or path)
    except Exception:  # noqa: BLE001 - the setup still applies; its workspace row is a convenience
        _log.exception("adding %s to the workspace failed", path)
        return str(path)


def register_container(path: str | Path, *, result_of: str = "") -> list[Any]:
    """Register what the container at *path* holds as the shell's drop lists it -- its photon
    streams and its burst runs -- as children of *result_of*; returns the datasets added."""
    from chisurf.core.fio.classify import container_entries
    from chisurf.core.plugin.workspace_input import register_result

    path = Path(path)
    added = []
    try:
        entries = container_entries(path)
    except Exception:  # noqa: BLE001 - an unreadable container gives no rows
        _log.exception("listing %s failed", path)
        return added
    for kind, address in entries:
        member = address[len(str(path)) + 1 :] if address != str(path) else ""
        name = f"{path.name}/{member}" if member else path.name
        try:
            added.append(register_result(address, kind=kind, result_of=result_of, name=name))
        except Exception:  # noqa: BLE001 - the container is there; the row is a convenience
            _log.exception("adding %s to the workspace failed", address)
    return added


def example_into_workspace(
    path: str | Path,
    receive: Callable[[Any, dict], Any],
    app: Any,
    *,
    key: str = "file",
    many: bool = False,
    extra: dict | None = None,
) -> Any:
    """Add the example at *path* to the workspace and hand it to *receive* (the tool's own hook)
    as the workspace would: ``{key: address (or [address]), "datasets": [uid], **extra}``.

    Returns the dataset added (``None`` when the workspace refused it; the tool still gets the file).
    """
    dataset = add_photons(str(path))
    uid = str(getattr(dataset, "unique_identifier", "") or "") if dataset is not None else ""
    payload: dict[str, Any] = dict(extra or {})
    payload[key] = [str(path)] if many else str(path)
    payload["datasets"] = [uid] if uid else []
    receive(app, payload)
    return dataset


__all__ = [
    "NamedWorkspaceInput",
    "add_photons",
    "add_setup",
    "container_files",
    "example_into_workspace",
    "photon_addresses",
    "read_setup",
    "register_container",
    "register_outputs",
]
