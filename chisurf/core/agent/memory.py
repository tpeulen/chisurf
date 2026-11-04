"""The agent's long-term memory: the user's shared Mnemosyne store.

The user runs several agents (this one, coding assistants, a chat agent) and
they share **one** memory: Mnemosyne, a local SQLite store. ChiSurf's agent
reads and writes that same database -- the one Mnemosyne's own MCP server
uses (``$MNEMOSYNE_DATA_DIR``, else ``~/.hermes/mnemosyne/data``) -- so a
lesson learned in ChiSurf ("this user fits DNA decays with two components")
is known to every other agent, and the other way round. It never creates a
database of its own.

Everything here is optional. Without the ``mnemosyne`` package, or when the
store cannot be opened or searched, :class:`AgentMemory` reports itself
unavailable and the agent runs exactly as it does without memory: recall
returns nothing and the memory tools say why.

How this differs from the user's skills (:mod:`chisurf.core.agent.user_okf`):
a *skill* is a procedure (``SKILL.md``), loaded whole when a request matches
its trigger words; a *memory* is one short fact with the reason it matters,
recalled by similarity before every request.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "AgentMemory",
    "MEMORY_RECALL",
    "MEMORY_REMEMBER",
    "Recollection",
    "build_tools",
    "default_memory",
    "looks_secret",
]

MEMORY_RECALL = "memory_recall"
MEMORY_REMEMBER = "memory_remember"

#: Who wrote a memory, as Mnemosyne records it; recall is not filtered by it.
AUTHOR_ID = "chisurf-agent"
SESSION_ID = "chisurf_agent"

#: A memory longer than this is a note, not a fact.
MAX_MEMORY_CHARS = 600

_SECRET = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|bearer\s+[a-z0-9]|sk-[a-z0-9]{8,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY)",
    re.IGNORECASE,
)
_TRACEBACK = re.compile(r"Traceback \(most recent call last\)|^\s+File \".*\", line \d+", re.M)


def looks_secret(text: str) -> bool:
    """Whether *text* looks like it carries a credential (never stored)."""
    return bool(_SECRET.search(str(text or "")))


@dataclass
class Recollection:
    """One recalled memory."""

    content: str
    id: str = ""
    score: float = 0.0
    source: str = ""


class AgentMemory:
    """The agent's handle on the shared Mnemosyne store.

    Parameters
    ----------
    store : object, optional
        A ``mnemosyne.core.memory.Mnemosyne`` (or anything with its
        ``recall(query, top_k)`` and ``remember(content, ...)``). Omitted, the
        user's default store is opened on first use -- the same database the
        Mnemosyne MCP server serves.
    enabled : bool
        ``False`` makes every call a no-op, as if the package were absent.

    Notes
    -----
    Calls are serialised by a lock: the agent runs on a worker thread and a
    store holds one SQLite connection.
    """

    def __init__(self, store: Any = None, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self._store = store
        self._failed: str | None = None
        self._lock = threading.Lock()

    # -- the store ------------------------------------------------------- #
    def _open(self) -> Any:
        """The store, opened on first use; ``None`` when there is none."""
        if not self.enabled or self._failed:
            return None
        if self._store is None:
            try:
                from mnemosyne.core.memory import Mnemosyne

                # No db_path and no bank: the default database the MCP server uses.
                self._store = Mnemosyne(
                    session_id=SESSION_ID, author_id=AUTHOR_ID, author_type="agent"
                )
            except Exception as error:  # noqa: BLE001 - no memory is a supported state
                self._failed = f"{type(error).__name__}: {error}"
                logger.info("agent memory unavailable: %s", self._failed)
                return None
        return self._store

    @property
    def available(self) -> bool:
        """Whether memories can be recalled and stored."""
        return self._open() is not None

    @property
    def why_unavailable(self) -> str:
        """The reason :attr:`available` is ``False`` ("" when it is not)."""
        if not self.enabled:
            return "memory is turned off"
        return self._failed or ""

    # -- reading ----------------------------------------------------------- #
    def recall(self, query: str, limit: int = 4) -> list[Recollection]:
        """The memories most relevant to *query*; empty when none or on any failure."""
        query = str(query or "").strip()
        store = self._open()
        if store is None or not query:
            return []
        try:
            with self._lock:
                rows = store.recall(query, top_k=max(1, int(limit)))
        except Exception:  # noqa: BLE001 - a failed recall must not fail the request
            logger.debug("memory recall failed", exc_info=True)
            return []
        found: list[Recollection] = []
        for row in rows or []:
            if not isinstance(row, dict) or row.get("superseded_by"):
                continue
            content = " ".join(str(row.get("content", "")).split())
            if content:
                found.append(
                    Recollection(
                        content=content,
                        id=str(row.get("id", "")),
                        score=float(row.get("score") or 0.0),
                        source=str(row.get("source", "")),
                    )
                )
        return found[: max(1, int(limit))]

    def as_context(self, query: str, limit: int = 4, max_chars: int = 240) -> str:
        """The recalled memories as a short block for the system prompt ("" when none)."""
        memories = self.recall(query, limit)
        if not memories:
            return ""
        lines = [
            "## What you remember (shared memory)",
            "Facts and lessons from earlier work with this user, recalled for this "
            "request. Use them when they apply; the user's words in this request win.",
        ]
        for memory in memories:
            text = memory.content
            if len(text) > max_chars:
                text = text[: max_chars - 1].rstrip() + "…"
            lines.append(f"- {text}")
        return "\n".join(lines)

    # -- writing ----------------------------------------------------------- #
    def remember(
        self,
        fact: str,
        why: str = "",
        kind: str = "fact",
        importance: float = 0.6,
    ) -> str:
        """Store one fact with why it matters; returns its id.

        Raises
        ------
        ValueError
            When the fact is empty, too long, looks like a secret or a stack
            trace, or the store is unavailable -- the message says which, so
            the model can correct itself.
        """
        fact = " ".join(str(fact or "").split())
        why = " ".join(str(why or "").split())
        if not fact:
            raise ValueError("a memory needs the fact itself")
        content = f"ChiSurf: {fact}" + (f" (why: {why})" if why else "")
        if len(content) > MAX_MEMORY_CHARS:
            raise ValueError(
                f"{len(content)} characters is a note, not a fact: keep a memory under "
                f"{MAX_MEMORY_CHARS} characters, one fact per memory"
            )
        if looks_secret(content):
            raise ValueError("this looks like it contains a credential; secrets are never stored")
        if _TRACEBACK.search(str(fact)):
            raise ValueError("store the lesson, not the stack trace")
        store = self._open()
        if store is None:
            raise ValueError(f"memory is not available ({self.why_unavailable or 'unknown'})")
        source = kind if kind in ("preference", "fact", "insight", "lesson") else "fact"
        with self._lock:
            return str(
                store.remember(
                    content,
                    source=source,
                    importance=max(0.0, min(1.0, float(importance))),
                    scope="global",
                    veracity="inferred",
                    metadata={"app": "chisurf", "author": AUTHOR_ID},
                )
            )


_DEFAULT: AgentMemory | None = None
_DEFAULT_LOCK = threading.Lock()


def default_memory() -> AgentMemory:
    """The process's handle on the user's shared store (one per process, opened lazily)."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = AgentMemory()
        return _DEFAULT


def build_tools(registry: Any) -> None:
    """Register ``memory_recall`` and ``memory_remember`` on *registry*.

    The handlers read the session's :class:`AgentMemory` from
    ``context.extras["memory"]``; a session without one answers that memory
    is off.
    """
    from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError

    def _memory(context: Any) -> AgentMemory:
        memory = context.extras.get("memory")
        if memory is None or not memory.available:
            reason = memory.why_unavailable if memory is not None else "memory is turned off"
            raise ToolError(f"memory is not available in this session ({reason or 'unknown'})")
        return memory

    @registry.add(
        name=MEMORY_RECALL,
        description=(
            "Search the user's long-term memory (shared with their other agents) for "
            "facts and lessons from earlier work: preferences, settings a dataset "
            "needed, a fix that worked. The most relevant memories for the request "
            "are already in your context; call this to look up something specific."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, in words."},
                "limit": {"type": "integer", "description": "At most this many (default 5)."},
            },
            "required": ["query"],
        },
        safety=SAFETY_READ,
    )
    def memory_recall(context: Any, query: str = "", limit: int = 5) -> dict[str, Any]:
        """Return the memories most relevant to *query*."""
        found = _memory(context).recall(query, max(1, min(int(limit or 5), 10)))
        return {"ok": True, "memories": [m.content for m in found], "count": len(found)}

    @registry.add(
        name=MEMORY_REMEMBER,
        description=(
            "Keep ONE durable lesson in the user's long-term memory, with why it "
            "matters: a user preference, a fix that worked, a setting a dataset "
            "needed. It is recalled in later sessions and by the user's other "
            "agents. Never store session noise, stack traces, file contents or "
            "secrets. A whole procedure belongs in save_skill instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact, one sentence, e.g. 'DNA decays from the "
                    "MT200 need two lifetime components'.",
                },
                "why": {
                    "type": "string",
                    "description": "Why it matters, e.g. 'one component left structured residuals'.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["preference", "fact", "lesson"],
                    "description": "preference (the user's choice), fact, or lesson (a fix).",
                },
            },
            "required": ["fact", "why"],
        },
        safety=SAFETY_WRITE,
    )
    def memory_remember(
        context: Any, fact: str = "", why: str = "", kind: str = "fact"
    ) -> dict[str, Any]:
        """Store one fact and why it matters."""
        memory = _memory(context)
        try:
            memory_id = memory.remember(fact, why, kind=kind)
        except ValueError as error:
            raise ToolError(str(error)) from error
        return {"ok": True, "remembered": fact, "id": memory_id}
