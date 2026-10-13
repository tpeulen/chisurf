"""The files an assistant answer asks to write, and where they go in the editor.

An answer writes a file with a fenced block whose first line names it::

    ```python
    # WRITE_FILE: analysis.py
    print("hello")
    ```

or with ``<write_file filename="analysis.py">...</write_file>``. The target is only the first
line after ``WRITE_FILE``: the content never folds into the file name. A target of ``current``
(``active``, ``untitled``, ...) is the document in front. Toolkit-free; the emtk editor applies
the writes (``EditorModel.apply_file_writes``) and the assistant validates them
(:func:`~chisurf.plugins.core.code_editor.validation.validate_writes`).
"""

from __future__ import annotations

import re

__all__ = ["CURRENT_TARGETS", "is_current_target", "parse_file_writes"]

#: Targets that mean "the document in front".
CURRENT_TARGETS = frozenset(
    {
        "current",
        "active",
        "current open document",
        "current_document",
        "current file",
        "untitled",
        "untitled document",
    }
)

_XML = re.compile(r"<write_file\s+filename=\"([^\"]+)\"\s*>(.*?)</write_file>", re.DOTALL)
_BLOCK = re.compile(r"```[a-zA-Z0-9_-]*\s*\n(.*?)\n```", re.DOTALL)
_HEADER = re.compile(r"^\s*(?:#|//)\s*WRITE_FILE:?\s*([^\r\n]+)\r?\n(.*)$", re.DOTALL)


def is_current_target(filename: str) -> bool:
    """Whether *filename* names the document in front rather than a file."""
    return filename.strip().lower() in CURRENT_TARGETS


def parse_file_writes(response: str) -> list[tuple[str, str]]:
    """``(filename, content)`` for every file *response* asks to write, in order of appearance.

    XML-style tags first, then fenced blocks that start with a ``WRITE_FILE`` comment line.
    """
    writes = [(name.strip(), content.strip()) for name, content in _XML.findall(response)]
    for block in _BLOCK.findall(response):
        match = _HEADER.match(block)
        if match:
            writes.append((match.group(1).strip(), match.group(2)))
    return writes
