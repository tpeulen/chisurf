"""Execution context shared by every ChiSurf agent tool.

The context is the single place that knows *where* the agent is allowed to
work (working directory, file-access roots), *how* it reports progress
(event callback), and *how* it resolves the loose references a language model
produces -- "the second fit", ``"215-268 D0"``, ``0`` -- into real ChiSurf
objects.

Keeping that resolution here (rather than in each tool) is what makes the
tools forgiving: the model may name a fit by index, name, or unique id and
still hit the right object.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from chisurf.core.agent.spec import ToolError

logger = logging.getLogger(__name__)

#: Callback signature for runtime progress events: ``(event_name, payload)``.
EventCallback = Callable[[str, dict[str, Any]], None]
#: Callback asking the user to approve a dangerous tool call.
ConfirmCallback = Callable[[str, dict[str, Any]], bool]


@dataclass
class AgentContext:
    """State and policy shared by the agent runtime and its tools.

    Parameters
    ----------
    working_directory : str
        Directory that relative paths are resolved against.
    allow_code_execution : bool
        Whether the ``run_python`` tool may run.
    code_timeout_s : float
        Wall-clock limit for a single ``run_python`` call.
    max_result_chars : int
        Tool results longer than this are truncated before being sent to the
        model, so one verbose result cannot blow the context window.
    confirm : callable, optional
        ``confirm(tool_name, arguments) -> bool``.  Consulted before every
        ``dangerous`` tool call.  ``None`` means "no confirmation required".
    event_callback : callable, optional
        Receives runtime events such as ``tool.started``/``tool.completed``.
    """

    working_directory: str = "."
    allow_code_execution: bool = True
    code_timeout_s: float = 60.0
    max_result_chars: int = 8000
    confirm: ConfirmCallback | None = None
    event_callback: EventCallback | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    # ── infrastructure ────────────────────────────────────────────────

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        """Send a runtime event to the registered callback, if any."""
        if self.event_callback is None:
            return
        try:
            self.event_callback(event, payload)
        except Exception:
            logger.exception("agent event callback failed for %s", event)

    def resolve_path(self, path: str) -> pathlib.Path:
        """Return *path* as an absolute path under the working directory.

        Models regularly repeat the working directory inside a relative path
        (``test/data`` + ``test/data/tcspc``).  When the naive join does not
        exist, an overlapping prefix is removed and the de-duplicated path is
        used instead -- but only if *that* one exists, so no path is ever
        silently rewritten into a different, existing location.

        Parameters
        ----------
        path : str
            Absolute or relative filesystem path; ``~`` is expanded.

        Returns
        -------
        pathlib.Path
        """
        candidate = pathlib.Path(str(path)).expanduser()
        if candidate.is_absolute():
            return candidate
        root = pathlib.Path(self.working_directory).expanduser()
        joined = root / candidate
        if joined.exists():
            return joined
        deduplicated = self._strip_repeated_prefix(root, candidate)
        if deduplicated is not None and deduplicated.exists():
            logger.debug("agent path %s de-duplicated to %s", path, deduplicated)
            return deduplicated
        return joined

    @staticmethod
    def _strip_repeated_prefix(
        root: pathlib.Path,
        relative: pathlib.Path,
    ) -> pathlib.Path | None:
        """Return *relative* joined to *root* with a repeated prefix removed.

        Parameters
        ----------
        root : pathlib.Path
            The working directory.
        relative : pathlib.Path
            A relative path that may repeat the tail of *root*.

        Returns
        -------
        pathlib.Path or None
            The de-duplicated path, or ``None`` when nothing overlaps.
        """
        root_parts = root.parts
        relative_parts = relative.parts
        for overlap in range(min(len(root_parts), len(relative_parts)), 0, -1):
            if root_parts[-overlap:] == relative_parts[:overlap]:
                return root.joinpath(*relative_parts[overlap:])
        return None

    def describe_working_directory(self) -> str:
        """Return a one-line listing of the working directory's entries.

        Appended to "no such path" errors so the model can correct itself
        instead of guessing again.
        """
        root = pathlib.Path(self.working_directory).expanduser()
        if not root.is_dir():
            return f"working directory {root} does not exist"
        entries = sorted(
            entry.name + ("/" if entry.is_dir() else "")
            for entry in root.iterdir()
            if not entry.name.startswith(".")
        )
        listing = ", ".join(entries[:30]) or "(empty)"
        return f"working directory is {root}; it contains: {listing}"

    def ensure_experiments(self) -> dict[str, dict[str, list[str]]]:
        """Make sure readers and model classes are registered.

        Returns
        -------
        dict
            The registry description, see
            :func:`chisurf.core.experiments.bootstrap.describe_registry`.
        """
        from chisurf.core.experiments.bootstrap import ensure_experiments_registered

        return ensure_experiments_registered()

    # ── session accessors ─────────────────────────────────────────────

    @property
    def datasets(self) -> list[Any]:
        """The datasets currently loaded in the ChiSurf session."""
        import chisurf as cs

        return list(getattr(cs, "imported_datasets", []) or [])

    @property
    def fits(self) -> list[Any]:
        """The fits currently present in the ChiSurf session."""
        import chisurf as cs

        return list(getattr(cs, "fits", []) or [])

    # ── reference resolution ──────────────────────────────────────────

    @staticmethod
    def _matches(obj: Any, reference: str) -> bool:
        """Return whether *obj* matches a name/uid/filename *reference*."""
        wanted = reference.strip().lower()
        for attribute in ("name", "unique_identifier", "filename"):
            value = str(getattr(obj, attribute, "") or "").strip().lower()
            if not value:
                continue
            if value == wanted or pathlib.Path(value).name == wanted:
                return True
        return False

    def _resolve(
        self,
        items: list[Any],
        reference: Any,
        kind: str,
    ) -> tuple[Any, int]:
        """Resolve *reference* against *items*, returning ``(object, index)``.

        Parameters
        ----------
        items : list
            Candidate objects (datasets or fits).
        reference : int, str or None
            Index, name, unique id, or ``None`` for "the only/current one".
        kind : str
            ``"dataset"`` or ``"fit"``; used in error messages.

        Raises
        ------
        ToolError
            When the reference is ambiguous or matches nothing.
        """
        if not items:
            raise ToolError(
                f"there are no {kind}s in the session yet — "
                f"{'load data first with load_data' if kind == 'dataset' else 'create one first with create_fit'}"
            )
        if reference is None or reference == "":
            if len(items) == 1:
                return items[0], 0
            current = self._current_index(kind)
            if current is not None and 0 <= current < len(items):
                return items[current], current
            raise ToolError(
                f"there are {len(items)} {kind}s — say which one "
                f"(index 0..{len(items) - 1} or its name)"
            )
        if isinstance(reference, bool):
            raise ToolError(f"invalid {kind} reference: {reference!r}")
        if isinstance(reference, (int, float)) or (
            isinstance(reference, str) and reference.strip().lstrip("-").isdigit()
        ):
            index = int(reference)
            if index < 0:
                index += len(items)
            if not 0 <= index < len(items):
                raise ToolError(
                    f"{kind} index {reference} is out of range (session has {len(items)} {kind}s)"
                )
            return items[index], index
        text = str(reference)
        exact = [(item, i) for i, item in enumerate(items) if self._matches(item, text)]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise ToolError(
                f"{kind} reference {text!r} is ambiguous — it matches indices "
                f"{[i for _, i in exact]}; use the index instead"
            )
        partial = [
            (item, i)
            for i, item in enumerate(items)
            if text.lower() in str(getattr(item, "name", "")).lower()
        ]
        if len(partial) == 1:
            return partial[0]
        available = [f"{i}: {getattr(item, 'name', '?')}" for i, item in enumerate(items)]
        raise ToolError(f"no {kind} matches {text!r}. Available {kind}s: {available}")

    @staticmethod
    def _current_index(kind: str) -> int | None:
        """Return the index of the fit currently selected in the GUI, if any."""
        if kind != "fit":
            return None
        import chisurf as cs

        gui = getattr(cs, "cs", None)
        if gui is None:
            return None
        try:
            index = int(getattr(gui, "fit_idx", -1))
        except Exception:
            return None
        return index if index >= 0 else None

    def resolve_dataset(self, reference: Any = None) -> tuple[Any, int]:
        """Resolve a dataset reference to ``(dataset, index)``."""
        return self._resolve(self.datasets, reference, "dataset")

    def resolve_fit(self, reference: Any = None) -> tuple[Any, int]:
        """Resolve a fit reference to ``(fit, index)``."""
        return self._resolve(self.fits, reference, "fit")

    def resolve_datasets(self, references: Any = None) -> list[int]:
        """Resolve one reference, a list of them, or ``None`` (= all datasets).

        Parameters
        ----------
        references : int, str, list or None
            Dataset references.  ``None`` selects every loaded dataset.

        Returns
        -------
        list of int
            Dataset indices, in the order given.
        """
        if references is None:
            return list(range(len(self.datasets)))
        if not isinstance(references, (list, tuple)):
            references = [references]
        return [self.resolve_dataset(reference)[1] for reference in references]
