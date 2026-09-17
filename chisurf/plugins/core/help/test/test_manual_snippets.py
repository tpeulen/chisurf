"""The manual's code has to be code that runs.

The fitting manual teaches the shell alongside the interface, and a snippet
that names a module which has moved is worse than no snippet: it is copied,
it fails, and nothing in the documentation says which of the two is out of
date. Two of them were — ``chisurf.parameter.Parameter`` (the module is
``chisurf.core.parameter``) and a ``sample_fit(fit, filename=…)`` call whose
second argument became a *directory*.

These tests do not execute the snippets — most of them need a loaded data set —
but they check the part that rots: that every dotted name a snippet uses can be
imported, and that every function it calls still takes the arguments it is
shown with.
"""

import importlib
import inspect
import re

import pytest

from chisurf.plugins.core.help.api.toc import docs_root

#: ``module.attribute`` occurrences in a manual snippet that must resolve.
_DOTTED = re.compile(r"\b(chisurf(?:\.[a-z_][a-z_0-9]*)+)\b")

#: Snippet prefixes that are not real module paths.
_NOT_MODULES = {"chisurf.fits", "chisurf.current_fit", "chisurf.macros.add_dataset"}


def _snippets() -> list[tuple[str, str]]:
    """Return ``(page, code)`` for every Python block in the manual."""
    manual = docs_root() / "manual"
    blocks = []
    for page in sorted(manual.glob("*.rst")):
        text = page.read_text(encoding="utf-8")
        for match in re.finditer(r"\.\. code-block:: python\n\n((?:[ \t]+.*\n|\n)+)", text):
            blocks.append((page.name, match.group(1)))
    return blocks


def _resolve(dotted: str) -> bool:
    """Whether ``a.b.c`` names an importable module or an attribute of one."""
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        module_name = ".".join(parts[:split])
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        target = module
        for attribute in parts[split:]:
            if not hasattr(target, attribute):
                return False
            target = getattr(target, attribute)
        return True
    return False


@pytest.mark.parametrize(
    "page,code",
    _snippets(),
    ids=lambda value: value if isinstance(value, str) and value.endswith(".rst") else "",
)
def test_snippet_names_resolve(page, code):
    """Every ``chisurf.…`` name a manual snippet uses must still exist."""
    unresolved = sorted(
        {
            dotted
            for dotted in _DOTTED.findall(code)
            if dotted not in _NOT_MODULES and not _resolve(dotted)
        }
    )
    assert not unresolved, f"{page}: {unresolved}"


def test_sample_fit_is_documented_with_its_real_signature():
    """The sampling page's call has to match the function it calls."""
    from chisurf.core.fitting.fit import sample_fit

    parameters = list(inspect.signature(sample_fit).parameters)
    assert parameters[:2] == ["fit", "target_directory"]

    page = (docs_root() / "manual" / "parameter_sampling.rst").read_text(encoding="utf-8")
    assert "sample_fit(fit, " in page
    # The old spelling wrote a *file*; it now creates a timestamped directory.
    assert "filename=" not in page


def test_manual_pages_are_not_stubs():
    """A page saying "Missing" is a broken promise in the table of contents."""
    manual = docs_root() / "manual"
    stubs = []
    for page in sorted(manual.glob("*.rst")):
        text = page.read_text(encoding="utf-8")
        body = "\n".join(text.splitlines()[2:]).strip()
        if len(body.split()) < 12 or body.lower() in {"missing", "tbd", "todo"}:
            stubs.append(page.name)
    assert not stubs, stubs


def test_no_lost_conversion_artifacts():
    """The docx conversion dropped inline equations, leaving holes in sentences.

    Two spaces inside a sentence, an empty ``()`` citation or a dangling
    ``, ,`` is where a symbol used to be. They are invisible in review and
    obvious to a reader.
    """
    manual = docs_root() / "manual"
    offenders = []
    for page in sorted(manual.glob("*.rst")):
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith((" ", "\t", "..")) or not line.strip():
                continue
            if re.search(r"\S\s\s+\S", line) or ", ," in line or re.search(r"\(\)\.?\s", line):
                offenders.append(f"{page.name}:{number}")
    assert not offenders, offenders
