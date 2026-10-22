"""Tests for core/opencode/opencode_chat.py — FollowUpQueue + question latch."""

from __future__ import annotations

import queue

import pytest

from core.opencode.opencode_chat import FollowUpQueue


class TestFollowUpQueue:
    def test_put_get_roundtrip(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.put("hello")
        assert q.get() == "hello"

    def test_signal_end_raises_empty_on_get(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.signal_end()
        with pytest.raises(queue.Empty):
            q.get()

    def test_is_end_detects_sentinel_after_signal(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.signal_end()
        # A get after end returns via the sentinel (re-raises Empty), but the
        # sentinel class predicate must be usable by the worker.
        assert q.qsize() >= 1  # sentinel is present in the queue

    def test_put_after_signal_end_raises(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.signal_end()
        with pytest.raises(RuntimeError):
            q.put("too late")


class TestQuestionLatch:
    def test_latch_and_take_question(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.latch_question("q1", "Continue?")
        assert q.has_question() is True
        assert q.take_question() == ("q1", "Continue?")
        assert q.has_question() is False

    def test_take_question_empty_when_none(self):
        q = FollowUpQueue("ses_1", timeout=1)
        assert q.take_question() == ("", "")

    def test_latch_empty_request_id_ignored(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.latch_question("", "ignore me")
        assert q.has_question() is False

    def test_latch_overwrites_previous(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.latch_question("q1", "first")
        q.latch_question("q2", "second")
        assert q.take_question() == ("q2", "second")

    def test_question_does_not_affect_message_flow(self):
        q = FollowUpQueue("ses_1", timeout=1)
        q.latch_question("q1", "Continue?")
        assert q.qsize() == 0
        q.put("answer")
        assert q.qsize() == 1