from __future__ import annotations
"""
Session-based conversation memory for the Army Archive chatbot.

Stores recent turns per session_id so the LLM can reference prior Q&A when
answering follow-up questions (e.g. "elaborate on point 3" or "what about
its advantages?").

Design constraints for offline CPU deployment:
  - Pure in-process Python dict — no Redis, no DB
  - Sessions auto-expire after IDLE_TIMEOUT_S of inactivity
  - History is SUMMARISED (not raw text) when injected into prompts to
    save context window space
  - Module-level singleton so all requests share the same memory store
"""
import time
from dataclasses import dataclass, field
from typing import List


IDLE_TIMEOUT_S      = 3_600    # sessions expire after 1 hour of inactivity
MAX_TURNS           = 8        # keep last 8 turns (4 Q&A pairs) per session
MAX_ANSWER_HISTORY  = 400      # truncate long answers stored in history


@dataclass
class Turn:
    role:      str    # "user" | "assistant"
    content:   str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id:  str
    turns:       List[Turn] = field(default_factory=list)
    last_active: float      = field(default_factory=time.time)


class ConversationMemory:
    """Thread-safe (GIL-protected) in-process conversation store."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_turn(self, session_id: str, query: str, answer: str) -> None:
        """Record a completed Q&A turn for the given session."""
        sess = self._get_or_create(session_id)
        sess.turns.append(Turn("user",      query))
        sess.turns.append(Turn("assistant", answer[:MAX_ANSWER_HISTORY]))
        # Keep within window
        if len(sess.turns) > MAX_TURNS * 2:
            sess.turns = sess.turns[-(MAX_TURNS * 2):]
        sess.last_active = time.time()
        self._evict_stale()

    def get_history(self, session_id: str) -> List[dict]:
        """Return raw history as list of {role, content} dicts."""
        sess = self._sessions.get(session_id)
        if not sess:
            return []
        sess.last_active = time.time()
        return [{"role": t.role, "content": t.content} for t in sess.turns]

    def get_context_block(self, session_id: str) -> str:
        """
        Return a compact conversation history block to inject into the LLM
        user prompt.  Shows the last 3 Q&A pairs (6 turns).

        Returns "" if no history exists for this session.
        """
        history = self.get_history(session_id)
        if not history:
            return ""

        recent = history[-6:]   # last 3 Q&A pairs
        lines  = ["CONVERSATION HISTORY (for context only — answer from CONTEXT DOCUMENTS):"]
        for t in recent:
            label = "User" if t["role"] == "user" else "Assistant"
            text  = t["content"][:200].replace("\n", " ")
            lines.append(f"  {label}: {text}")
        lines.append("")
        return "\n".join(lines)

    def clear(self, session_id: str) -> None:
        """Delete all history for a session (e.g. user presses 'New Chat')."""
        self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        return len(self._sessions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def _evict_stale(self) -> None:
        now   = time.time()
        stale = [k for k, v in self._sessions.items()
                 if now - v.last_active > IDLE_TIMEOUT_S]
        for k in stale:
            del self._sessions[k]


# ---------------------------------------------------------------------------
# Module-level singleton — imported wherever needed
# ---------------------------------------------------------------------------
memory = ConversationMemory()
