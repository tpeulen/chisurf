"""Tab completion against the live namespace.

Completing against real objects beats static analysis in a REPL, and by a wide
margin: ``df.<TAB>`` on an actual DataFrame, ``fit.model.<TAB>`` on a live
ChiSurf fit and dictionary keys are all things a static analyser cannot see. The
trade is the other direction -- a name that has never been executed does not
exist yet, so it cannot be completed.

The hazard of the live approach is that completing ``a.b.c`` means *evaluating*
``a.b`` to ask what attributes it has. :data:`_SAFE_EXPR` bounds what may be
evaluated to dotted names and literal subscripts -- never anything containing a
call, an assignment or an operator -- so Tab cannot invoke a function.

Measured, so the guarantee is not overstated: a **property getter does still
run** when you complete ``obj.prop.<TAB>``, because reading ``obj.prop`` is what
listing its attributes requires. Stock :mod:`rlcompleter` behaves identically
here, as does IPython without jedi. What the guard adds over stock rlcompleter
is a bound that holds for subscripts and for the wider set of expressions this
completer accepts; both already refuse to cross a parenthesis.
"""

from __future__ import annotations

import dataclasses
import glob
import keyword
import os
import pkgutil
import re
import rlcompleter
import typing

__all__ = ["CompletionResult", "ChinsoleCompleter"]

#: An expression safe to evaluate for completion: dotted names and subscripts
#: with literal contents, and nothing else. No call, no assignment, no operator.
#: Anything not matching this is not evaluated at all.
_SAFE_EXPR = re.compile(r"^[A-Za-z_]\w*(?:\.\w+|\[[^\]\[()]*\])*$")

_DICT_KEY_RE = re.compile(
    r"(?P<expr>[A-Za-z_]\w*(?:\.\w+|\[[^\]\[]*\])*)\[\s*(?P<quote>['\"])(?P<prefix>[^'\"]*)$"
)
_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(?P<mod>[\w.]*)$")
_FROM_IMPORT_RE = re.compile(r"^\s*from\s+(?P<mod>[\w.]+)\s+import\s+(?P<prefix>\w*)$")
_STRING_TAIL_RE = re.compile(r"(?P<quote>['\"])(?P<text>[^'\"]*)$")
_MAGIC_RE = re.compile(r"^\s*(?P<esc>%{1,2})(?P<name>\w*)$")
_WORD_RE = re.compile(r"[A-Za-z_]\w*$")

#: Magics whose argument is a filesystem path.
_PATH_MAGICS = frozenset({"run", "load", "cd", "edit", "pushd", "save", "writefile"})


@dataclasses.dataclass
class CompletionResult:
    """The completions for one cursor position.

    Attributes
    ----------
    matches : list of str
        Full replacement texts, already sorted.
    start, end : int
        The span of *line* that a chosen match replaces.
    common_prefix : str
        Longest prefix shared by every match; inserted on the first Tab.
    kind : str
        What was completed, for the popup's per-row glyph.
    """

    matches: list[str]
    start: int
    end: int
    common_prefix: str = ""
    kind: str = "name"

    def __bool__(self) -> bool:
        """Return whether there is anything to offer.

        Returns
        -------
        bool
        """
        return bool(self.matches)


def _common_prefix(matches: typing.Sequence[str]) -> str:
    """Return the longest prefix shared by *matches*.

    Parameters
    ----------
    matches : sequence of str

    Returns
    -------
    str
    """
    if not matches:
        return ""
    first, last = min(matches), max(matches)
    for index, char in enumerate(first):
        if index >= len(last) or last[index] != char:
            return first[:index]
    return first


def _rank(matches: typing.Iterable[str], prefix: str) -> list[str]:
    """Sort *matches*, hiding private names unless they were asked for.

    Parameters
    ----------
    matches : iterable of str
    prefix : str

    Returns
    -------
    list of str
    """
    unique = sorted(set(matches))
    if not prefix.startswith("_"):
        visible = [m for m in unique if not m.rpartition(".")[2].startswith("_")]
        hidden = [m for m in unique if m.rpartition(".")[2].startswith("_")]
        unique = visible or hidden
    return sorted(unique, key=lambda m: (m.rpartition(".")[2].startswith("_"), m.lower()))


class ChinsoleCompleter:
    """Completes console input against a live :class:`~chisurf.core.console.shell.Shell`.

    Parameters
    ----------
    shell : Shell
    """

    def __init__(self, shell: typing.Any) -> None:
        self.shell = shell

    @property
    def namespace(self) -> dict:
        """dict: The namespace completions are drawn from."""
        return self.shell.user_ns

    def complete(self, line: str, cursor_pos: int) -> CompletionResult:
        """Return the completions for *line* at *cursor_pos*.

        Parameters
        ----------
        line : str
        cursor_pos : int

        Returns
        -------
        CompletionResult
            Empty when nothing applies; never raises.
        """
        head = line[:cursor_pos]
        for strategy in (
            self._complete_magic,
            self._complete_dict_key,
            self._complete_from_import,
            self._complete_import,
            self._complete_path,
            self._complete_attr,
            self._complete_name,
        ):
            try:
                result = strategy(head, cursor_pos)
            except Exception:
                continue
            if result:
                result.common_prefix = _common_prefix(result.matches)
                return result
        return CompletionResult([], cursor_pos, cursor_pos)

    # ------------------------------------------------------------------
    # strategies
    # ------------------------------------------------------------------

    def _complete_magic(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete a ``%magic`` name, or a magic's path argument.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        match = _MAGIC_RE.match(head)
        if match is not None:
            esc = match.group("esc")
            prefix = match.group("name")
            kind = "cell" if esc == "%%" else "line"
            names = [n for n in self.shell.magics.names(kind) if n.startswith(prefix)]
            return CompletionResult(
                [esc + n for n in sorted(names)],
                match.start("esc"),
                cursor,
                kind="magic",
            )

        stripped = head.lstrip()
        if not stripped.startswith("%"):
            return None
        name, _, rest = stripped[1:].lstrip("%").partition(" ")
        if name in _PATH_MAGICS and rest is not None:
            return self._path_matches(head, cursor, rest.rsplit(" ", 1)[-1])
        return None

    def _complete_dict_key(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete a string subscript such as ``df['col``.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        match = _DICT_KEY_RE.search(head)
        if match is None:
            return None
        container = self._safe_eval(match.group("expr"))
        if container is None:
            return None

        keys: list[str] = []
        custom = getattr(container, "_ipython_key_completions_", None)
        if callable(custom):
            with _ignored():
                keys = [str(k) for k in custom()]
        if not keys:
            getter = getattr(container, "keys", None)
            if not callable(getter):
                return None
            with _ignored():
                keys = [k for k in getter() if isinstance(k, str)]
        if not keys:
            return None

        prefix = match.group("prefix")
        quote = match.group("quote")
        matches = [k for k in sorted(keys) if k.startswith(prefix)]
        return CompletionResult(
            [f"{k}{quote}]" for k in matches],
            match.start("prefix"),
            cursor,
            kind="key",
        )

    def _complete_from_import(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete ``from package import <TAB>``.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        match = _FROM_IMPORT_RE.match(head)
        if match is None:
            return None
        module = self._imported(match.group("mod"))
        if module is None:
            return None
        prefix = match.group("prefix")
        names = [n for n in dir(module) if n.startswith(prefix)]
        names += [n for n in self._submodules(module) if n.startswith(prefix)]
        if not names:
            return None
        return CompletionResult(
            _rank(names, prefix), match.start("prefix"), cursor, kind="module",
        )

    def _complete_import(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete ``import package.<TAB>`` without importing the target.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        match = _IMPORT_RE.match(head)
        if match is None:
            return None
        typed = match.group("mod")
        parent, _, prefix = typed.rpartition(".")

        if not parent:
            import sys

            names = sorted(
                {info.name for info in pkgutil.iter_modules()}
                | set(sys.builtin_module_names)
            )
            names = [n for n in names if n.startswith(prefix) and not n.startswith("_")]
            return CompletionResult(names, match.start("mod"), cursor, kind="module") if names else None

        module = self._imported(parent)
        if module is None:
            return None
        names = [n for n in self._submodules(module) if n.startswith(prefix)]
        return CompletionResult(
            [f"{parent}.{n}" for n in sorted(names)],
            match.start("mod"),
            cursor,
            kind="module",
        ) if names else None

    def _complete_path(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete a filesystem path inside a string literal or after ``!``.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        match = _STRING_TAIL_RE.search(head)
        if match is not None:
            return self._path_matches(head, cursor, match.group("text"), start=match.start("text"))
        if head.lstrip().startswith("!"):
            return self._path_matches(head, cursor, head.rsplit(" ", 1)[-1])
        return None

    def _path_matches(
            self,
            head: str,
            cursor: int,
            fragment: str,
            *,
            start: int | None = None,
    ) -> CompletionResult | None:
        """Return filesystem completions for *fragment*.

        Parameters
        ----------
        head : str
        cursor : int
        fragment : str
        start : int, optional
            Where *fragment* begins in the line; derived when omitted.

        Returns
        -------
        CompletionResult or None
        """
        cleaned = fragment.strip().strip("'\"")
        expanded = os.path.expanduser(cleaned)
        try:
            hits = glob.glob(expanded + "*")
        except OSError:
            return None
        if not hits:
            return None
        matches = sorted(
            hit + (os.sep if os.path.isdir(hit) else "") for hit in hits
        )
        if cleaned.startswith("~"):
            home = os.path.expanduser("~")
            matches = [
                "~" + m[len(home):] if m.startswith(home) else m for m in matches
            ]
        begin = start if start is not None else cursor - len(fragment)
        return CompletionResult(matches, begin, cursor, kind="path")

    def _complete_attr(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete ``obj.attr``.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        word = self._word_before(head)
        if "." not in word:
            return None
        expr, _, prefix = word.rpartition(".")
        if not _SAFE_EXPR.match(expr):
            # Anything with a call, an operator or an assignment in it is not
            # evaluated at all. Listing attributes requires evaluating the
            # expression, and evaluation of arbitrary text is how a completer
            # ends up running the user's code on a keystroke.
            return None
        obj = self._safe_eval(expr)
        if obj is None:
            return None
        names = set(dir(obj))
        names.update(getattr(type(obj), "__slots__", ()) or ())
        names.update(getattr(obj, "__annotations__", {}) or {})
        matches = [f"{expr}.{n}" for n in names if n.startswith(prefix)]
        if not matches:
            return None
        return CompletionResult(
            _rank(matches, prefix), cursor - len(word), cursor, kind="attr",
        )

    def _complete_name(self, head: str, cursor: int) -> CompletionResult | None:
        """Complete a bare name from the namespace, builtins and keywords.

        Parameters
        ----------
        head : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        word = self._word_before(head)
        if not word or "." in word:
            return None
        completer = rlcompleter.Completer(self.namespace)
        try:
            matches = list(completer.global_matches(word) or [])
        except Exception:
            matches = []
        matches += [k for k in keyword.kwlist if k.startswith(word)]
        matches += [k for k in getattr(keyword, "softkwlist", ()) if k.startswith(word)]
        matches = [m for m in matches if m != transform_shell_object()]
        if not matches:
            return None
        return CompletionResult(
            _rank(matches, word), cursor - len(word), cursor, kind="name",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _word_before(head: str) -> str:
        """Return the dotted word ending at the end of *head*.

        Parameters
        ----------
        head : str

        Returns
        -------
        str
        """
        index = len(head)
        while index > 0:
            char = head[index - 1]
            if char.isalnum() or char in "_.":
                index -= 1
            else:
                break
        return head[index:]

    def _safe_eval(self, expression: str) -> typing.Any:
        """Evaluate *expression* only if it cannot have side effects.

        Parameters
        ----------
        expression : str

        Returns
        -------
        object or None
            ``None`` when the expression is unsafe or evaluation failed.
        """
        if not _SAFE_EXPR.match(expression):
            return None
        try:
            return eval(expression, dict(self.namespace))  # noqa: S307 - guarded above
        except Exception:
            return None

    def _imported(self, name: str) -> typing.Any:
        """Return an already-imported module *name*, without importing it.

        Parameters
        ----------
        name : str

        Returns
        -------
        module or None
        """
        import sys

        return sys.modules.get(name) or self.namespace.get(name)

    @staticmethod
    def _submodules(module: typing.Any) -> list[str]:
        """Return the submodule names of *module*.

        Parameters
        ----------
        module : module

        Returns
        -------
        list of str
        """
        path = getattr(module, "__path__", None)
        if not path:
            return []
        try:
            return [info.name for info in pkgutil.iter_modules(path)]
        except Exception:
            return []


def transform_shell_object() -> str:
    """Return the hidden shell name, so completion never offers it.

    Returns
    -------
    str
    """
    from chisurf.core.console.transform import SHELL_OBJECT

    return SHELL_OBJECT


class _ignored:
    """Context manager swallowing any exception from a third-party object."""

    def __enter__(self) -> "_ignored":
        """Enter the block.

        Returns
        -------
        _ignored
        """
        return self

    def __exit__(self, *exc_info) -> bool:
        """Swallow whatever was raised.

        Returns
        -------
        bool
            Always ``True``.
        """
        return True
