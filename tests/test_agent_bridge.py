import queue
import threading
import pytest

# These imports will fail until Task 3 implements them.
from webapp.agent_bridge import (
    enqueue_send,
    dequeue_send,
    enqueue_reply,
    dequeue_reply,
    clear_reply_queue,
)


def test_enqueue_and_dequeue_send():
    """A message placed in the send queue is immediately retrievable."""
    clear_reply_queue()
    enqueue_send("hello teammate")
    msg = dequeue_send(timeout=0.1)
    assert msg == "hello teammate"


def test_dequeue_send_returns_none_when_empty():
    """Draining an empty send queue returns None without blocking."""
    # Drain any leftover
    while dequeue_send(timeout=0) is not None:
        pass
    result = dequeue_send(timeout=0)
    assert result is None


def test_enqueue_reply_and_dequeue():
    """A reply placed in the reply queue is retrievable once."""
    clear_reply_queue()
    enqueue_reply("agent says hi")
    reply = dequeue_reply()
    assert reply == "agent says hi"


def test_dequeue_reply_returns_none_when_empty():
    clear_reply_queue()
    assert dequeue_reply() is None


def test_enqueue_send_clears_old_reply():
    """enqueue_send clears the reply queue so old replies don't leak."""
    enqueue_reply("stale reply")
    enqueue_send("new message")  # should clear the stale reply
    assert dequeue_reply() is None


def test_reply_queue_overwrites_when_full():
    """Filling the reply queue beyond maxsize discards the oldest, not the newest."""
    clear_reply_queue()
    for i in range(12):  # maxsize is 10
        enqueue_reply(f"msg-{i}")
    # Should have 10 messages, newest ones
    replies = []
    while True:
        r = dequeue_reply()
        if r is None:
            break
        replies.append(r)
    assert len(replies) == 10
    assert "msg-11" in replies  # newest retained
    assert "msg-0" not in replies  # oldest evicted
    assert "msg-1" not in replies  # second-oldest evicted
