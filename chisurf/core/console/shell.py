"""The interactive shell: namespace, execution, and the whole Qt seam.

:class:`Shell` is what ``get_ipython()`` returns inside the console. It duck-types
enough of IPython's ``InteractiveShell`` that the spellings already sitting in
ChiSurf's shipped ``console_init`` -- ``%matplotlib inline``,
``%config Completer.use_jedi = False`` and ``get_ipython().cache_size = 0`` --
keep working without anyone editing their settings file. That matters more than
it looks: ChiSurf merges packaged defaults *underneath* the user's settings and
never overwrites them, so those three lines are on every existing installation
permanently.

The Qt seam is five optional callbacks. Pass none and the shell is a working
head-less REPL that writes to ``sys.stdout``.
"""

from __future__ import annotations

import builtins
import contextlib
import dataclasses
import sys
import time
import typing

from chisurf.core.console import tracebacks, transform
from chisurf.core.console.interpreter import Interpreter, cell_filename
from chisurf.core.console.streams import InputStream, OutputStream

__all__ = ["Shell", "ExecutionResult", "Bunch"]


class Bunch(dict):
    """An attribute-addressable dict that grows children on demand.

    This is what makes ``%config Completer.use_jedi = False`` succeed. The
    setting names a class chinsole does not have, and the honest options are to
    fail or to accept it; failing would mean every existing ChiSurf install
    prints an error on startup forever, so it is accepted and recorded.
    """

    def __getattr__(self, name: str) -> typing.Any:
        """Return ``self[name]``, creating a child :class:`Bunch` if needed.

        Parameters
        ----------
        name : str

        Returns
        -------
        object
        """
        if name.startswith("__"):
            raise AttributeError(name)
        return self.setdefault(name, Bunch())

    def __setattr__(self, name: str, value: typing.Any) -> None:
        """Store *value* under *name*.

        Parameters
        ----------
        name : str
        value : object
        """
        self[name] = value


@dataclasses.dataclass
class ExecutionResult:
    """What running one cell produced.

    Attributes
    ----------
    source : str
        Exactly what the user typed.
    transformed : str
        The Python it became.
    execution_count : int
    value : object
        The trailing expression's value, when there was one.
    has_value : bool
    error_before_exec : BaseException or None
        A ``SyntaxError`` from compilation.
    error_in_exec : BaseException or None
    interrupted : bool
    elapsed : float
        Wall-clock seconds.
    """

    source: str
    transformed: str
    execution_count: int
    value: typing.Any = None
    has_value: bool = False
    error_before_exec: BaseException | None = None
    error_in_exec: BaseException | None = None
    interrupted: bool = False
    elapsed: float = 0.0

    @property
    def success(self) -> bool:
        """bool: Whether the cell ran without error or interruption."""
        return (
            self.error_before_exec is None
            and self.error_in_exec is None
            and not self.interrupted
        )

    def raise_error(self) -> None:
        """Re-raise whatever the cell raised.

        Raises
        ------
        BaseException
        """
        error = self.error_before_exec or self.error_in_exec
        if error is not None:
            raise error


class Shell:
    """An interactive Python shell with magics, history and rich display.

    Parameters
    ----------
    user_ns : dict, optional
        The namespace cells run in. Created when omitted.
    write : callable, optional
        ``write(stream_name, text)``. Defaults to the real ``sys.stdout`` /
        ``sys.stderr``, which is what makes a shell with no callbacks a usable
        head-less REPL.
    display : callable, optional
        ``display(data, metadata, kind, execution_count)`` where *data* is a
        MIME bundle. Defaults to writing the bundle's ``text/plain``.
    read_input : callable, optional
        ``read_input(prompt, password) -> str``, backing :func:`input`.
    clear : callable, optional
        Clears the screen, for ``%clear``.
    edit_file : callable, optional
        ``edit_file(path, line)``, for ``%edit``.
    history : HistoryManager, optional
    magics : MagicRegistry, optional
        Defaults to a copy of the built-in registry, so one shell registering a
        magic does not alter another's.
    """

    def __init__(
            self,
            user_ns: dict | None = None,
            *,
            write: typing.Callable[[str, str], None] | None = None,
            display: typing.Callable[[dict, dict, str, int | None], None] | None = None,
            read_input: typing.Callable[[str, bool], str] | None = None,
            clear: typing.Callable[[], None] | None = None,
            edit_file: typing.Callable[[str, int], None] | None = None,
            history: typing.Any = None,
            magics: typing.Any = None,
    ) -> None:
        from chisurf.core.console import magics as magics_module
        # Importing for the side effect of populating ``BUILTIN``; the module
        # is a registry of decorated functions, so it must be imported before
        # the registry is copied or every shell starts with no magics at all.
        from chisurf.core.console import magics_builtin  # noqa: F401
        from chisurf.core.console.completer import ChinsoleCompleter
        from chisurf.core.console.formatters import DisplayFormatter
        from chisurf.core.console.history import HistoryManager

        self.user_ns: dict = user_ns if user_ns is not None else {}
        self._write = write
        self._display = display
        self._read_input = read_input
        self._clear = clear
        self._edit_file = edit_file

        self.magics = magics or magics_module.BUILTIN.copy()
        self.history = history if history is not None else HistoryManager()
        self.formatter = DisplayFormatter()
        self.interpreter = Interpreter(self)
        self.completer = ChinsoleCompleter(self)

        self.execution_count = 1
        self.In: list[str] = [""]
        self.Out: dict[int, typing.Any] = {}
        self.config = Bunch()
        self.dir_stack: list[str] = []
        self.aliases: dict[str, str] = {}
        self.xmode = "context"
        self.pdb_on_error = False
        self.last_traceback = None
        self.exit_requested = False

        self._cache_size = 1000
        self._busy = False
        self._post_execute: list[typing.Callable[[], None]] = []
        self._matplotlib_backend: str | None = None

        self._install_namespace()

    # ------------------------------------------------------------------
    # namespace
    # ------------------------------------------------------------------

    def _install_namespace(self) -> None:
        """Seed the user namespace with the shell's own handles."""
        self.user_ns.setdefault("__name__", "__main__")
        self.user_ns.setdefault("__builtins__", builtins)
        self.user_ns[transform.SHELL_OBJECT] = self
        self.user_ns["get_ipython"] = self.get_ipython
        self.user_ns["In"] = self.In
        self.user_ns["Out"] = self.Out
        self.user_ns["_ih"] = self.In
        self.user_ns["_oh"] = self.Out
        # Only fill in ``get_ipython`` globally when nothing else claimed it: a
        # real IPython in the same process must keep its own.
        if not hasattr(builtins, "get_ipython"):
            builtins.get_ipython = self.get_ipython

    def get_ipython(self) -> "Shell":
        """Return this shell.

        Named for the function every interactive Python snippet reaches for.

        Returns
        -------
        Shell
        """
        return self

    def push(self, variables: typing.Mapping[str, typing.Any]) -> None:
        """Add *variables* to the user namespace.

        Parameters
        ----------
        variables : mapping
        """
        self.user_ns.update(variables)

    def reset(self, *, keep: typing.Sequence[str] = (), new_session: bool = True) -> None:
        """Clear the user namespace.

        Parameters
        ----------
        keep : sequence of str, optional
            Names to preserve.
        new_session : bool, optional
            Also reset the execution counter and the input/output caches.
        """
        preserved = {name: self.user_ns[name] for name in keep if name in self.user_ns}
        self.user_ns.clear()
        self.user_ns.update(preserved)
        self._install_namespace()
        if new_session:
            self.execution_count = 1
            del self.In[1:]
            self.Out.clear()

    @property
    def cache_size(self) -> int:
        """int: How many outputs ``Out`` keeps; ``0`` disables it.

        A real property because ChiSurf's shipped ``console_init`` sets it --
        ``get_ipython().cache_size = 0`` -- to stop the console pinning large
        arrays in memory. Accepting the assignment silently and ignoring it
        would reintroduce exactly the leak that line exists to prevent.
        """
        return self._cache_size

    @cache_size.setter
    def cache_size(self, value: int) -> None:
        self._cache_size = max(0, int(value))
        if self._cache_size == 0:
            self.Out.clear()
        else:
            while len(self.Out) > self._cache_size:
                self.Out.pop(min(self.Out), None)

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------

    def write(self, text: str) -> None:
        """Write *text* to the console's stdout channel.

        Parameters
        ----------
        text : str
        """
        if self._write is not None:
            self._write("stdout", text)
        else:
            sys.__stdout__.write(text)

    def write_err(self, text: str) -> None:
        """Write *text* to the console's stderr channel.

        Parameters
        ----------
        text : str
        """
        if self._write is not None:
            self._write("stderr", text)
        else:
            sys.__stderr__.write(text)

    def display_data(
            self,
            data: dict,
            metadata: dict | None = None,
            *,
            kind: str = "display_data",
            execution_count: int | None = None,
    ) -> None:
        """Publish a MIME bundle to the console.

        Parameters
        ----------
        data : dict
            MIME type to payload.
        metadata : dict, optional
        kind : str, optional
            ``"display_data"`` or ``"execute_result"``.
        execution_count : int, optional
        """
        if self._display is not None:
            self._display(data, metadata or {}, kind, execution_count)
            return
        text = data.get("text/plain")
        if text is not None:
            self.write(text if text.endswith("\n") else text + "\n")

    def record_output(self, value: typing.Any) -> None:
        """Cache and display the value of a trailing expression.

        Parameters
        ----------
        value : object
        """
        count = self.execution_count
        builtins._ = value
        self.user_ns["___"] = self.user_ns.get("__")
        self.user_ns["__"] = self.user_ns.get("_")
        self.user_ns["_"] = value
        if self._cache_size:
            self.Out[count] = value
            self.user_ns[f"_{count}"] = value
            while len(self.Out) > self._cache_size:
                self.Out.pop(min(self.Out), None)
        data, metadata = self.formatter.format(value)
        self.display_data(data, metadata, kind="execute_result", execution_count=count)

    def clear_screen(self) -> None:
        """Clear the console, for ``%clear``."""
        if self._clear is not None:
            self._clear()

    def edit(self, path: str, line: int = 0) -> None:
        """Open *path* in an editor, for ``%edit``.

        Parameters
        ----------
        path : str
        line : int, optional
        """
        if self._edit_file is not None:
            self._edit_file(path, line)
        else:
            self.write(f"{path}:{line}\n")

    def read_line(self, prompt: str = "", password: bool = False) -> str:
        """Read one line from the console.

        Parameters
        ----------
        prompt : str, optional
        password : bool, optional

        Returns
        -------
        str

        Raises
        ------
        EOFError
            When the console cannot read input.
        """
        if self._read_input is None:
            raise EOFError("this console cannot read input")
        if prompt:
            self.write(prompt)
        return self._read_input(prompt, password)

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def _redirected(self) -> typing.Iterator[None]:
        """Swap the standard streams and display hook for the console's."""
        saved = (sys.stdout, sys.stderr, sys.stdin, sys.displayhook)
        if self._write is not None:
            sys.stdout = OutputStream("stdout", self._write)
            sys.stderr = OutputStream("stderr", self._write)
        if self._read_input is not None:
            sys.stdin = InputStream(self._read_input)
        sys.displayhook = self.interpreter.displayhook
        try:
            yield
        finally:
            sys.stdout, sys.stderr, sys.stdin, sys.displayhook = saved

    def run_cell(
            self,
            raw: str,
            *,
            store_history: bool = True,
            silent: bool = False,
            filename: str | None = None,
    ) -> ExecutionResult:
        """Run one cell.

        Parameters
        ----------
        raw : str
            Exactly what the user typed, escapes and all.
        store_history : bool, optional
            Record it in ``In`` and the persistent history.
        silent : bool, optional
            Suppress the trailing-expression echo.
        filename : str, optional
            Overrides the generated ``<chinsole-input-N>``.

        Returns
        -------
        ExecutionResult
        """
        if self._busy:
            self.write_err(
                "the console is already running a command; wait for it to finish\n"
            )
            return ExecutionResult(raw, raw, self.execution_count)

        count = self.execution_count
        source = raw

        stripped = raw.strip()
        if stripped.endswith(";") and not stripped.endswith(";;"):
            silent = True

        if store_history and stripped:
            self.In.append(raw)
            self.user_ns["_iii"] = self.user_ns.get("_ii")
            self.user_ns["_ii"] = self.user_ns.get("_i")
            self.user_ns["_i"] = raw
            self.user_ns[f"_i{count}"] = raw
            with contextlib.suppress(Exception):
                self.history.append(raw)

        try:
            transformed = transform.transform_cell(raw, magic_names=self.magics.names())
        except Exception as exc:  # a malformed escape must not kill the console
            self.write_err(f"could not parse input: {exc}\n")
            return ExecutionResult(raw, raw, count, error_before_exec=exc)

        name = filename or cell_filename(count)
        self.interpreter.register_source(transformed, name)

        result = ExecutionResult(source, transformed, count)
        started = time.monotonic()
        self._busy = True
        try:
            try:
                codes = self.interpreter.compile_cell(transformed, name, silent=silent)
            except SyntaxError as exc:
                result.error_before_exec = exc
                self.write_err(tracebacks.format_syntax_error(exc))
                return result

            if not codes:
                return result

            with self._redirected():
                try:
                    self.interpreter.run_codes(codes, self.user_ns)
                except SystemExit:
                    self.exit_requested = True
                except KeyboardInterrupt:
                    result.interrupted = True
                    self.write_err("\nKeyboardInterrupt\n")
                except BaseException as exc:  # noqa: BLE001 - a console shows everything
                    result.error_in_exec = exc
                    self.showtraceback(exc)
        finally:
            self._busy = False
            result.elapsed = time.monotonic() - started
            if store_history and stripped:
                self.execution_count += 1
            self._run_post_execute()

        value = self.Out.get(count)
        if value is not None:
            result.value = value
            result.has_value = True
        return result

    def showtraceback(self, exc: BaseException | None = None) -> None:
        """Render *exc* to the console's error channel.

        Parameters
        ----------
        exc : BaseException, optional
            Defaults to the exception currently being handled.
        """
        if exc is None:
            exc = sys.exc_info()[1]
        if exc is None:
            return
        self.last_traceback = exc
        sys.last_value = exc
        sys.last_type = type(exc)
        sys.last_traceback = exc.__traceback__
        self.write_err(tracebacks.format_exception(exc, mode=self.xmode))
        if self.pdb_on_error:
            with contextlib.suppress(Exception):
                self.run_line_magic("debug", "")

    def register_post_execute(self, func: typing.Callable[[], None]) -> None:
        """Register *func* to run after every cell.

        This is how the inline matplotlib backend flushes figures.

        Parameters
        ----------
        func : callable
        """
        if func not in self._post_execute:
            self._post_execute.append(func)

    def unregister_post_execute(self, func: typing.Callable[[], None]) -> None:
        """Remove a callback registered by :meth:`register_post_execute`.

        Parameters
        ----------
        func : callable
        """
        with contextlib.suppress(ValueError):
            self._post_execute.remove(func)

    def _run_post_execute(self) -> None:
        """Run the post-execute callbacks, surviving a broken one."""
        for func in list(self._post_execute):
            try:
                func()
            except Exception as exc:  # noqa: BLE001
                self.write_err(f"post-execute hook failed: {exc!r}\n")

    # ------------------------------------------------------------------
    # IPython-compatible surface
    # ------------------------------------------------------------------

    def run_line_magic(self, name: str, line: str) -> typing.Any:
        """Run the line magic *name*.

        Parameters
        ----------
        name : str
        line : str

        Returns
        -------
        object
        """
        from chisurf.core.console.magics import MagicError

        try:
            return self.magics.call(self, name, line)
        except MagicError as exc:
            self.write_err(f"{exc}\n")
            return None

    def run_cell_magic(self, name: str, line: str, cell: str) -> typing.Any:
        """Run the cell magic *name*.

        Parameters
        ----------
        name : str
        line : str
        cell : str

        Returns
        -------
        object
        """
        from chisurf.core.console.magics import MagicError

        try:
            return self.magics.call(self, name, line, cell)
        except MagicError as exc:
            self.write_err(f"{exc}\n")
            return None

    def magic(self, arg_s: str) -> typing.Any:
        """Run a magic written as one string, IPython's old spelling.

        Parameters
        ----------
        arg_s : str

        Returns
        -------
        object
        """
        name, _, line = arg_s.lstrip("%").partition(" ")
        return self.run_line_magic(name, line)

    def register_magic_function(
            self,
            func: typing.Callable,
            magic_kind: str = "line",
            magic_name: str | None = None,
    ) -> None:
        """Register *func* as a magic.

        Parameters
        ----------
        func : callable
        magic_kind : str, optional
        magic_name : str, optional
        """
        self.magics.register(magic_name or func.__name__, func, kind=magic_kind)

    def ev(self, expression: str) -> typing.Any:
        """Evaluate *expression* in the user namespace.

        Parameters
        ----------
        expression : str

        Returns
        -------
        object
        """
        return eval(expression, self.user_ns)  # noqa: S307 - that is the point

    def ex(self, source: str) -> None:
        """Execute *source* in the user namespace.

        Parameters
        ----------
        source : str
        """
        exec(source, self.user_ns)  # noqa: S102 - that is the point

    def system(self, cmd: str) -> int:
        """Run *cmd* in a shell, streaming its output to the console.

        Parameters
        ----------
        cmd : str

        Returns
        -------
        int
            The child's exit status.
        """
        from chisurf.core.console.shellcmd import run_streaming

        return run_streaming(self, self.var_expand(cmd))

    def getoutput(self, cmd: str, split: bool = True):
        """Run *cmd* and return its output.

        Parameters
        ----------
        cmd : str
        split : bool, optional
            Return a list of lines rather than one string.

        Returns
        -------
        SList or str
        """
        from chisurf.core.console.shellcmd import capture

        return capture(self, self.var_expand(cmd), split=split)

    def var_expand(self, cmd: str) -> str:
        """Interpolate ``{name}`` and ``$name`` from the user namespace.

        Parameters
        ----------
        cmd : str

        Returns
        -------
        str
            *cmd* unchanged when interpolation fails, because a shell command
            containing a brace is far more likely than a typo'd substitution.
        """
        from chisurf.core.console.shellcmd import expand_variables

        return expand_variables(cmd, self.user_ns)

    def pinfo(self, expression: str, detail_level: int = 0) -> None:
        """Show information about *expression*, backing ``obj?``.

        Parameters
        ----------
        expression : str
        detail_level : int, optional
            ``1`` includes the source, as ``obj??`` does.
        """
        from chisurf.core.console import introspect

        try:
            obj = self.ev(expression)
        except Exception:
            self.write_err(f"no such object: {expression}\n")
            return
        text = introspect.format_info(
            introspect.info(obj, name=expression, detail_level=detail_level)
        )
        self.display_data({"text/plain": text}, {}, kind="page")

    def complete(self, line: str, cursor_pos: int | None = None):
        """Return completions for *line*.

        Parameters
        ----------
        line : str
        cursor_pos : int, optional

        Returns
        -------
        CompletionResult
        """
        return self.completer.complete(
            line, cursor_pos if cursor_pos is not None else len(line)
        )

    def check_complete(self, source: str) -> tuple[str, str]:
        """Return whether *source* is a finished cell.

        Parameters
        ----------
        source : str

        Returns
        -------
        tuple of str
        """
        return transform.check_complete(source)

    def set_next_input(self, text: str, replace: bool = False) -> None:
        """Prefill the prompt with *text*.

        Parameters
        ----------
        text : str
        replace : bool, optional
        """
        self._next_input = (text, replace)

    def enable_matplotlib(self, gui: str | None = None) -> tuple[str, str]:
        """Select a matplotlib backend, backing ``%matplotlib``.

        Parameters
        ----------
        gui : str, optional
            ``"inline"``, ``"qt"``, ``"agg"``, or ``None`` to report the
            current backend.

        Returns
        -------
        tuple of str
            ``(requested, backend)``.
        """
        from chisurf.core.console.mpl_inline import enable

        return enable(self, gui)
