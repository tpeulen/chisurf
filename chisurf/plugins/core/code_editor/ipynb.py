"""Read and write Jupyter notebooks (``.ipynb``, format 4) without nbformat.

A notebook is a JSON document; the editor needs only the parts of nbformat
that build one, read one and write one back. This module reproduces those with
nbformat's own conventions, so a file ChiSurf saves is byte-for-byte what
nbformat would have written (pinned by ``test_ipynb.py``, which uses nbformat
as the oracle):

- reading joins multi-line lists (``source``, stream ``text``, text-like
  output ``data``) into single strings;
- writing splits ``text/*`` (and JavaScript/SVG) back into lists of lines and
  dumps with sorted keys, ``indent=1``, ``separators=(",", ": ")`` and
  ``ensure_ascii=False``;
- both drop the transient metadata (``orig_nbformat``, ``orig_nbformat_minor``,
  ``signature``, and each cell's ``trusted``);
- new cells carry an 8-character ``id`` (format 4.5).

Only format 4 is read; anything else raises ``ValueError``.

The names mirror nbformat's (``v4.new_code_cell``, ``read``, ``reads``,
``writes``, ``from_dict``) so the editor reads as it did.
"""

from __future__ import annotations

import copy
import json
import types
import uuid

__all__ = ["NotebookNode", "from_dict", "read", "reads", "v4", "writes"]

#: The format minor version new notebooks carry (cell ids exist from 4.5).
NBFORMAT_MINOR = 5


class NotebookNode(dict):
    """A dict whose keys are also attributes, like nbformat's node."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = from_dict(value)

    def __setitem__(self, key, value):
        super().__setitem__(key, from_dict(value))

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def __deepcopy__(self, memo):
        return from_dict(copy.deepcopy(dict(self), memo))


def from_dict(value):
    """Convert nested dicts (and dicts inside lists) to :class:`NotebookNode`.

    Parameters
    ----------
    value : object
        A dict, a list, or a leaf value.

    Returns
    -------
    object
        The same structure with every dict a :class:`NotebookNode`.
    """
    if isinstance(value, dict) and not isinstance(value, NotebookNode):
        node = NotebookNode()
        for key, item in value.items():
            dict.__setitem__(node, key, from_dict(item))
        return node
    if isinstance(value, NotebookNode):
        for key, item in list(value.items()):
            dict.__setitem__(value, key, from_dict(item))
        return value
    if isinstance(value, list):
        return [from_dict(item) for item in value]
    return value


def _cell_id() -> str:
    return uuid.uuid4().hex[:8]


def _new_notebook(**kwargs) -> NotebookNode:
    nb = from_dict(
        {"nbformat": 4, "nbformat_minor": NBFORMAT_MINOR, "metadata": {}, "cells": []}
    )
    nb.update(kwargs)
    return nb


def _new_code_cell(source: str = "", **kwargs) -> NotebookNode:
    cell = from_dict(
        {
            "id": _cell_id(),
            "cell_type": "code",
            "metadata": {},
            "execution_count": None,
            "source": source,
            "outputs": [],
        }
    )
    cell.update(kwargs)
    return cell


def _new_text_cell(cell_type: str, source: str = "", **kwargs) -> NotebookNode:
    cell = from_dict({"id": _cell_id(), "cell_type": cell_type, "metadata": {}, "source": source})
    cell.update(kwargs)
    return cell


#: The ``nbformat.v4`` constructors the editor uses.
v4 = types.SimpleNamespace(
    new_notebook=_new_notebook,
    new_code_cell=_new_code_cell,
    new_markdown_cell=lambda source="", **kw: _new_text_cell("markdown", source, **kw),
    new_raw_cell=lambda source="", **kw: _new_text_cell("raw", source, **kw),
)


def _is_json_mime(key: str) -> bool:
    return key == "application/json" or (key.startswith("application/") and key.endswith("+json"))


#: Non-``text/*`` mime types nbformat still writes as line lists.
_NON_TEXT_SPLIT_MIMES = {"application/javascript", "image/svg+xml"}


def _rejoin_bundle(data: dict) -> None:
    for key, value in list(data.items()):
        if (
            not _is_json_mime(key)
            and isinstance(value, list)
            and all(isinstance(line, str) for line in value)
        ):
            data[key] = "".join(value)


def _split_bundle(data: dict) -> None:
    for key, value in list(data.items()):
        if isinstance(value, str) and (key.startswith("text/") or key in _NON_TEXT_SPLIT_MIMES):
            data[key] = value.splitlines(True)


def _rejoin_lines(nb: NotebookNode) -> NotebookNode:
    for cell in nb.get("cells", []):
        if isinstance(cell.get("source"), list):
            cell["source"] = "".join(cell["source"])
        for attachment in (cell.get("attachments") or {}).values():
            _rejoin_bundle(attachment)
        if cell.get("cell_type") == "code":
            for output in cell.get("outputs", []) or []:
                kind = output.get("output_type", "")
                if kind in ("execute_result", "display_data"):
                    _rejoin_bundle(output.get("data", {}))
                elif kind and isinstance(output.get("text", ""), list):
                    output["text"] = "".join(output["text"])
    return nb


def _split_lines(nb: NotebookNode) -> NotebookNode:
    for cell in nb.get("cells", []):
        if isinstance(cell.get("source"), str):
            cell["source"] = cell["source"].splitlines(True)
        for attachment in (cell.get("attachments") or {}).values():
            _split_bundle(attachment)
        if cell.get("cell_type") == "code":
            for output in cell.get("outputs", []) or []:
                kind = output.get("output_type")
                if kind in ("execute_result", "display_data"):
                    _split_bundle(output.get("data", {}))
                elif kind == "stream" and isinstance(output.get("text"), str):
                    output["text"] = output["text"].splitlines(True)
    return nb


def _strip_transient(nb: NotebookNode) -> NotebookNode:
    # nbformat strips these on read *and* write; the notebook-level
    # ``trusted`` is not one of them.
    meta = nb.setdefault("metadata", {})
    for key in ("orig_nbformat", "orig_nbformat_minor", "signature"):
        meta.pop(key, None)
    for cell in nb.get("cells", []):
        cell.setdefault("metadata", {}).pop("trusted", None)
    return nb


def reads(text: str, as_version: int = 4) -> NotebookNode:
    """Parse a notebook from JSON text.

    Parameters
    ----------
    text : str
        The ``.ipynb`` content.
    as_version : int, optional
        Must be 4 (the only format read).

    Returns
    -------
    NotebookNode

    Raises
    ------
    ValueError
        Not JSON, not a notebook, or not format 4.
    """
    if as_version != 4:
        raise ValueError(f"only notebook format 4 is supported, not {as_version}")
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("nbformat") != 4 or not isinstance(
        data.get("cells"), list
    ):
        raise ValueError("not a format-4 notebook with a cells list")
    return _ensure_cell_ids(_strip_transient(_rejoin_lines(from_dict(data))))


def _ensure_cell_ids(nb: NotebookNode) -> NotebookNode:
    """Give every cell a unique ``id`` when the format requires one (>= 4.5).

    nbformat repairs a 4.5 notebook the same way on read (missing ids are
    drawn at random, duplicates replaced), so a file saved from here is
    valid wherever nbformat would read it.
    """
    if int(nb.get("nbformat_minor", 0)) < 5:
        return nb
    seen: set[str] = set()
    for cell in nb.get("cells", []):
        cid = cell.get("id")
        if not isinstance(cid, str) or not cid or cid in seen:
            cid = _cell_id()
            while cid in seen:
                cid = _cell_id()
            cell["id"] = cid
        seen.add(cid)
    return nb


def read(path, as_version: int = 4) -> NotebookNode:
    """Read a notebook file; see :func:`reads`."""
    with open(path, encoding="utf-8") as handle:
        return reads(handle.read(), as_version=as_version)


def writes(nb, sort_keys: bool = True, indent: int = 1) -> str:
    """Serialise a notebook exactly as ``nbformat.writes`` does.

    Parameters
    ----------
    nb : dict
        The notebook.
    sort_keys, indent : optional
        Accepted for nbformat's signature and, as there, overridden: the file
        is always written with sorted keys and ``indent=1``, so a saved
        notebook diffs the same whoever wrote it.

    Returns
    -------
    str
        JSON text, without a trailing newline (as ``nbformat.writes``).
    """
    nb = _strip_transient(_split_lines(from_dict(copy.deepcopy(dict(nb)))))
    return json.dumps(nb, sort_keys=True, indent=1, separators=(",", ": "), ensure_ascii=False)
