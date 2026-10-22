"""Thread-safe FIFO queue for multi-turn OpenCode chat sessions."""

from __future__ import annotations

import queue
import threading
from typing import Any


class _EndSentinel:
    """Singleton sentinel to signal the end of a chat session."""
    _instance: _EndSentinel | None = None

    def __new__(cls) -> _EndSentinel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

_END = _EndSentinel()


class FollowUpQueue:
    """Thread-safe FIFO queue for chat follow-up messages.

    Each chat session gets one queue. The worker thread blocks on ``get()``
    waiting for the next user message. The caller (e.g. OpenCodeAPI) calls
    ``put()`` to enqueue a follow-up and ``signal_end()`` to terminate the loop.
    """

    def __init__(self, session_id: str, *, timeout: float = 900.0) -> None:
        self.session_id = session_id
        self._timeout = timeout
        self._queue: queue.Queue[str | _EndSentinel] = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()
        self._pending_question: str | None = None
        self._pending_question_text = ""

    # -- public API ----------------------------------------------------------

    def put(self, message: str) -> None:
        """Enqueue a follow-up message.

        Raises RuntimeError if the queue has been closed via ``signal_end()``.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError(
                    f"Chat session {self.session_id} is already closed."
                )
            self._queue.put(message)

    def get(self) -> str:
        """Block until a message arrives or the timeout expires.

        Returns:
            The next queued message string.

        Raises:
            queue.Empty: if no message arrives within the configured timeout.
        """
        item = self._queue.get(timeout=self._timeout)
        if isinstance(item, _EndSentinel):
            # Put the sentinel back so subsequent get() calls also see end.
            self._queue.put(item)
            raise queue.Empty("Chat session ended.")
        return item

    def signal_end(self) -> None:
        """Signal the worker thread to exit the chat loop."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(_END)

    # -- question latch (question relay) ------------------------------------

    def latch_question(self, request_id: str, question: str = "") -> None:
        """Record a pending OpenCode question that the next user utterance answers.

        While a question is latched, the next follow-up message is treated as
        the user's spoken answer and routed via ``reply_question`` instead of
        being sent as a normal chat prompt.
        """
        request_id = (request_id or "").strip()
        if not request_id:
            return
        with self._lock:
            self._pending_question = request_id
            self._pending_question_text = (question or "").strip()

    def take_question(self) -> tuple[str, str]:
        """Atomically pop and return the pending question ``(request_id, text)``.

        Returns ``("", "")`` when no question is latched.
        """
        with self._lock:
            req_id = self._pending_question
            text = self._pending_question_text
            self._pending_question = None
            self._pending_question_text = ""
        return (req_id or "", text)

    def has_question(self) -> bool:
        """Return True when a question is waiting for the user's answer."""
        with self._lock:
            return bool(self._pending_question)

    @staticmethod
    def is_end(value: Any) -> bool:
        """Check whether *value* is the end-of-chat sentinel."""
        return isinstance(value, _EndSentinel)

    # -- convenience ---------------------------------------------------------

    def qsize(self) -> int:
        """Approximate number of pending messages."""
        return self._queue.qsize()

    def __repr__(self) -> str:
        return (
            f"<FollowUpQueue session_id={self.session_id!r} "
            f"qsize={self._queue.qsize()} closed={self._closed}>"
        )
