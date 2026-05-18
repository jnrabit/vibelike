"""Tests for RequestQueue."""

# import pytest
import sqlite3
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from reqqueue.manager import RequestQueue, QueueStatus
from models.request import Request


# fixture
def test_db(tmp_path):
    """Provide a temporary database for testing."""
    db_path = tmp_path / "test_queue.db"
    return str(db_path)


# fixture
def queue(test_db):
    """Create a test queue."""
    return RequestQueue(db_path=test_db)


def test_queue_initialization(queue):
    """Test queue initializes properly."""
    assert queue.db_path.exists()


def test_enqueue_dequeue(queue):
    """Test enqueue and dequeue operations."""
    request = Request(
        req_id="test-1",
        tool_name="echo-tool",
        args=["hello"],
        priority=1
    )

    enqueued_id = queue.enqueue(request)
    assert enqueued_id == "test-1"

    # Check status
    status = queue.get_status()
    assert status.pending >= 1

    # Dequeue
    dequeued = queue.dequeue()
    assert dequeued is not None
    assert dequeued.req_id == "test-1"
    assert dequeued.tool_name == "echo-tool"


def test_queue_priority(queue):
    """Test that higher priority requests are dequeued first."""
    req_low = Request(req_id="low-priority", tool_name="tool", priority=10)
    req_high = Request(req_id="high-priority", tool_name="tool", priority=1)

    queue.enqueue(req_low)
    queue.enqueue(req_high)

    # High priority should be dequeued first
    first = queue.dequeue()
    assert first.req_id == "high-priority"


def test_complete_request(queue):
    """Test completing a request."""
    request = Request(req_id="test-complete", tool_name="tool")
    queue.enqueue(request)
    dequeued = queue.dequeue()

    queue.complete(dequeued.req_id, exit_code=0)

    # Check status
    status = queue.get_status()
    assert status.completed >= 1


def test_fail_request(queue):
    """Test failing a request."""
    request = Request(req_id="test-fail", tool_name="tool")
    queue.enqueue(request)
    dequeued = queue.dequeue()

    queue.fail(dequeued.req_id, error="Test error", retries=0)

    status = queue.get_status()
    assert status.failed >= 1


def test_retry_logic(queue):
    """Test retry logic for failed requests."""
    request = Request(req_id="test-retry", tool_name="tool")
    queue.enqueue(request)

    dequeued = queue.dequeue()
    queue.fail(dequeued.req_id, error="Error", retries=2)

    # After delay, should be available again
    requeued = queue.dequeue()
    assert requeued is not None
    assert requeued.req_id == "test-retry"


def test_queue_status(queue):
    """Test queue status reporting."""
    req1 = Request(req_id="req1", tool_name="tool", priority=1)
    req2 = Request(req_id="req2", tool_name="tool", priority=2)

    queue.enqueue(req1)
    queue.enqueue(req2)

    status = queue.get_status()
    assert isinstance(status, QueueStatus)
    assert status.pending >= 2
    assert status.running == 1  # After first dequeue
    assert status.completed == 0

    dequeued = queue.dequeue()
    queue.complete(dequeued.req_id, exit_code=0)

    status = queue.get_status()
    assert status.completed >= 1
