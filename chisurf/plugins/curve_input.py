"""The curve tools' side of the Datasets workspace: what they take and what they give back.

Decay, anisotropy, correlation and trace tools take their curves from the workspace (manifest
``accepts[].from_workspace``, :mod:`chisurf.core.plugin.workspace_input`) and never ask for an
input file. What repeats across them lives here:

* :class:`CurveInput` -- the model and spec of one generated Input section, bound to one named
  ``accepts`` entry, so a tool with two inputs (a decay and its IRF, a batch and a reference) draws
  one section per input;
* :func:`curve_of` -- what an address the workspace hands over is: the session dataset (a curve read
  into ChiSurf, ``@<uid>``) or the file itself (a dataset the session links to a path);
* :func:`add_curve` / :func:`example_into_workspace` -- a curve a tool computed or a demo it wrote
  enters the workspace (as a child of its source), and *Load example* hands the demo to the tool's
  own receive hook exactly as the user's data would be.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.plugin.workspace_input import WorkspaceInputMixin

_log = logging.getLogger(__name__)


def _plugin_dir(plugin: str) -> Path:
    """The folder of the plugin whose manifest ``id`` is *plugin* (one or two folders deep)."""
    plugins = Path(__file__).resolve().parent
    for manifest in [*plugins.glob("*/manifest.json"), *plugins.glob("*/*/manifest.json")]:
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("id") == plugin:
                return manifest.parent
        except (OSError, ValueError):
            continue
    raise KeyError(plugin)


class CurveInput(WorkspaceInputMixin):
    """One Input section feeding the ``accepts`` entry *name* of *plugin* (the first entry with a
    ``from_workspace`` declaration when *name* is empty).

    ``spec`` is the section to draw with :func:`emtk.view_form.draw_form` over this object, ``form``
    its state; a pick goes to the plugin's receive hook with *app* as its first argument.
    """

    def __init__(
        self, plugin: str, app: Any, *, name: str = "", title: str = "", height: float | None = None
    ) -> None:
        from emtk.view_form import FormState

        from chisurf.core.plugin.workspace_input import input_section, parse

        self.workspace_input_plugin = plugin
        self.workspace_input_app = app
        self.name = name
        self._found = None
        manifest = json.loads((_plugin_dir(plugin) / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest.get("accepts") or []:
            if entry.get("from_workspace") and (not name or entry.get("name") == name):
                self.name = str(entry.get("name", ""))
                section = input_section(parse(entry["from_workspace"]), title=title)
                if height is not None:
                    for part in section.get("sections", []):
                        if (part.get("options") or {}).get("source") == "workspace_input_rows":
                            part["options"]["height"] = height
                self.spec = {"sections": [section]}
                break
        else:
            raise KeyError(f"{plugin} declares no workspace input {name!r}")
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

    def draw(self, rects: dict | None = None, on_used: Callable | None = None) -> None:
        """Draw the section; its control rects go into *rects* (a guided tour's targets)."""
        from emtk.view_form import draw_form

        if on_used is not None:
            self.form.on_used = on_used
            self.workspace_input_on_used = on_used
        self.form.rects.clear()
        draw_form(self.spec, self, self.form)
        if rects is not None:
            rects.update(self.form.rects)


def curve_of(address: str) -> Any:
    """The curve *address* names when the session holds its points (``@<uid>``, a curve read into
    ChiSurf), else ``None`` -- then *address* is a file (a dataset the workspace only links to, or
    a path) the tool reads itself."""
    from chisurf.core.plugin.workspace_input import resolve_dataset

    dataset = resolve_dataset(str(address))
    return dataset if dataset is not None and hasattr(dataset, "y") else None


def curve_file(address: str, folder: Path) -> str:
    """A file holding the curve at *address*: the file it was read from, else its points written as
    two columns (time, counts) into *folder* -- for tools whose engine reads a path."""
    dataset = curve_of(address)
    if dataset is None:
        if Path(str(address)).is_file():
            return str(address)
        raise FileNotFoundError(f"{address} is not in the workspace")
    for source in (getattr(dataset, "filename", ""), getattr(dataset, "address", "")):
        if source and Path(str(source)).is_file():
            return str(source)
    name = str(getattr(dataset, "name", "") or "curve").replace("/", "_")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{Path(name).stem or 'curve'}.dat"
    np.savetxt(
        target, np.column_stack([np.asarray(dataset.x), np.asarray(dataset.y)]), delimiter="\t"
    )
    return str(target)


def dataset_uids(payload: dict) -> list[str]:
    """The uids of the workspace datasets a payload came from (its ``datasets`` list)."""
    return [str(u) for u in payload.get("datasets") or [] if str(u)]


def add_curve(
    x: Any,
    y: Any,
    *,
    name: str,
    kind: str,
    result_of: str = "",
    experiment: str = "",
    ey: Any = None,
) -> Any:
    """A curve (computed or a demo) enters the workspace as a dataset of *kind*; returns it
    (``None`` on failure, logged: the tool keeps its data, the row is a convenience)."""
    from chisurf.core.data import DataCurve
    from chisurf.core.plugin.workspace_input import register_result

    try:
        kwargs = {"ey": np.asarray(ey, float)} if ey is not None else {}
        curve = DataCurve(
            x=np.asarray(x, float),
            y=np.asarray(y, float),
            name=str(name),
            load_filename_on_init=False,
            **kwargs,
        )
        curve.data_kind = kind
        if experiment:
            _attach_experiment(curve, experiment)
        return register_result(curve, result_of=result_of, name=str(name))
    except Exception:  # noqa: BLE001 - never break the tool over a workspace row
        _log.exception("adding %s to the workspace failed", name)
        return None


def _attach_experiment(curve: Any, name: str) -> None:
    """Give *curve* the registered experiment *name* (the workspace's Experiment column)."""
    try:
        import chisurf

        experiment = (getattr(chisurf, "experiment", None) or {}).get(name)
        if experiment is not None:
            curve.experiment = experiment
    except Exception:  # noqa: BLE001 - the curve is still a valid row without it
        pass


def address_of_dataset(dataset: Any) -> str:
    """The address the workspace hands *dataset* over by (``@<uid>`` for a session curve)."""
    from chisurf.core.plugin.workspace_input import SESSION_PREFIX

    linked = getattr(dataset, "address", "")
    return str(linked) if linked else f"{SESSION_PREFIX}{getattr(dataset, 'unique_identifier', '')}"


def example_into_workspace(
    curves: list[tuple[Any, Any, str]],
    receive: Callable[[Any, dict], Any],
    app: Any,
    *,
    key: str,
    kind: str,
    many: bool = False,
    experiment: str = "",
    extra: dict | None = None,
) -> list[Any]:
    """Add the demo *curves* (``(x, y, name)``) to the workspace and hand them to *receive* (the
    tool's own hook) as the workspace would; returns the datasets added. A curve the workspace
    refused still reaches the tool (written to a temporary file)."""
    import tempfile

    added, addresses = [], []
    folder = Path(tempfile.gettempdir()) / "chisurf-curve-examples"
    for x, y, name in curves:
        dataset = add_curve(x, y, name=name, kind=kind, experiment=experiment)
        if dataset is not None:
            added.append(dataset)
            addresses.append(address_of_dataset(dataset))
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{Path(name).stem or 'example'}.dat"
            np.savetxt(path, np.column_stack([np.asarray(x, float), np.asarray(y, float)]))
            addresses.append(str(path))
    payload: dict[str, Any] = dict(extra or {})
    payload[key] = addresses if many else (addresses[0] if addresses else "")
    payload["datasets"] = [str(getattr(d, "unique_identifier", "")) for d in added]
    receive(app, payload)
    return added


def vv_vh_files(addresses: list[str]) -> list[str]:
    """The VV/VH files behind workspace *addresses*: a file the workspace links to, the file a
    curve was read from, or -- two curves read into ChiSurf named VV and VH -- a VV/VH file
    written from them."""
    import tempfile

    from chisurf.plugins.curve_input import curve_of

    files, loose = [], []
    for address in addresses:
        dataset = curve_of(address)
        if dataset is None:
            if Path(address).exists():
                files.append(address)
            continue
        source = str(getattr(dataset, "filename", "") or "")
        if source and Path(source).is_file():
            files.append(source)
        else:
            loose.append(dataset)
    named = {}
    for dataset in loose:
        low = str(getattr(dataset, "name", "")).lower()
        named.setdefault("vh" if "vh" in low or "perp" in low else "vv", dataset)
    if "vv" in named and "vh" in named:
        from chisurf.core.fio.vv_vh import write_vv_vh

        folder = Path(tempfile.gettempdir()) / "chisurf-vv-vh-input"
        folder.mkdir(parents=True, exist_ok=True)
        stem = Path(str(getattr(named["vv"], "name", "") or "vv_vh")).stem or "vv_vh"
        target = folder / f"{stem}_vvvh.dat"
        write_vv_vh(
            target,
            vv=np.asarray(named["vv"].y, float),
            vh=np.asarray(named["vh"].y, float),
            metadata={"comment": "written from two ChiSurf curves"},
        )
        files.append(str(target))
    elif loose:
        raise ValueError("pick the VV/VH file, or two curves named VV and VH")
    return list(dict.fromkeys(files))


__all__ = [
    "CurveInput",
    "add_curve",
    "address_of_dataset",
    "curve_file",
    "curve_of",
    "dataset_uids",
    "example_into_workspace",
    "vv_vh_files",
]
