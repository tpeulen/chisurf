"""The on-device model ChiSurf's agent uses by default.

ChiSurf's default AI runs on the user's own machine: Liquid AI's LFM3-1.7B,
served by llama.cpp's ``llama-server`` through the same OpenAI-compatible
``/chat/completions`` API every other provider speaks. The model is about a
gigabyte at 4-bit, needs no GPU, and runs on Linux, macOS and Windows; the
measurements never leave the computer.

This module is the toolchain around it:

* :func:`find_llama_server` locates the ``llama-server`` binary (the ChiSurf
  environment ships it; a system install on ``PATH`` works as well);
* :func:`server_command` builds the command line, including the sampling
  Liquid AI recommends for tool use and agents (``temperature 0.1``,
  ``top_k 50``, ``repeat_penalty 1.1``) and ``--jinja``, without which the
  model's XML tool calls arrive as prose instead of structured ``tool_calls``;
* :func:`ensure_server` starts the server on first use and waits until the
  model is loaded. The first start downloads the GGUF from Hugging Face into
  llama.cpp's cache; later starts read it from disk.

A server the user started themselves (``llama-server``, ``llama serve``,
Ollama, LM Studio) is used as it is: ChiSurf only starts one when nothing
answers at the configured address.
"""

from __future__ import annotations

import atexit
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

#: Hugging Face repository of the default model's GGUF builds.
LFM3_REPO = "LiquidAI/LFM3-1.7B-GGUF"
#: Quantisation: 1.1 GB, the size/quality point Liquid AI documents first.
LFM3_QUANT = "Q4_K_M"
#: Model reference understood by ``llama-server -hf``.
LFM3_MODEL = f"{LFM3_REPO}:{LFM3_QUANT}"

#: Port of ``llama serve``/``llama-server``'s own default, so a server the user
#: started by following Liquid AI's instructions is found without configuration.
DEFAULT_PORT = 8080
DEFAULT_BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}/v1"

#: Context window the managed server allocates. The agent's system prompt and
#: tool catalogue are ~12k tokens; 32k leaves room for a working conversation
#: while keeping the KV cache small enough for an 8 GB laptop.
DEFAULT_CONTEXT = 32768

#: Liquid AI's sampling for "chat, tool use, agents, coding".
LFM3_SAMPLING = {"temperature": 0.1, "top_k": 50, "repeat_penalty": 1.1}

#: Oldest llama.cpp build that loads LFM3 GGUFs.
MIN_LLAMA_CPP_BUILD = 11960

#: Hosts a managed server may be started for; anything else is someone else's.
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

#: Servers this process started, stopped when ChiSurf exits.
_STARTED: dict[str, subprocess.Popen] = {}


class LocalModelError(RuntimeError):
    """The local model server cannot be found or started."""


def find_llama_server() -> str | None:
    """Return the path of a ``llama-server`` executable, or ``None``.

    The ChiSurf environment's own binary is preferred over one on ``PATH``:
    it is the build ChiSurf was tested against, and a stale system install
    may predate LFM3 support.

    Returns
    -------
    str or None
    """
    override = os.environ.get("CHISURF_LLAMA_SERVER", "").strip()
    if override:
        return override if pathlib.Path(override).is_file() else shutil.which(override)
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    prefix = pathlib.Path(sys.prefix)
    for candidate in (
        prefix / "bin" / exe,
        prefix / "Library" / "bin" / exe,
        prefix / "Scripts" / exe,
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("llama-server")


def is_local_url(base_url: str) -> bool:
    """Return whether *base_url* points at this machine.

    Parameters
    ----------
    base_url : str
        API root, e.g. ``http://127.0.0.1:8080/v1``.

    Returns
    -------
    bool
    """
    host = urllib.parse.urlsplit(str(base_url or "")).hostname or ""
    return host in _LOCAL_HOSTS


def server_command(
    model: str = LFM3_MODEL,
    port: int = DEFAULT_PORT,
    context: int = DEFAULT_CONTEXT,
    binary: str | None = None,
) -> list[str]:
    """Return the ``llama-server`` command line for *model*.

    Parameters
    ----------
    model : str
        A Hugging Face reference (``repo:quant``) or the path of a ``.gguf``.
    port : int
        Port to listen on; the server binds to loopback only.
    context : int
        Context window in tokens.
    binary : str, optional
        Executable; :func:`find_llama_server` when omitted.

    Returns
    -------
    list of str

    Raises
    ------
    LocalModelError
        When no ``llama-server`` is installed.
    """
    binary = binary or find_llama_server()
    if not binary:
        raise LocalModelError(
            "llama-server is not installed. It ships with the ChiSurf environment "
            "(conda-forge package 'llama.cpp'); install it with "
            "'conda install -c conda-forge llama.cpp', or start any OpenAI-compatible "
            "server yourself and point Settings → AI at it."
        )
    source = ["-m", model] if model.lower().endswith(".gguf") else ["-hf", model]
    return [
        binary,
        *source,
        # Parse the model's own tool-call syntax into structured tool_calls.
        "--jinja",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        str(context),
        # One conversation at a time: the whole window goes to it, and the
        # prompt cache of the long, fixed system prompt is never evicted by a
        # second slot.
        "-np",
        "1",
        # Every layer on the GPU — Metal on Apple Silicon, CUDA/Vulkan where the
        # build has them; a CPU-only build ignores it. The whole 1.7B model is
        # ~1 GB, so it fits any GPU that has one. Measured on an M1 Pro
        # (llama-bench, Q4_K_M): prompt 744-869 tok/s on the GPU vs 158-178 on
        # the CPU; generation 85 tok/s on the GPU with flash attention.
        "-ngl",
        "999",
        # Flash attention: +33 % generation on Metal, and an agent turn is
        # mostly generation (the model reasons ~1k tokens over a cached prompt).
        "-fa",
        "on",
        "--temp",
        str(LFM3_SAMPLING["temperature"]),
        "--top-k",
        str(LFM3_SAMPLING["top_k"]),
        "--repeat-penalty",
        str(LFM3_SAMPLING["repeat_penalty"]),
    ]


def server_health(base_url: str, timeout_s: float = 2.0) -> str:
    """Return ``"ready"``, ``"loading"`` or ``"down"`` for the server at *base_url*.

    Parameters
    ----------
    base_url : str
        API root ending in ``/v1``.
    timeout_s : float
        Per-probe timeout.

    Returns
    -------
    str
    """
    root = str(base_url).rstrip("/")
    root = root[: -len("/v1")] if root.endswith("/v1") else root
    for path in ("/health", "/v1/models"):
        try:
            with urllib.request.urlopen(root + path, timeout=timeout_s) as response:
                if response.status == 200:
                    return "ready"
        except urllib.error.HTTPError as error:
            # llama-server answers 503 while the model is still loading.
            if error.code == 503:
                return "loading"
            continue
        except Exception:
            return "down"
    return "down"


def _log_path() -> pathlib.Path:
    """Return the file the managed server's output goes to."""
    try:
        from chisurf.core.settings.path_utils import get_path

        directory = pathlib.Path(get_path("settings"))
    except Exception:
        directory = pathlib.Path.home() / ".chisurf"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "llama-server.log"


def ensure_server(
    base_url: str = DEFAULT_BASE_URL,
    model: str = LFM3_MODEL,
    context: int = DEFAULT_CONTEXT,
    timeout_s: float = 900.0,
    progress=None,
) -> bool:
    """Make sure a model server answers at *base_url*, starting one if needed.

    Nothing is started for a remote address or when a server already
    answers; a server this call starts is stopped when ChiSurf exits.

    Parameters
    ----------
    base_url : str
        API root the client will call.
    model : str
        Model reference passed to :func:`server_command`.
    context : int
        Context window for a server started here.
    timeout_s : float
        How long to wait for the model to load. The first start includes the
        ~1 GB download.
    progress : callable, optional
        Called with a short status string while waiting.

    Returns
    -------
    bool
        ``True`` once the server is ready; ``False`` for a remote address.

    Raises
    ------
    LocalModelError
        When the server cannot be started or does not become ready in time.
    """
    if not is_local_url(base_url):
        return False
    state = server_health(base_url)
    if state == "ready":
        return True

    process = _STARTED.get(base_url)
    if state == "down" and (process is None or process.poll() is not None):
        port = urllib.parse.urlsplit(base_url).port or DEFAULT_PORT
        command = server_command(model, port=port, context=context)
        log = _log_path()
        logger.info("starting local model server: %s (log: %s)", " ".join(command), log)
        handle = open(log, "ab")  # noqa: SIM115 - owned by the child process
        process = subprocess.Popen(
            command,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
        )
        _STARTED[base_url] = process

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise LocalModelError(
                f"llama-server exited with code {process.returncode}; see {_log_path()}"
            )
        state = server_health(base_url)
        if state == "ready":
            return True
        if progress is not None:
            progress(
                "loading the local model" if state == "loading" else "starting the local model"
            )
        time.sleep(1.0)
    raise LocalModelError(
        f"the local model at {base_url} was not ready after {timeout_s:.0f} s; see {_log_path()}"
    )


def stop_servers() -> None:
    """Stop every model server this process started."""
    for base_url, process in list(_STARTED.items()):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        _STARTED.pop(base_url, None)


atexit.register(stop_servers)
