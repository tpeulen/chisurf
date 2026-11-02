"""Addresses of data inside containers: ``<path>[/<member>...]``.

A container (a ``.pto`` measurement, a ``.cs.pto`` project) holds several objects,
and anything that reads one names the object the same way a path names a file::

    measurement.pto                      the container
    measurement.pto/m001.ptu             a photon stream inside it
    measurement.pto/burstwise/bursts     a run's table
    project.cs.pto/decay_green           a dataset of a project
    project.cs.pto/@3f2a9c               the same, by its uid
    project.cs.pto/m000.pto/burstwise    a container inside a project

The rule is one sentence: the container is the **shortest leading prefix of the
address that is an existing regular file** -- a directory never is -- and the rest
is the member path (``""`` for the container itself). An address none of whose
prefixes is a file is an ordinary path (``(None, None)``): nothing exists yet, or
it is not a container address at all.

The same rule is implemented by ptolib and tttrlib; ``test/data/address_cases.json``
(copied from ptolib's ``tests/data/address_cases.json``) is the table every one of
them passes. File-path interfaces of the API and CLI take these addresses wherever
they take a path.
"""

from __future__ import annotations

import os
import pathlib

__all__ = [
    "CONTAINER_SUFFIXES",
    "SEPARATOR",
    "UID_PREFIX",
    "container_of",
    "join_address",
    "split_address",
    "split_address_lexical",
]

#: Separates a container from the member inside it, and the levels of a member.
SEPARATOR = "/"

#: A member that starts with this names a project dataset by its uid.
UID_PREFIX = "@"

#: File suffixes of ChiSurf's containers (``.cs.pto`` ends in ``.pto``).
CONTAINER_SUFFIXES = (".pto",)


def _parts(address) -> tuple[str, ...]:
    return pathlib.Path(os.fspath(address)).parts


def split_address(address) -> tuple[pathlib.Path | None, str | None]:
    """Split *address* into ``(container, member)`` by asking the filesystem.

    Parameters
    ----------
    address : str or os.PathLike
        A path, or a path followed by ``/<member>...``.

    Returns
    -------
    container : pathlib.Path or None
        The shortest leading prefix that is an existing regular file, or ``None``
        when no prefix is one.
    member : str or None
        The part below the container, joined with ``/`` (``""`` for the
        container itself), or ``None`` together with ``container``.

    Examples
    --------
    >>> split_address("no/such/file.pto/run")
    (None, None)
    """
    parts = _parts(address)
    # Nothing lies below a file, so a path has at most one prefix that is a file: the first
    # component with a suffix (``m.pto``) is tried first -- one stat where walking down from the
    # root took one per component, and a run picker asks every frame.
    for index, part in enumerate(parts, start=1):
        if pathlib.PurePath(part).suffix:
            candidate = pathlib.Path(*parts[:index])
            if candidate.is_file():
                return candidate, SEPARATOR.join(parts[index:])
            break
    for index in range(1, len(parts) + 1):
        candidate = pathlib.Path(*parts[:index])
        if candidate.is_file():
            return candidate, SEPARATOR.join(parts[index:])
    return None, None


def split_address_lexical(address) -> tuple[pathlib.Path | None, str]:
    """Split *address* at its first container-suffixed component, without a file check.

    For addresses of containers that do not exist yet (a writer naming its output).
    A component that exists as a directory is never the container. Prefer
    :func:`split_address` whenever the container may exist.

    Returns
    -------
    container : pathlib.Path or None
    member : str
        ``""`` when there is no container or nothing below it.

    Examples
    --------
    >>> split_address_lexical("out/new.pto/run one")
    (PosixPath('out/new.pto'), 'run one')
    >>> split_address_lexical("plain/file.dat")
    (None, '')
    """
    found, member = split_address(address)
    if found is not None:
        return found, member
    parts = _parts(address)
    for index, part in enumerate(parts):
        if part.lower().endswith(CONTAINER_SUFFIXES):
            candidate = pathlib.Path(*parts[: index + 1])
            if candidate.is_dir():
                continue
            return candidate, SEPARATOR.join(parts[index + 1 :])
    return None, ""


def container_of(address) -> pathlib.Path:
    """The file to open, stage or stat for *address*: its container, else the path itself."""
    container, _ = split_address(address)
    return container if container is not None else pathlib.Path(os.fspath(address))


def join_address(container, *members: str) -> str:
    """Return the address of *members* inside *container*.

    Examples
    --------
    >>> join_address("m000.pto", "burstwise", "bursts")
    'm000.pto/burstwise/bursts'
    >>> join_address("m000.pto")
    'm000.pto'
    """
    text = os.fspath(container)
    below = SEPARATOR.join(str(m).strip(SEPARATOR) for m in members if str(m).strip(SEPARATOR))
    return f"{text}{SEPARATOR}{below}" if below else text
