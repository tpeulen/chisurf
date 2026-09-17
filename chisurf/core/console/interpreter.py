"""Compile and run one cell.

The interesting part is how a cell's trailing expression comes to be echoed.
Splitting the cell so the last expression compiles in ``"single"`` mode -- and
not evaluating it ourselves -- means CPython calls :data:`sys.displayhook` for
us, and ``None``-suppression, ``Out[n]`` caching and the ``_``/``__``/``___``
rotation all happen in exactly one place, with exactly the semantics the real
interpreter has.
"""

from __future__ import annotations

import ast
import linecache
import types
import typing

__all__ = ["Interpreter", "cell_filename"]

#: Compile flags that let a cell contain a top-level ``await``.
_TOP_LEVEL_AWAIT = getattr(ast, "PyCF_ALLOW_TOP_LEVEL_AWAIT", 0)


def cell_filename(execution_count: int) -> str:
    """Return the pseudo-filename for a cell.

    Parameters
    ----------
    execution_count : int

    Returns
    -------
    str
    """
    return f"<chinsole-input-{execution_count}>"


class Interpreter:
    """Compiles and executes cells for a :class:`~chisurf.core.console.shell.Shell`.

    Parameters
    ----------
    shell : Shell
        Owner; consulted for the display hook and the output streams.
    """

    def __init__(self, shell: typing.Any) -> None:
        self.shell = shell
        #: Accumulated ``__future__`` flags, so ``from __future__ import
        #: annotations`` typed at the prompt stays in force for the session --
        #: which is what :class:`codeop.Compile` does for the stock REPL.
        self.compile_flags = 0

    def register_source(self, source: str, filename: str) -> None:
        """Make *source* visible to :mod:`linecache` under *filename*.

        Without this a traceback from a cell shows no source line, and
        :func:`inspect.getsource` on a function defined at the prompt fails.

        Parameters
        ----------
        source : str
        filename : str
        """
        lines = [line + "\n" for line in source.splitlines()]
        linecache.cache[filename] = (len(source), None, lines, filename)

    def compile_cell(
        self,
        source: str,
        filename: str,
        *,
        silent: bool = False,
    ) -> list[types.CodeType]:
        """Compile *source* into one or two code objects.

        Parameters
        ----------
        source : str
            Already transformed Python.
        filename : str
        silent : bool, optional
            Suppress the trailing-expression echo, as a trailing ``;`` does.

        Returns
        -------
        list of types.CodeType
            One object for the leading statements (when there are any) and one
            for the trailing expression compiled in ``"single"`` mode.

        Raises
        ------
        SyntaxError
            Propagated to the caller, which renders it with a caret.
        """
        flags = self.compile_flags | _TOP_LEVEL_AWAIT
        tree = compile(
            source,
            filename,
            "exec",
            flags | ast.PyCF_ONLY_AST,
            dont_inherit=True,
        )
        self._absorb_future_flags(tree)
        flags = self.compile_flags | _TOP_LEVEL_AWAIT

        body = list(tree.body)
        if not body:
            return []

        if not silent and isinstance(body[-1], ast.Expr):
            head, tail = body[:-1], body[-1]
            codes: list[types.CodeType] = []
            if head:
                module = ast.Module(body=head, type_ignores=tree.type_ignores)
                codes.append(compile(module, filename, "exec", flags, dont_inherit=True))
            interactive = ast.Interactive(body=[tail])
            codes.append(compile(interactive, filename, "single", flags, dont_inherit=True))
            return codes

        return [compile(tree, filename, "exec", flags, dont_inherit=True)]

    def _absorb_future_flags(self, tree: ast.Module) -> None:
        """Record any ``__future__`` import in *tree* for later cells.

        Parameters
        ----------
        tree : ast.Module
        """
        import __future__ as future_module

        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.module != "__future__":
                continue
            for alias in node.names:
                feature = getattr(future_module, alias.name, None)
                if feature is not None:
                    self.compile_flags |= feature.compiler_flag

    def run_codes(
        self,
        codes: typing.Sequence[types.CodeType],
        namespace: dict,
    ) -> None:
        """Execute *codes* in *namespace*.

        Parameters
        ----------
        codes : sequence of types.CodeType
        namespace : dict
            Used as both globals and locals, so a comprehension at the prompt
            can see names defined in an earlier cell. Passing two different
            mappings is the classic way to make ``[x for _ in y]`` raise
            ``NameError`` in a REPL.

        Raises
        ------
        BaseException
            Whatever the user's code raised.
        """
        for code in codes:
            if code.co_flags & 0x80:  # CO_COROUTINE
                self._run_coroutine(code, namespace)
            else:
                exec(code, namespace)

    def _run_coroutine(self, code: types.CodeType, namespace: dict) -> None:
        """Drive a cell that used a top-level ``await``.

        Parameters
        ----------
        code : types.CodeType
        namespace : dict
        """
        import asyncio

        coroutine = eval(code, namespace)  # noqa: S307 - the code object is ours
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is not None:
            coroutine.close()
            self.shell.write_err(
                "top-level await cannot run while an event loop is already "
                "running in this thread; wrap it in a task instead\n"
            )
            return

        asyncio.run(coroutine)

    def displayhook(self, value: typing.Any) -> None:
        """Record and display the value of a trailing expression.

        Installed as :data:`sys.displayhook` while a cell runs, so CPython
        calls it for the ``"single"``-mode code object and never for a
        statement.

        Parameters
        ----------
        value : object
        """
        if value is None:
            return
        self.shell.record_output(value)
