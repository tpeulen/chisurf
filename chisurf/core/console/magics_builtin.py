"""The magics every chinsole shell ships with.

Grouped roughly as IPython groups them, so muscle memory transfers. ``%ls`` and
``%pwd`` are implemented in Python rather than shelled out, which means they
behave identically on Windows -- a small thing that stops a tutorial from
working on one machine and not another.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import time
import typing

from chisurf.core.console.magics import BUILTIN, MagicError, magic_parser, parse_args

__all__ = ["BUILTIN"]

line = BUILTIN.line
cell = BUILTIN.cell


# ----------------------------------------------------------------------
# running code
# ----------------------------------------------------------------------

@line("run")
def _run(shell, args: str):
    """Run a Python file. ``-i`` runs it in the interactive namespace."""
    parser = magic_parser("%run")
    parser.add_argument("-i", action="store_true", dest="interactive")
    parser.add_argument("-t", action="store_true", dest="timeit")
    parser.add_argument("-e", action="store_true", dest="propagate_exit")
    parser.add_argument("-m", dest="module")
    parser.add_argument("rest", nargs="*")
    options = parser.parse_args(parse_args(args))

    if options.module:
        import runpy

        started = time.monotonic()
        runpy.run_module(options.module, run_name="__main__")
        if options.timeit:
            shell.write(f"ran in {time.monotonic() - started:.3f} s\n")
        return None

    if not options.rest:
        raise MagicError("%run needs a filename")

    path = pathlib.Path(os.path.expandvars(os.path.expanduser(options.rest[0])))
    if not path.is_file():
        raise MagicError(f"no such file: {path}")

    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MagicError(f"could not read {path}: {exc}") from exc

    if options.interactive:
        namespace = shell.user_ns
    else:
        namespace = {"__builtins__": __builtins__}
    saved_name = namespace.get("__name__")
    saved_file = namespace.get("__file__")
    namespace["__name__"] = "__main__"
    namespace["__file__"] = str(path)

    saved_argv = list(sys.argv)
    sys.argv = [str(path)] + list(options.rest[1:])
    started = time.monotonic()
    try:
        code = compile(source, str(path), "exec")
        shell.interpreter.register_source(source, str(path))
        exec(code, namespace)  # noqa: S102 - running a file is the feature
    except SystemExit as exc:
        if options.propagate_exit:
            raise
        if exc.code:
            shell.write_err(f"script exited with status {exc.code}\n")
    except BaseException as exc:  # noqa: BLE001
        shell.showtraceback(exc)
    finally:
        sys.argv = saved_argv
        if options.interactive:
            if saved_name is not None:
                namespace["__name__"] = saved_name
            if saved_file is not None:
                namespace["__file__"] = saved_file
            else:
                namespace.pop("__file__", None)
        if options.timeit:
            shell.write(f"ran in {time.monotonic() - started:.3f} s\n")
    return None


@line("load")
def _load(shell, args: str):
    """Load a file's contents into the next prompt."""
    words = parse_args(args)
    if not words:
        raise MagicError("%load needs a filename")
    path = pathlib.Path(os.path.expanduser(words[0]))
    if not path.is_file():
        raise MagicError(f"no such file: {path}")
    shell.set_next_input(path.read_text(encoding="utf-8"), replace=True)
    return None


@line("time")
def _time(shell, args: str):
    """Time one statement."""
    return _timed(shell, args)


@cell("time")
def _time_cell(shell, args: str, body: str):
    """Time a whole cell."""
    return _timed(shell, body)


def _timed(shell, source: str):
    """Run *source* once and report how long it took.

    Parameters
    ----------
    shell : Shell
    source : str

    Returns
    -------
    None
    """
    if not source.strip():
        raise MagicError("%time needs something to run")
    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        exec(compile(source, "<%time>", "exec"), shell.user_ns)  # noqa: S102
    except BaseException as exc:  # noqa: BLE001
        shell.showtraceback(exc)
        return None
    wall = time.perf_counter() - started
    cpu = time.process_time() - cpu_started
    shell.write(f"CPU time: {cpu:.4g} s\nWall time: {wall:.4g} s\n")
    return None


@line("timeit")
def _timeit(shell, args: str):
    """Time a statement repeatedly and report the best run."""
    parser = magic_parser("%timeit")
    parser.add_argument("-n", type=int, dest="number")
    parser.add_argument("-r", type=int, dest="repeat", default=5)
    parser.add_argument("-o", action="store_true", dest="return_result")
    parser.add_argument("-q", action="store_true", dest="quiet")
    known, rest = parser.parse_known_args(parse_args(args))
    statement = " ".join(rest)
    return _run_timeit(shell, statement, known)


@cell("timeit")
def _timeit_cell(shell, args: str, body: str):
    """Time a whole cell repeatedly."""
    parser = magic_parser("%%timeit")
    parser.add_argument("-n", type=int, dest="number")
    parser.add_argument("-r", type=int, dest="repeat", default=5)
    parser.add_argument("-o", action="store_true", dest="return_result")
    parser.add_argument("-q", action="store_true", dest="quiet")
    known, _rest = parser.parse_known_args(parse_args(args))
    return _run_timeit(shell, body, known)


def _run_timeit(shell, statement: str, options):
    """Time *statement* and report.

    Parameters
    ----------
    shell : Shell
    statement : str
    options : argparse.Namespace

    Returns
    -------
    object or None
        A result object when ``-o`` was given.
    """
    import timeit as timeit_module

    if not statement.strip():
        raise MagicError("%timeit needs something to run")

    timer = timeit_module.Timer(statement, globals=shell.user_ns)
    number = options.number
    if not number:
        # Scale the loop count so one run takes ~0.2 s, as timeit's own CLI
        # does; a fixed count is either too slow or statistically meaningless.
        number = 1
        for _ in range(12):
            if timer.timeit(number) >= 0.2:
                break
            number *= 10

    try:
        runs = timer.repeat(repeat=options.repeat, number=number)
    except BaseException as exc:  # noqa: BLE001
        shell.showtraceback(exc)
        return None

    per_loop = [run / number for run in runs]
    best = min(per_loop)
    mean = sum(per_loop) / len(per_loop)
    spread = (sum((value - mean) ** 2 for value in per_loop) / len(per_loop)) ** 0.5

    if not options.quiet:
        shell.write(
            f"{_seconds(mean)} +- {_seconds(spread)} per loop "
            f"(mean +- s.d. of {options.repeat} runs, {number} loop"
            f"{'s' if number != 1 else ''} each); best {_seconds(best)}\n"
        )

    if options.return_result:
        return type(
            "TimeitResult",
            (),
            {
                "best": best, "worst": max(per_loop), "average": mean,
                "stdev": spread, "loops": number, "repeat": options.repeat,
                "timings": per_loop,
                "__repr__": lambda self: f"<TimeitResult {_seconds(best)} per loop>",
            },
        )()
    return None


def _seconds(value: float) -> str:
    """Return *value* seconds with a sensible SI prefix.

    Parameters
    ----------
    value : float

    Returns
    -------
    str
    """
    for scale, unit in ((1.0, "s"), (1e-3, "ms"), (1e-6, "us"), (1e-9, "ns")):
        if value >= scale:
            return f"{value / scale:.3g} {unit}"
    return f"{value:.3g} s"


@line("prun")
def _prun(shell, args: str):
    """Profile a statement with cProfile."""
    return _profile(shell, args)


@cell("prun")
def _prun_cell(shell, args: str, body: str):
    """Profile a whole cell with cProfile."""
    return _profile(shell, body)


def _profile(shell, source: str):
    """Run *source* under cProfile and print the top entries.

    Parameters
    ----------
    shell : Shell
    source : str

    Returns
    -------
    None
    """
    import cProfile
    import pstats

    if not source.strip():
        raise MagicError("%prun needs something to run")
    profiler = cProfile.Profile()
    try:
        profiler.runctx(source, shell.user_ns, shell.user_ns)
    except BaseException as exc:  # noqa: BLE001
        shell.showtraceback(exc)
        return None
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer).sort_stats("cumulative")
    stats.print_stats(25)
    shell.display_data({"text/plain": buffer.getvalue()}, {"title": "%prun"}, kind="page")
    return None


# ----------------------------------------------------------------------
# the filesystem
# ----------------------------------------------------------------------

@line("pwd")
def _pwd(shell, args: str):
    """Print the working directory."""
    return os.getcwd()


@line("cd")
def _cd(shell, args: str):
    """Change directory. ``-`` returns to the previous one."""
    target = args.strip().strip("'\"")
    previous = os.getcwd()
    if not target:
        target = str(pathlib.Path.home())
    elif target == "-":
        if not shell.dir_stack:
            raise MagicError("no previous directory")
        target = shell.dir_stack.pop()
    try:
        os.chdir(os.path.expandvars(os.path.expanduser(target)))
    except OSError as exc:
        raise MagicError(f"could not change directory: {exc}") from exc
    shell.dir_stack.append(previous)
    shell.write(os.getcwd() + "\n")
    return None


@line("pushd")
def _pushd(shell, args: str):
    """Change directory, remembering the current one."""
    return _cd(shell, args)


@line("popd")
def _popd(shell, args: str):
    """Return to the directory ``%pushd`` came from."""
    return _cd(shell, "-")


@line("dirs")
def _dirs(shell, args: str):
    """Show the directory stack."""
    shell.write("\n".join(reversed(shell.dir_stack)) + "\n")
    return None


@line("ls")
def _ls(shell, args: str):
    """List a directory. Implemented in Python, so it behaves the same everywhere."""
    parser = magic_parser("%ls")
    parser.add_argument("-l", action="store_true", dest="long")
    parser.add_argument("-a", action="store_true", dest="all")
    known, rest = parser.parse_known_args(parse_args(args))
    target = pathlib.Path(rest[0] if rest else ".").expanduser()

    try:
        entries = sorted(
            os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower())
        )
    except OSError as exc:
        raise MagicError(f"could not list {target}: {exc}") from exc

    if not known.all:
        entries = [e for e in entries if not e.name.startswith(".")]

    if known.long:
        lines = []
        for entry in entries:
            try:
                stat = entry.stat()
                size = stat.st_size
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            except OSError:
                size, when = 0, "?"
            flag = "d" if entry.is_dir() else "-"
            lines.append(f"{flag} {size:>12} {when}  {entry.name}")
        shell.write("\n".join(lines) + "\n" if lines else "")
        return None

    names = [entry.name + (os.sep if entry.is_dir() else "") for entry in entries]
    shell.write(_columnise(names) )
    return None


def _columnise(names: typing.Sequence[str], width: int = 80) -> str:
    """Lay *names* out in columns.

    Parameters
    ----------
    names : sequence of str
    width : int, optional

    Returns
    -------
    str
    """
    if not names:
        return ""
    longest = max(len(name) for name in names) + 2
    columns = max(1, width // longest)
    rows = (len(names) + columns - 1) // columns
    lines = []
    for row in range(rows):
        cells = names[row * columns:(row + 1) * columns]
        lines.append("".join(name.ljust(longest) for name in cells).rstrip())
    return "\n".join(lines) + "\n"


@cell("writefile")
def _writefile(shell, args: str, body: str):
    """Write the cell body to a file."""
    parser = magic_parser("%%writefile")
    parser.add_argument("-a", action="store_true", dest="append")
    parser.add_argument("path")
    options = parser.parse_args(parse_args(args))
    path = pathlib.Path(os.path.expanduser(options.path))
    mode = "a" if options.append else "w"
    try:
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(body if body.endswith("\n") else body + "\n")
    except OSError as exc:
        raise MagicError(f"could not write {path}: {exc}") from exc
    shell.write(f"{'Appended to' if options.append else 'Wrote'} {path}\n")
    return None


# ----------------------------------------------------------------------
# the namespace
# ----------------------------------------------------------------------

def _user_names(shell) -> list[str]:
    """Return the interesting names in the user namespace.

    Parameters
    ----------
    shell : Shell

    Returns
    -------
    list of str
    """
    from chisurf.core.console.transform import SHELL_OBJECT

    hidden = {
        SHELL_OBJECT, "get_ipython", "In", "Out", "_ih", "_oh", "_", "__", "___",
        "_i", "_ii", "_iii", "exit", "quit",
    }
    return sorted(
        name for name, value in shell.user_ns.items()
        if not name.startswith("_")
        and name not in hidden
        and not _is_module_or_builtin(value)
    )


def _is_module_or_builtin(value: typing.Any) -> bool:
    """Return whether *value* is uninteresting to ``%who``.

    Parameters
    ----------
    value : object

    Returns
    -------
    bool
    """
    import types

    return isinstance(value, types.ModuleType)


@line("who")
def _who(shell, args: str):
    """List the names defined in the session."""
    names = _user_names(shell)
    if not names:
        shell.write("Interactive namespace is empty.\n")
        return None
    shell.write(_columnise(names))
    return None


@line("who_ls")
def _who_ls(shell, args: str):
    """Return the names defined in the session as a list."""
    return _user_names(shell)


@line("whos")
def _whos(shell, args: str):
    """List the names defined in the session with their types and values."""
    names = _user_names(shell)
    if not names:
        shell.write("Interactive namespace is empty.\n")
        return None
    rows = [("Variable", "Type", "Data/Info")]
    for name in names:
        value = shell.user_ns[name]
        try:
            text = repr(value)
        except Exception as exc:  # noqa: BLE001
            text = f"<unprintable: {exc!r}>"
        if len(text) > 60:
            text = text[:57] + "..."
        rows.append((name, type(value).__name__, text.replace("\n", " ")))
    widths = [max(len(row[i]) for row in rows) + 2 for i in range(3)]
    lines = [
        "".join(cell_text.ljust(widths[i]) for i, cell_text in enumerate(row)).rstrip()
        for row in rows
    ]
    lines.insert(1, "-" * min(sum(widths), 100))
    shell.write("\n".join(lines) + "\n")
    return None


@line("reset")
def _reset(shell, args: str):
    """Clear the interactive namespace."""
    words = parse_args(args)
    if "-f" not in words and shell._read_input is not None:
        answer = shell.read_line("Clear the interactive namespace? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            shell.write("cancelled\n")
            return None
    shell.reset(new_session="-s" not in words)
    shell.write("Interactive namespace cleared.\n")
    return None


@line("clear")
def _clear(shell, args: str):
    """Clear the console."""
    shell.clear_screen()
    return None


@line("history")
def _history(shell, args: str):
    """Show the input history."""
    parser = magic_parser("%history")
    parser.add_argument("-n", action="store_true", dest="numbers")
    parser.add_argument("-f", dest="path")
    parser.add_argument("-g", dest="grep")
    known, rest = parser.parse_known_args(parse_args(args))

    entries = shell.history.range(" ".join(rest))
    if known.grep:
        needle = known.grep.lower()
        entries = [(n, s) for n, s in entries if needle in s.lower()]

    lines = [
        (f"{number:>4}: {source}" if known.numbers else source)
        for number, source in entries
    ]
    text = "\n".join(lines) + ("\n" if lines else "")

    if known.path:
        pathlib.Path(known.path).write_text(text, encoding="utf-8")
        shell.write(f"wrote {len(entries)} entries to {known.path}\n")
        return None
    shell.display_data({"text/plain": text}, {"title": "%history"}, kind="page")
    return None


# ----------------------------------------------------------------------
# introspection and configuration
# ----------------------------------------------------------------------

@line("pinfo")
def _pinfo(shell, args: str):
    """Show information about an object, as ``obj?`` does."""
    shell.pinfo(args.strip(), detail_level=0)
    return None


@line("pinfo2")
def _pinfo2(shell, args: str):
    """Show an object's source, as ``obj??`` does."""
    shell.pinfo(args.strip(), detail_level=1)
    return None


@line("pdoc")
def _pdoc(shell, args: str):
    """Show an object's docstring."""
    import inspect

    obj = shell.ev(args.strip())
    shell.display_data({"text/plain": inspect.getdoc(obj) or "(no docstring)"}, {}, kind="page")
    return None


@line("psource")
def _psource(shell, args: str):
    """Show an object's source."""
    import inspect

    obj = shell.ev(args.strip())
    try:
        source = inspect.getsource(obj)
    except (OSError, TypeError) as exc:
        raise MagicError(f"no source available: {exc}") from exc
    shell.display_data({"text/plain": source}, {}, kind="page")
    return None


@line("config")
def _config(shell, args: str):
    """Set a configuration value, e.g. ``%config InlineBackend.figure_format = 'svg'``."""
    text = args.strip()
    if not text:
        shell.write(_format_config(shell.config) or "(nothing configured)\n")
        return None
    if "=" not in text:
        target = shell.config
        for part in text.split("."):
            target = target[part] if part in target else getattr(target, part)
        shell.write(f"{text} = {target!r}\n")
        return None

    target_name, _, value_text = text.partition("=")
    parts = [part.strip() for part in target_name.strip().split(".") if part.strip()]
    if len(parts) < 2:
        raise MagicError("%config takes Class.trait = value")
    try:
        value = eval(value_text.strip(), {"__builtins__": {}}, {})  # noqa: S307
    except Exception:
        value = value_text.strip()

    node = shell.config
    for part in parts[:-1]:
        node = getattr(node, part)
    node[parts[-1]] = value

    if parts[0] not in ("InlineBackend",):
        # Accepting an unknown trait rather than failing is deliberate: the
        # shipped console_init sets Completer.use_jedi, chinsole has no jedi,
        # and erroring would print a warning on every start for every user.
        import chisurf

        chisurf.logging.debug(
            "%%config %s has no effect in chinsole; recorded only", target_name.strip()
        )
    return None


def _format_config(node, prefix: str = "") -> str:
    """Render the configuration tree.

    Parameters
    ----------
    node : Bunch
    prefix : str, optional

    Returns
    -------
    str
    """
    lines = []
    for key in sorted(node):
        value = node[key]
        if isinstance(value, dict):
            lines.append(_format_config(value, f"{prefix}{key}."))
        else:
            lines.append(f"{prefix}{key} = {value!r}\n")
    return "".join(lines)


@line("xmode")
def _xmode(shell, args: str):
    """Set the traceback style: plain, context or verbose."""
    from chisurf.core.console.tracebacks import MODES

    mode = args.strip().lower()
    if not mode:
        shell.write(f"{shell.xmode}\n")
        return None
    if mode not in MODES:
        raise MagicError(f"unknown mode {mode!r}; known: {', '.join(MODES)}")
    shell.xmode = mode
    shell.write(f"Exception reporting mode: {mode}\n")
    return None


@line("pdb")
def _pdb(shell, args: str):
    """Toggle dropping into the debugger when an exception escapes."""
    text = args.strip().lower()
    if text in ("on", "1", "true"):
        shell.pdb_on_error = True
    elif text in ("off", "0", "false"):
        shell.pdb_on_error = False
    else:
        shell.pdb_on_error = not shell.pdb_on_error
    shell.write(f"Automatic pdb calling has been turned {'ON' if shell.pdb_on_error else 'OFF'}\n")
    return None


@line("debug")
def _debug(shell, args: str):
    """Debug the last exception."""
    import pdb

    if shell.last_traceback is None or shell.last_traceback.__traceback__ is None:
        raise MagicError("no traceback to debug")
    if shell._read_input is None:
        raise MagicError("this console cannot read input, so pdb cannot run")

    from chisurf.core.console.streams import InputStream, OutputStream

    debugger = pdb.Pdb(
        stdin=InputStream(shell._read_input),
        stdout=OutputStream("stdout", shell._write) if shell._write else sys.stdout,
    )
    debugger.use_rawinput = False
    debugger.reset()
    debugger.interaction(None, shell.last_traceback.__traceback__)
    return None


@line("matplotlib")
def _matplotlib(shell, args: str):
    """Select a matplotlib backend, e.g. ``%matplotlib inline``."""
    requested, backend = shell.enable_matplotlib(args.strip() or None)
    if not requested:
        shell.write(f"Using matplotlib backend: {backend}\n")
    return None


@line("pylab")
def _pylab(shell, args: str):
    """Select a matplotlib backend and import numpy and pyplot."""
    _matplotlib(shell, args)
    shell.ex("import numpy\nimport numpy as np\nimport matplotlib.pyplot as plt")
    shell.write("Populating the interactive namespace from numpy and matplotlib\n")
    return None


@line("lsmagic")
def _lsmagic(shell, args: str):
    """List the available magics."""
    lines = ["Line magics:", _columnise(["%" + n for n in shell.magics.names("line")])]
    lines.append("Cell magics:")
    lines.append(_columnise(["%%" + n for n in shell.magics.names("cell")]))
    shell.display_data({"text/plain": "\n".join(lines)}, {"title": "%lsmagic"}, kind="page")
    return None


@line("magic")
def _magic(shell, args: str):
    """Describe the available magics."""
    lines = []
    for kind, marker in (("line", "%"), ("cell", "%%")):
        lines.append(f"=== {kind} magics ===")
        for spec in shell.magics.specs(kind):
            summary = spec.doc.splitlines()[0] if spec.doc else ""
            lines.append(f"  {marker}{spec.name:<14} {summary}")
        lines.append("")
    shell.display_data({"text/plain": "\n".join(lines)}, {}, kind="page")
    return None


@line("quickref")
def _quickref(shell, args: str):
    """Show a short reference card."""
    shell.display_data({"text/plain": _QUICKREF}, {"title": "%quickref"}, kind="page")
    return None


@line("edit")
def _edit(shell, args: str):
    """Open a file, or an object's source, in the ChiSurf editor."""
    import inspect

    text = args.strip().strip("'\"")
    if not text:
        raise MagicError("%edit needs a filename or an object")
    candidate = pathlib.Path(os.path.expanduser(text))
    if candidate.exists():
        shell.edit(str(candidate), 0)
        return None
    try:
        obj = shell.ev(text)
        path = inspect.getsourcefile(obj)
        line_number = inspect.getsourcelines(obj)[1]
    except Exception as exc:
        raise MagicError(f"cannot locate source for {text!r}: {exc}") from exc
    if not path:
        raise MagicError(f"{text!r} has no source file")
    shell.edit(path, line_number)
    return None


# ----------------------------------------------------------------------
# environment
# ----------------------------------------------------------------------

@line("env")
def _env(shell, args: str):
    """Show, or set, environment variables."""
    text = args.strip()
    if not text:
        lines = [f"{key}={value}" for key, value in sorted(os.environ.items())]
        shell.display_data({"text/plain": "\n".join(lines)}, {}, kind="page")
        return None
    if "=" in text:
        key, _, value = text.partition("=")
        os.environ[key.strip()] = value.strip()
        return None
    return os.environ.get(text)


@line("set_env")
def _set_env(shell, args: str):
    """Set an environment variable."""
    text = args.strip()
    if "=" not in text:
        key, _, value = text.partition(" ")
    else:
        key, _, value = text.partition("=")
    if not key.strip():
        raise MagicError("%set_env needs NAME=value")
    os.environ[key.strip()] = value.strip()
    return None


@line("alias")
def _alias(shell, args: str):
    """Define a shell alias."""
    text = args.strip()
    if not text:
        for name, command in sorted(shell.aliases.items()):
            shell.write(f"{name} = {command}\n")
        return None
    name, _, command = text.partition(" ")
    if not command:
        raise MagicError("%alias needs a name and a command")
    shell.aliases[name] = command
    return None


@line("unalias")
def _unalias(shell, args: str):
    """Remove a shell alias."""
    shell.aliases.pop(args.strip(), None)
    return None


@cell("capture")
def _capture(shell, args: str, body: str):
    """Run the cell with its output captured instead of displayed."""
    from chisurf.core.console.streams import CapturingStream

    target = args.strip()
    out = CapturingStream("stdout")
    err = CapturingStream("stderr")
    saved = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = out, err
    try:
        exec(compile(body, "<%%capture>", "exec"), shell.user_ns)  # noqa: S102
    except BaseException as exc:  # noqa: BLE001
        sys.stdout, sys.stderr = saved
        shell.showtraceback(exc)
        return None
    finally:
        sys.stdout, sys.stderr = saved
    if target:
        shell.user_ns[target] = type(
            "CapturedIO",
            (),
            {
                "stdout": out.getvalue(), "stderr": err.getvalue(),
                "__repr__": lambda self: self.stdout,
                "show": lambda self: shell.write(self.stdout),
            },
        )()
    return None


@cell("bash")
def _bash(shell, args: str, body: str):
    """Run the cell body with bash."""
    return _run_with(shell, body, "bash")


@cell("sh")
def _sh(shell, args: str, body: str):
    """Run the cell body with sh."""
    return _run_with(shell, body, "sh")


def _run_with(shell, body: str, interpreter: str):
    """Run *body* through *interpreter*.

    Parameters
    ----------
    shell : Shell
    body : str
    interpreter : str

    Returns
    -------
    None
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as handle:
        handle.write(body)
        path = handle.name
    try:
        shell.system(f"{interpreter} {path}")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)
    return None


@cell("html")
def _html(shell, args: str, body: str):
    """Render the cell body as HTML."""
    shell.display_data({"text/html": body, "text/plain": body}, {})
    return None


@cell("markdown")
def _markdown(shell, args: str, body: str):
    """Render the cell body as Markdown."""
    shell.display_data({"text/markdown": body, "text/plain": body}, {})
    return None


@cell("latex")
def _latex(shell, args: str, body: str):
    """Render the cell body as LaTeX. Only maths is supported, via mathtext."""
    shell.display_data({"text/latex": body, "text/plain": body}, {})
    return None


@cell("javascript")
def _javascript(shell, args: str, body: str):
    """Not supported: ChiSurf's console has no JavaScript engine."""
    raise MagicError(
        "%%javascript needs a browser; ChiSurf's console renders Qt rich text, "
        "not a web page"
    )


@cell("python")
def _python_cell(shell, args: str, body: str):
    """Run the cell body as ordinary Python."""
    exec(compile(body, "<%%python>", "exec"), shell.user_ns)  # noqa: S102
    return None


_QUICKREF = """\
chinsole quick reference
========================

  obj?            show information about obj
  obj??           show obj's source
  %magic          describe all magics          %lsmagic   list them
  !cmd            run cmd in the shell         x = !cmd   capture its output
  %run -i file    run a file in this namespace
  %time / %timeit time a statement             %prun      profile it
  %who / %whos    what is defined              %reset     clear it
  %history        what you have typed          Ctrl-R     search it
  %matplotlib inline | qt                      %config    set an option
  %xmode          traceback detail             %debug     debug the last error
  %cd %pwd %ls    move around                  %edit      open in the editor

  _ __ ___        the last three results       Out[n]     result n
  In[n]           input n                      Ctrl-C     interrupt
"""
