"""A PTY session: a child process on a pseudo-terminal, read into a screen.

The classic pattern, in the stdlib only: :func:`pty.fork` gives the child a
controlling terminal (a plain ``subprocess`` pipe does not -- the child would
see ``isatty() == False``, no job control, no window size), the parent reads
the master side on a thread of its own and feeds the screen, and a resize sets
the window size the child's ``ioctl(TIOCSWINSZ)`` asks about (delivered as
``SIGWINCH``).

The screen is updated on the reader thread; the frame thread only *reads* it
(the cells are replaced, never mutated in place, so a draw during a feed sees
a consistent line). UTF-8 is decoded incrementally: a multi-byte character
split across two reads is held back by the codec, not mangled.

Windows has no ``pty`` module: the terminal plugin's factory reports that and
draws a message instead of a session.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import pty
import signal
import struct
import termios
import threading
import time

from .screen import TerminalScreen

__all__ = ["PtySession", "spawn"]


def spawn(
    argv: list[str],
    *,
    columns: int = 80,
    rows: int = 24,
    cwd: str | None = None,
    env: dict | None = None,
    max_scrollback: int = 2000,
) -> PtySession:
    """Run *argv* on a new pseudo-terminal and return its live session.

    Parameters
    ----------
    argv : list of str
        The command; ``["/bin/zsh", "-i"]`` (or ``SHELL``) for a shell.
    columns, rows : int
        The initial terminal size.
    cwd : str, optional
        The child's working directory.
    env : dict, optional
        The child's environment (``TERM=xterm-256color`` is added when unset).
    max_scrollback : int
        Lines kept above the grid.
    """
    return PtySession(argv, columns=columns, rows=rows, cwd=cwd, env=env,
                      max_scrollback=max_scrollback)


class PtySession:
    """One child process on a PTY, its output decoded into a :class:`TerminalScreen`.

    Parameters
    ----------
    argv : list of str
    columns, rows, cwd, env, max_scrollback
        As :func:`spawn`.
    """

    def __init__(
        self,
        argv: list[str],
        *,
        columns: int = 80,
        rows: int = 24,
        cwd: str | None = None,
        env: dict | None = None,
        max_scrollback: int = 2000,
    ) -> None:
        self.argv = [str(a) for a in argv]
        self.screen = TerminalScreen(columns, rows, max_scrollback=max_scrollback)
        child_env = dict(os.environ if env is None else env)
        child_env.setdefault("TERM", "xterm-256color")
        child_env.setdefault("COLUMNS", str(int(columns)))
        child_env.setdefault("LINES", str(int(rows)))
        # openpty (posix_openpt + grantpt + unlockpt) BEFORE the fork, then a
        # plain fork + exec: this process is multi-threaded (the GUI), and
        # Python warns that forkpty's pre-exec work can deadlock in the child.
        # The window here is the few syscalls between fork and exec, none of
        # which take a lock.
        master_fd, slave_fd = pty.openpty()
        winsize = struct.pack("HHHH", int(rows), int(columns), 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        pid = os.fork()
        if pid == 0:
            # Child: the slave becomes stdin/out/err and the controlling
            # terminal (setsid + TIOCSCTTY), then exec replaces everything.
            try:
                os.setsid()
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                os.close(master_fd)
                if cwd:
                    os.chdir(cwd)
                os.execvpe(self.argv[0], self.argv, child_env)
            except BaseException:
                os._exit(127)
        os.close(slave_fd)
        self.pid = pid
        self._master = master_fd
        self._decoder = _IncrementalUtf8()
        self._lock = threading.Lock()
        self._dead = threading.Event()
        self.exit_status: int | None = None
        self._closing = False
        self._reader = threading.Thread(
            target=self._read_loop, name=f"terminal-pty-{pid}", daemon=True
        )
        self._reader.start()

    # ── state ─────────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        """Whether the child has not been waited on as exited yet."""
        return self.exit_status is None and not self._dead.is_set()

    def poll_status(self) -> int | None:
        """Collect the exit status if it is there; ``None`` while it runs."""
        if self.exit_status is not None:
            return self.exit_status
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self._dead.set()
            return self.exit_status
        if pid == 0:
            return None
        return self._reap(status)

    def wait(self, timeout: float | None = None) -> int | None:
        """Block until the child exits (collecting its status); ``None`` on timeout."""
        if self.exit_status is not None:
            return self.exit_status
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                self._dead.set()
                return self.exit_status
            if pid != 0:
                return self._reap(status)
            if end is not None and time.monotonic() >= end:
                return None
            time.sleep(0.01)

    def _reap(self, status: int) -> int:
        if os.WIFEXITED(status):
            self.exit_status = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            self.exit_status = 128 + os.WTERMSIG(status)
        else:
            self.exit_status = status
        self._dead.set()
        return self.exit_status

    # ── io ────────────────────────────────────────────────────────────────

    def write(self, data: bytes | str) -> None:
        """Send *data* to the child (keystrokes, pasted text)."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            os.write(self._master, data)
        except OSError:
            pass  # the child went away mid-write; the reader will notice

    def resize(self, columns: int, rows: int) -> None:
        """Set the PTY's window size and resize the screen."""
        if not self.alive and self.exit_status is not None:
            pass
        try:
            winsize = struct.pack("HHHH", int(rows), int(columns), 0, 0)
            fcntl.ioctl(self._master, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass
        with self._lock:
            self.screen.resize(columns, rows)

    def close(self) -> None:
        """Terminate the child (SIGHUP, then SIGKILL) and stop reading.

        The master fd belongs to the reader thread: on macOS a ``close`` of an
        fd another thread is blocked reading can itself block until the read
        ends, so the fd is only closed here as a last resort if the reader
        never came back.
        """
        if self._closing:
            return
        self._closing = True
        # Decide on the exit status, not on ``alive``: the reader marks the child dead as
        # soon as the pty reports EOF, before anyone waited on it, and skipping the wait
        # then left a zombie for every closed pane.
        if self.poll_status() is None:
            with contextlib.suppress(OSError):
                os.kill(self.pid, signal.SIGHUP)
            end = time.monotonic() + 0.5
            while self.poll_status() is None and time.monotonic() < end:
                time.sleep(0.01)
            if self.poll_status() is None:
                with contextlib.suppress(OSError):
                    os.kill(self.pid, signal.SIGKILL)
                self.wait(timeout=2.0)
        self._reader.join(timeout=3.0)
        if self._reader.is_alive():
            with contextlib.suppress(OSError):
                os.close(self._master)
            self._reader.join(timeout=1.0)

    # ── the reader ────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        try:
            while not self._closing:
                try:
                    data = os.read(self._master, 65536)
                except OSError:
                    break  # EIO: the child closed its side (it exited)
                if not data:
                    break
                with self._lock:
                    self.screen.feed(self._decoder.decode(data))
        finally:
            # The reader owns the master: it closes it here (see close()).
            with contextlib.suppress(OSError):
                os.close(self._master)
            self._decoder.decode(b"", final=True)
            self._dead.set()
            self.poll_status()

    def snapshot_lines(self) -> list[str]:
        """The visible lines as text (a convenience for tests and logging)."""
        return [text for _i, text in self.screen.visible(0)]


class _IncrementalUtf8:
    """A UTF-8 decoder that holds a character split across reads."""

    def __init__(self) -> None:
        import codecs

        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def decode(self, data: bytes, final: bool = False) -> str:
        return self._decoder.decode(data, final)
