"""A plugin takes its input from the Datasets workspace, never from a file dialog.

Data enters ChiSurf one way -- dropped on the window -- and lives in the workspace (and the
project). A plugin says what it takes in its manifest, on one of its ``accepts`` hand-off kinds::

    "accepts": [{
        "name": "tttr_trace", "receive": "...gui.app:receive_trace", "required": ["file"],
        "from_workspace": {"kinds": ["photons"], "key": "file"}
    }]

``from_workspace`` (:class:`WorkspaceInput`) names the data ``kinds`` (:mod:`chisurf.core.data_kinds`)
and/or ``experiments`` it takes, for images which ``representations`` (``photons``/``intensity``),
whether it takes ``many`` datasets at once, the payload ``key`` the chosen addresses go under, and
whether the shared detector setup comes along (``with_setup``). Everything else is generic:

* the shell feeds a plugin from the workspace -- *Open in…* on a row, or a row dragged onto the
  plugin (:meth:`chisurf.emtk.main_app.EmtkShellApp.feed_from_workspace`), through the existing
  hand-off and the plugin's own receive hook;
* the plugin's form shows a generated *Input* section listing the workspace rows it takes
  (:func:`input_section`, :class:`WorkspaceInputMixin`, :func:`with_workspace_input`);
* what the plugin writes goes back into the workspace with :func:`register_result`.

A payload value is an **address** (:mod:`chisurf.core.fio.address`): a linked dataset's file or
container member (``m000.pto/m000.spc``, ``m000.pto/<run>``), or ``@<uid>`` for a dataset that lives
only in the session (a decay read from a text file, a fitted curve). The receive hook resolves it
with :func:`resolve_dataset` / :func:`read_address`. This module imports no toolkit.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

_log = logging.getLogger(__name__)

__all__ = [
    "SESSION_PREFIX",
    "WorkspaceInput",
    "WorkspaceInputMixin",
    "address_of",
    "build_payload",
    "input_section",
    "matches",
    "parse",
    "plugins_accepting",
    "read_address",
    "register_result",
    "resolve_dataset",
    "spec_for",
    "validate",
    "with_workspace_input",
    "workspace_rows",
]

#: The address of a dataset that lives only in the session: ``@<uid>`` (``project.cs.pto/@<uid>``
#: names the same dataset once the project is saved).
SESSION_PREFIX = "@"

_KEYS = {"kinds", "experiments", "representations", "many", "key", "with_setup", "defaults"}


@dataclass
class WorkspaceInput:
    """What a hand-off kind takes from the workspace (``accepts[].from_workspace``)."""

    #: Data kinds taken (``photons``, ``decay``, ``bursts``, ...); empty: any kind of the experiments.
    kinds: list[str] = field(default_factory=list)
    #: Experiment names taken (``TCSPC``, ``Single photon counting``, ...); empty: any.
    experiments: list[str] = field(default_factory=list)
    #: For images: ``photons`` and/or ``intensity``; empty: either.
    representations: list[str] = field(default_factory=list)
    #: Whether several datasets go in one payload (a list under :attr:`key`).
    many: bool = False
    #: The payload key the chosen address (or list of addresses) goes under.
    key: str = "address"
    #: Whether a detector/channel setup goes along: a workspace row of kind ``setup`` chosen beside
    #: the data travels as ``setup`` (its address).
    with_setup: bool = False
    #: Payload values filled in when the workspace does not provide them (a bin width, a window).
    defaults: dict = field(default_factory=dict)


def validate(raw: Any, prefix: str = "from_workspace") -> list[str]:
    """The problems of a raw ``from_workspace`` declaration (empty when it is well formed)."""
    from chisurf.core.data_kinds import KINDS

    if not isinstance(raw, dict):
        return [f"{prefix} must be an object"]
    errors = [f"{prefix}: unknown field {key!r}" for key in raw if key not in _KEYS]
    for name in ("kinds", "experiments", "representations"):
        value = raw.get(name, [])
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            errors.append(f"{prefix}.{name} must be an array of strings")
    unknown = [k for k in raw.get("kinds", []) or [] if isinstance(k, str) and k not in KINDS]
    if unknown:
        errors.append(f"{prefix}.kinds names unknown kinds {unknown}")
    if not (raw.get("kinds") or raw.get("experiments")):
        errors.append(f"{prefix} must name kinds or experiments")
    bad = [r for r in raw.get("representations", []) or [] if r not in ("photons", "intensity")]
    if bad:
        errors.append(f"{prefix}.representations must be 'photons' or 'intensity', not {bad}")
    for name in ("many", "with_setup"):
        if name in raw and not isinstance(raw[name], bool):
            errors.append(f"{prefix}.{name} must be true or false")
    if "key" in raw and (not isinstance(raw["key"], str) or not raw["key"]):
        errors.append(f"{prefix}.key must be a non-empty string")
    if "defaults" in raw and not isinstance(raw["defaults"], dict):
        errors.append(f"{prefix}.defaults must be an object")
    return errors


def parse(raw: Any) -> WorkspaceInput | None:
    """A :class:`WorkspaceInput` from a raw declaration (``None`` when there is none)."""
    if not isinstance(raw, dict):
        return None
    return WorkspaceInput(
        kinds=[str(k) for k in raw.get("kinds", []) or []],
        experiments=[str(e) for e in raw.get("experiments", []) or []],
        representations=[str(r) for r in raw.get("representations", []) or []],
        many=bool(raw.get("many", False)),
        key=str(raw.get("key") or "address"),
        with_setup=bool(raw.get("with_setup", False)),
        defaults=dict(raw.get("defaults") or {}),
    )


# -- rows and addresses ---------------------------------------------------------------- #
def address_of(dto: dict) -> str:
    """The address a workspace row is handed to a plugin by.

    A linked dataset (photons, a burst run, an image, a setup: it has a ``link_status``) is its file
    or container member; any other dataset lives in the session and is ``@<uid>``.
    """
    if dto.get("address"):
        return str(dto["address"])
    if dto.get("link_status") is not None and dto.get("filename"):
        return str(dto["filename"])
    return f"{SESSION_PREFIX}{dto.get('uid', '')}"


def matches(spec: WorkspaceInput, dto: dict) -> bool:
    """Whether the workspace row *dto* is something *spec* takes."""
    kind = str(dto.get("kind") or "")
    if not kind:
        return False
    if spec.kinds and kind not in spec.kinds:
        return False
    if spec.experiments and str(dto.get("experiment") or "") not in spec.experiments:
        return False
    if spec.representations and kind == "image":
        if str(dto.get("representation") or "") not in spec.representations:
            return False
    return True


def _flatten(dtos: Iterable[dict]) -> list[dict]:
    """Datasets and the members of their groups, one row each (a group itself is not data)."""
    out: list[dict] = []
    for dto in dtos or ():
        members = dto.get("members") or []
        if len(members) > 1:
            out.extend(members)
        elif members and not dto.get("kind"):
            out.extend(members)
        else:
            out.append(dto)
    return out


def _api() -> Any:
    """The session's API (the shell's, when one runs), else a local one."""
    import chisurf as cs

    api = getattr(cs, "api", None)
    if api is None:
        from chisurf.core.api import ChiSurfAPI

        api = ChiSurfAPI(mode="local")
    return api


def _api_rows() -> list[dict]:
    try:
        return list(_api().list_datasets() or [])
    except Exception:  # noqa: BLE001 - no session yet: an empty workspace
        _log.debug("listing the workspace failed", exc_info=True)
        return []


def workspace_rows(spec: WorkspaceInput, dtos: Iterable[dict] | None = None) -> list[dict]:
    """The workspace rows *spec* takes: ``uid``, ``name``, ``kind``, ``kind_label``,
    ``experiment``, ``source`` (file name), ``address`` and ``result_of``."""
    from chisurf.core.data_kinds import KINDS

    rows = []
    for dto in _flatten(_api_rows() if dtos is None else dtos):
        if not (matches(spec, dto) or (spec.with_setup and dto.get("kind") == "setup")):
            continue
        address = address_of(dto)
        found = KINDS.get(str(dto.get("kind") or ""))
        label = f"{found.icon}  {found.label}" if found else ""
        if dto.get("representation"):
            label = f"{label} · {dto['representation']}"
        source = "" if address.startswith(SESSION_PREFIX) else address.replace("\\", "/")
        rows.append(
            {
                "uid": str(dto.get("uid", "")),
                "name": str(dto.get("name", "")),
                "kind": str(dto.get("kind", "")),
                "kind_label": label,
                "experiment": str(dto.get("experiment", "")),
                "source": source.rsplit("/", 1)[-1],
                "address": address,
                "result_of": str(dto.get("result_of", "") or ""),
            }
        )
    return rows


def build_payload(spec: WorkspaceInput, rows: list[dict]) -> dict[str, Any]:
    """The hand-off payload for *rows*: the data rows' address (or list of addresses) under
    :attr:`WorkspaceInput.key`, their uids under ``datasets``, a chosen setup row's address under
    ``setup`` (when the spec takes one), and the declared defaults for the rest."""
    setups = [r for r in rows if spec.with_setup and r.get("kind") == "setup" and not matches(spec, r)]
    data = [r for r in rows if r not in setups]
    if not data:
        raise ValueError("no workspace data chosen")
    if len(data) > 1 and not spec.many:
        raise ValueError("this tool takes one dataset at a time")
    if len(setups) > 1:
        raise ValueError("choose one setup")
    addresses = [address_of(row) for row in data]
    payload: dict[str, Any] = dict(spec.defaults)
    payload[spec.key] = addresses if spec.many else addresses[0]
    payload["datasets"] = [str(row.get("uid", "")) for row in data]
    if setups:
        payload["setup"] = address_of(setups[0])
    return payload


def resolve_dataset(address: str) -> Any:
    """The session dataset named by *address* (``@<uid>``, or a linked dataset's address); ``None``
    when no dataset of the session has it."""
    from chisurf.core.api import dataset_objects

    address = str(address)
    pool: list[Any] = []
    for dataset in dataset_objects():
        pool.append(dataset)
        pool.extend(list(dataset) if hasattr(dataset, "__iter__") and not hasattr(dataset, "x") else [])
    if address.startswith(SESSION_PREFIX):
        uid = address[len(SESSION_PREFIX):]
        return next((d for d in pool if str(getattr(d, "unique_identifier", "")) == uid), None)
    return next((d for d in pool if str(getattr(d, "address", "")) == address), None)


def read_address(address: str) -> str:
    """Where the data of *address* is read from: the address itself, or -- for a linked dataset
    the session holds -- its local read address (an MMFDB object's cached copy)."""
    dataset = resolve_dataset(address)
    read = getattr(dataset, "read_address", None)
    return str(read) if read else str(address)


# -- which plugins take what ------------------------------------------------------------ #
def spec_for(manifest: dict | None, *, kind: str | None = None) -> tuple[Any, WorkspaceInput] | None:
    """The first hand-off spec of *manifest* that takes workspace data (of *kind*, when given),
    with its parsed :class:`WorkspaceInput`."""
    from chisurf.core.plugin.handoff import specs_of

    for spec in specs_of(manifest):
        found = spec.from_workspace
        if found is None:
            continue
        if kind is None or not found.kinds or kind in found.kinds:
            return spec, found
    return None


def plugins_accepting(catalog: dict[str, dict], rows: list[dict]) -> list[tuple[str, Any]]:
    """``[(plugin_id, handoff_spec), ...]`` of the plugins that take every row of *rows*."""
    out = []
    if not rows:
        return out
    from chisurf.core.plugin.handoff import specs_of

    for plugin_id, manifest in sorted(catalog.items()):
        for spec in specs_of(manifest):
            found = spec.from_workspace
            if found is None or (len(rows) > 1 and not found.many):
                continue
            if all(matches(found, row) for row in rows):
                out.append((plugin_id, spec))
                break
    return out


# -- the generated Input section --------------------------------------------------------- #
def input_section(spec: WorkspaceInput, *, title: str = "Input") -> dict:
    """The AutoForm section a plugin's form shows for *spec*: the workspace rows it takes.

    One dataset: picking a row hands it over. Several: rows are selected, then *Use selected*.
    """
    from chisurf.core.data_kinds import KINDS

    kinds = ", ".join(KINDS[k].plural.lower() for k in spec.kinds if k in KINDS) or ", ".join(
        spec.experiments
    )
    table = {
        "type": "custom",
        "key": "data_table",
        "description": (
            f"The {kinds} in the workspace this tool takes. Data enters ChiSurf by dropping files "
            "on the window; pick here what this tool works on."
        ),
        "options": {
            "source": "workspace_input_rows",
            "row_key": "uid",
            "editable": False,
            "height": 110,
            "filter": True,
            "columns": [
                {"key": "name", "title": "Data name", "width": 180,
                 "tooltip": "The dataset's name in the workspace."},
                {"key": "kind_label", "title": "Kind", "width": 120,
                 "tooltip": "What the dataset is (and, for an image, which representation)."},
                {"key": "source", "title": "Source", "width": 160,
                 "tooltip": "The file it comes from; empty for data that lives in the session."},
            ],
        },
    }
    if spec.many:
        table["options"]["selection_attr"] = "workspace_input_selection"
        return {
            "type": "panel",
            "title": title,
            "sections": [
                table,
                {
                    "type": "info",
                    "key": "workspace_input_hint",
                    "source": "workspace_input_hint",
                    "description": "What is chosen, or how to add data.",
                },
                {
                    "type": "button_row",
                    "buttons": [
                        {
                            "action": "workspace_input_use",
                            "label": "Use selected",
                            "description": "Hand the selected workspace data to this tool.",
                        }
                    ],
                },
            ],
        }
    table["options"]["selected_call"] = "workspace_input_selected"
    return {
        "type": "panel",
        "title": title,
        "sections": [
            table,
            {
                "type": "info",
                "key": "workspace_input_hint",
                "source": "workspace_input_hint",
                "description": "What is chosen, or how to add data.",
            },
        ],
    }


def with_workspace_input(spec: dict, inputs: WorkspaceInput, *, title: str = "Input") -> dict:
    """*spec* (a loaded view spec, not modified) with the Input section first, once."""
    out = copy.deepcopy(spec)
    top = out.setdefault("sections", [])

    def present(sections: list) -> bool:
        return any(
            isinstance(s, dict)
            and (
                (s.get("options") or {}).get("source") == "workspace_input_rows"
                or present(s.get("sections") or [])
            )
            for s in sections
        )

    if not present(top):
        top.insert(0, input_section(inputs, title=title))
    return out


class WorkspaceInputMixin:
    """The model half of the generated Input section.

    A plugin's form model inherits this and sets :attr:`workspace_input_plugin` (its id); the
    section reads :meth:`workspace_input_rows`, and a pick hands the chosen rows to the plugin's own
    receive hook (:attr:`workspace_input_app` is the app the hook gets; the model itself by
    default) -- exactly what *Open in…* or a drag from the workspace does.
    """

    workspace_input_plugin: str = ""
    workspace_input_kind: str | None = None
    workspace_input_app: Any = None
    workspace_input_status: str = ""
    #: Called with ``"workspace_input_rows"`` after a pick was handed over (a guided tour awaits it).
    workspace_input_on_used: Any = None

    def _workspace_input(self) -> tuple[Any, WorkspaceInput] | None:
        from chisurf.emtk.plugins import manifests

        return spec_for(manifests().get(self.workspace_input_plugin), kind=self.workspace_input_kind)

    def workspace_input_rows(self) -> list[dict]:
        """The workspace rows this plugin takes (a method: AutoForm calls its sources)."""
        found = self._workspace_input()
        return workspace_rows(found[1]) if found else []

    @property
    def workspace_input_selection(self) -> list:
        return getattr(self, "_workspace_input_selection", [])

    @workspace_input_selection.setter
    def workspace_input_selection(self, value: list) -> None:
        self._workspace_input_selection = list(value or [])

    def workspace_input_hint(self) -> str:
        """What is chosen, or -- an empty workspace -- how data gets in."""
        if self.workspace_input_status:
            return self.workspace_input_status
        if not self.workspace_input_rows():
            return "Nothing in the workspace yet: drop files on the ChiSurf window to add data."
        return "Pick what this tool works on."

    def workspace_input_selected(self, row: Any) -> None:
        """A row picked in a one-dataset Input section: hand it over."""
        if isinstance(row, dict) and row.get("uid"):
            self._workspace_input_deliver([row])

    def workspace_input_use(self) -> None:
        """*Use selected* in a many-dataset Input section."""
        rows = [r for r in self.workspace_input_selection if isinstance(r, dict) and r.get("uid")]
        if rows:
            self._workspace_input_deliver(rows)

    def _workspace_input_deliver(self, rows: list[dict]) -> None:
        found = self._workspace_input()
        if found is None:
            return
        handoff, inputs = found
        from chisurf.core.plugin.handoff import check_payload, deliver

        try:
            payload = build_payload(inputs, rows)
            check_payload(handoff, payload)
            deliver(self.workspace_input_app or self, handoff, payload)
        except Exception as exc:  # noqa: BLE001 - said in the section, never raised into the frame
            _log.exception("handing workspace data to %s failed", self.workspace_input_plugin)
            self.workspace_input_status = f"Could not use it: {exc}"
            return
        names = ", ".join(str(r.get("name", "")) for r in rows[:3])
        self.workspace_input_status = f"Using {names}{'…' if len(rows) > 3 else ''}"
        if callable(self.workspace_input_on_used):
            self.workspace_input_on_used("workspace_input_rows")


# -- results back into the workspace ---------------------------------------------------------- #
def register_result(
    result: Any,
    *,
    kind: str | None = None,
    result_of: str = "",
    name: str = "",
) -> Any:
    """Put what a plugin wrote into the workspace (and so the project), through the API seam.

    *result* is a dataset object (a curve the tool computed: its kind comes from its experiment) or
    an address the tool wrote -- a burst run ``m000.pto/<run>``, a map or image, a setup file --
    read by the experiment that reads *kind* (:mod:`chisurf.core.experiments.linked`) and linked
    like a dropped file (embedded at the next save when the project embeds). *result_of* is the uid
    of the dataset it was computed from: a burst run of a photon stream is that dataset's child.

    Returns the dataset that was added.
    """
    dataset = result
    if isinstance(result, (str, bytes)) or hasattr(result, "__fspath__"):
        from chisurf.core.experiments.linked import reader_for_kind

        if not kind:
            raise ValueError("an address needs its kind to enter the workspace")
        reader = reader_for_kind(kind)
        address = str(result)
        if reader is None:
            from chisurf.core.data import LinkedDataset

            dataset = LinkedDataset(address, data_kind=kind)
        elif kind == "bursts":
            dataset = reader.make_dataset(address, result_of=result_of)
        else:
            dataset = reader.make_dataset(address)
        if reader is not None:
            dataset.data_reader = reader
    if result_of and not getattr(dataset, "result_of", ""):
        try:
            dataset.result_of = str(result_of)
        except AttributeError:
            pass
    if name:
        dataset.name = str(name)
    import chisurf as cs

    if getattr(cs, "cs", None) is None and getattr(cs, "api", None) is None:
        # No running session (a script, the agent runtime): the session-less dataset list.
        from chisurf.core.api.live_edit import add_dataset

        add_dataset(dataset)
    else:
        _api().load_dataset(dataset=dataset, name=str(getattr(dataset, "name", "") or ""))
    return dataset
