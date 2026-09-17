from __future__ import annotations

import datetime
import functools
import itertools
import textwrap
import warnings
import weakref

__all__ = [
    "DeprecatedWarning",
    "UnsupportedWarning",
    "deprecated",
    "register",
    "set_module",
]


def register(cls):
    """Decorator to make a class a registered class.

    Example usage::

    @chisurf.core.support.decorators.register
    class A1():
        pass

    @chisurf.core.support.decorators.register
    class B():
        pass

    @chisurf.core.support.decorators.register
    class A2(A1):
        pass

    class A3(A1):
        pass

    a1_1 = A1()
    a1_2 = A1()
    a2_1 = A2()
    a3_1 = A3()
    b = B()

    assert a1_2 in a1_1.get_instances()
    assert a2_1 not in a1_1.get_instances()
    assert a3_1 in a1_1.get_instances()
    assert b not in a1_1.get_instances()

    """

    class RegisteredClass(cls):
        _instances = set()

        @classmethod
        def get_instances(cls) -> weakref.ReferenceType:
            """Returns all instances of the class as a generator"""
            dead = set()
            for ref in cls._instances:
                obj = ref()
                if obj is not None:
                    yield obj
                else:
                    dead.add(ref)
            cls._instances -= dead

        def __init__(self, *args, **kwargs):
            # Initialize the base class first so that attributes like
            # unique_identifier are available before we add the weakref
            # to _instances (weakref.ref.__hash__ delegates to self.__hash__).
            super().__init__(*args, **kwargs)
            self._instances.add(weakref.ref(self))
            self.__class__.__name__ = cls.__name__

    return RegisteredClass


def set_module(module):
    """Decorator for overriding __module__ on a function or class.

    Example usage::

        @set_module('numpy')
        def example():
            pass

        assert example.__module__ == 'numpy'
    """

    def decorator(func):
        if module is not None:
            func.__module__ = module
        return func

    return decorator


class DeprecatedWarning(DeprecationWarning):
    """Warning issued when a deprecated function is called.

    A specialization of :class:`DeprecationWarning` that carries the pieces of
    the deprecation notice as attributes, so the message can be composed once in
    :meth:`__str__` rather than at every decoration site.

    Parameters
    ----------
    function : str
        Name of the deprecated function.
    deprecated_in : str or None
        Version in which the function was deprecated.
    removed_in : str or datetime.date or None
        Version or date at which the function is removed.
    details : str
        Extra guidance, usually naming the replacement.
    """

    def __init__(self, function, deprecated_in, removed_in, details=""):
        self.function = function
        self.deprecated_in = deprecated_in
        self.removed_in = removed_in
        self.details = details
        super().__init__(function, deprecated_in, removed_in, details)

    def __str__(self):
        """Return the human-readable deprecation message."""
        parts = [f"{self.function} is deprecated"]
        if self.deprecated_in:
            parts.append(f" as of {self.deprecated_in}")
        if self.removed_in:
            on_or_in = "on" if isinstance(self.removed_in, datetime.date) else "in"
            parts.append(f" and will be removed {on_or_in} {self.removed_in}")
        if self.deprecated_in or self.removed_in or self.details:
            parts.append(".")
        if self.details:
            parts.append(f" {self.details}")
        return "".join(parts)


class UnsupportedWarning(DeprecatedWarning):
    """Warning issued when a function is called past its removal version.

    Subclasses :class:`DeprecatedWarning` so a single filter catches both, while
    the distinct class lets callers (and tests) treat "should already be gone"
    differently from "will go away".
    """

    def __str__(self):
        """Return the human-readable removal message."""
        details = f" {self.details}" if self.details else ""
        return f"{self.function} is unsupported as of {self.removed_in}.{details}"


def _version_key(text: str) -> tuple:
    """Return a comparable key for a dotted version string.

    Each dot-separated chunk contributes its leading run of digits. A chunk that
    is not purely numeric (``dev0``, ``rc1``, ``3b1``) marks a pre-release, and
    the key is truncated after a ``-1`` sentinel so that ``26.dev0`` sorts below
    ``26.1``. This is deliberately not a full PEP 440 implementation -- it orders
    the ``YY.MM.DD`` / ``YY.devN`` versions this project uses, which is all the
    deprecation bookkeeping needs, and avoids a dependency for a comparison.

    Parameters
    ----------
    text : str
        Version string, e.g. ``"19.10.31"`` or ``"26.dev0"``.

    Returns
    -------
    tuple of int
        Key ordered by the same relation as the versions themselves.
    """
    key: list[int] = []
    for chunk in str(text).split("."):
        digits = "".join(itertools.takewhile(str.isdigit, chunk))
        key.append(int(digits) if digits else 0)
        if digits != chunk:
            key.append(-1)
            break
    return tuple(key)


def _running_version():
    """Return the version of the running code, or ``None`` if unknown.

    Resolved lazily from :mod:`chisurf.core.info` -- a dependency-free leaf
    module -- so that this module keeps working when it is lifted out of
    ChiSurf, in which case the version comparison is simply disabled.

    Returns
    -------
    str or None
        The running version string, or ``None`` outside a ChiSurf tree.
    """
    try:
        from chisurf.core.info import __version__
    except ImportError:  # pragma: no cover - only outside a ChiSurf tree
        return None
    return __version__


def _deprecation_state(deprecated_in, removed_in, current_version):
    """Decide whether a decoration warns, and with which warning class.

    Parameters
    ----------
    deprecated_in : str or None
        Version the function was deprecated in. ``None`` means "deprecated now".
    removed_in : str or datetime.date or None
        Version or date the function is removed at.
    current_version : str or None
        Version of the running code. ``None`` disables the comparison, in which
        case the decoration always warns as *deprecated* -- the decorator was
        applied, so the function *is* deprecated, but without a version to
        compare against there is no way to tell that it is already past
        ``removed_in``.

    Returns
    -------
    tuple of bool
        ``(should_warn, is_unsupported)``.
    """
    if isinstance(removed_in, datetime.date):
        return True, datetime.date.today() >= removed_in
    if current_version is None:
        return True, False
    current = _version_key(current_version)
    if removed_in and current >= _version_key(removed_in):
        return True, True
    if deprecated_in is None or current >= _version_key(deprecated_in):
        return True, False
    return False, False


def _with_deprecation_note(docstring: str, deprecated_in, removed_in, details: str) -> str:
    """Append a Sphinx ``.. deprecated::`` directive to a docstring.

    Parameters
    ----------
    docstring : str
        The original docstring (may be empty).
    deprecated_in : str or None
        Version for the directive argument.
    removed_in : str or datetime.date or None
        Version or date mentioned in the directive body.
    details : str
        Extra guidance appended to the directive body.

    Returns
    -------
    str
        Docstring with the notice appended, dedented below the summary line so
        the directive is not swallowed by the original indentation.
    """
    summary, _, body = docstring.partition("\n")
    note = ".. deprecated::"
    if deprecated_in:
        note += f" {deprecated_in}"
    if details:
        note += f" {details}"
    if removed_in:
        on_or_in = "on" if isinstance(removed_in, datetime.date) else "in"
        note += f"\n   This will be removed {on_or_in} {removed_in}."
    return "\n\n".join(part for part in (summary, textwrap.dedent(body).strip(), note) if part)


_UNSET = object()


def deprecated(deprecated_in=None, removed_in=None, current_version=_UNSET, details=""):
    """Mark a function as deprecated.

    The wrapped function keeps working and gains two things: a
    ``.. deprecated::`` note in its docstring, and a :class:`DeprecatedWarning`
    (or :class:`UnsupportedWarning` past ``removed_in``) raised through the
    :mod:`warnings` machinery on every call. Both are subclasses of the built-in
    :class:`DeprecationWarning`, which Python hides outside ``__main__`` unless
    warnings are enabled -- run with ``-W default::DeprecationWarning`` to see
    them.

    This replaces the third-party ``deprecation`` package, which did exactly this
    and nothing else; the behaviour and keyword names are the same, so decorated
    call sites did not change.

    Parameters
    ----------
    deprecated_in : str, optional
        Version in which the function became deprecated. ``None`` (the default)
        means it is deprecated as of now.
    removed_in : str or datetime.date, optional
        Version or date at which the function is removed. Cannot be given
        without ``deprecated_in``.
    current_version : str, optional
        Version of the running code, used to decide whether the deprecation
        period has started and whether ``removed_in`` has already passed.
        Defaults to the running ChiSurf version; pass ``None`` explicitly to
        disable the comparison, in which case the decoration always warns as
        deprecated and never as unsupported.
    details : str, optional
        Extra guidance, typically naming the replacement.

    Returns
    -------
    callable
        Decorator that wraps the target function.

    Raises
    ------
    TypeError
        If ``removed_in`` is given without ``deprecated_in``.

    Examples
    --------
    >>> import warnings
    >>> @deprecated(deprecated_in="19.10.31", details="Use tttrlib instead")
    ... def read_file(path):
    ...     '''Read a file.'''
    ...     return path
    >>> with warnings.catch_warnings(record=True) as caught:
    ...     warnings.simplefilter("always")
    ...     _ = read_file("x")
    >>> str(caught[0].message)
    'read_file is deprecated as of 19.10.31. Use tttrlib instead'
    """
    if deprecated_in is None and removed_in is not None:
        raise TypeError("Cannot set removed_in without also setting deprecated_in")

    if current_version is _UNSET:
        current_version = _running_version()
    should_warn, is_unsupported = _deprecation_state(deprecated_in, removed_in, current_version)

    def _decorate(function):
        if should_warn:
            note = _with_deprecation_note(
                function.__doc__ or "", deprecated_in, removed_in, details
            )
            try:
                function.__doc__ = note
            except (AttributeError, TypeError):
                # Compiled callables (numba dispatchers, C extensions) have a
                # read-only __doc__; the wrapper below still carries the note.
                pass

        @functools.wraps(function)
        def _inner(*args, **kwargs):
            if should_warn:
                cls = UnsupportedWarning if is_unsupported else DeprecatedWarning
                warnings.warn(
                    cls(
                        getattr(function, "__name__", repr(function)),
                        deprecated_in,
                        removed_in,
                        details,
                    ),
                    category=DeprecationWarning,
                    stacklevel=2,
                )
            return function(*args, **kwargs)

        if should_warn:
            _inner.__doc__ = note
        return _inner

    return _decorate
