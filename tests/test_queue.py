import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from reqqueue.manager import RequestQueue
from models.request import Request


def test_queue_fixture(queue: RequestQueue):
    """Fixture loads correctly."""
    assert queue is not None
    assert isinstance(queue, RequestQueue)


def test_enqueue_and_dequeue(queue: RequestQueue):
    """Test basic enqueue/dequeue workflow."""
    # Enqueue
    req = Request(command="echo hello")
    req_id = queue.enqueue(req)
    assert req_id is not None

    # Status should be pending
    retrieved = queue.get_request(req_id)
    assert retrieved is not None
    assert retrieved.status == "pending"

    # Dequeue
    dequeued = queue.dequeue()
    assert dequeued is not None
    assert dequeued.req_id == req_id
    assert dequeued.status == "running"


def test_complete_request(queue: RequestQueue):
    """Test marking request as complete."""
    req = Request(command="test")
    req_id = queue.enqueue(req)
    queue.dequeue()  # Move to running

    queue.complete(req_id, exit_code=0)
    retrieved = queue.get_request(req_id)
    assert retrieved.status == "done"
    assert retrieved.exit_code == 0


def test_fail_request(queue: RequestQueue):
    """Test marking request as failed."""
    req = Request(command="test")
    req_id = queue.enqueue(req)
    queue.dequeue()  # Move to running

    queue.fail(req_id, error_reason="Test error")
    retrieved = queue.get_request(req_id)
    assert retrieved.status == "failed"


def test_timeout_request(queue: RequestQueue):
    """Test marking request as timeout."""
    req = Request(command="test")
    req_id = queue.enqueue(req)
    queue.dequeue()  # Move to running

    queue.timeout(req_id)
    retrieved = queue.get_request(req_id)
    assert retrieved.status == "timeout"


def test_get_status(queue: RequestQueue):
    """Test getting queue status."""
    # Enqueue a few requests
    for i in range(3):
        req = Request(command=f"test{i}")
        queue.enqueue(req)

    status = queue.get_status()
    assert status.pending >= 3
    assert status.total >= 3


def test_list_requests(queue: RequestQueue):
    """Test listing requests with filters."""
    # Add requests
    req1 = Request(command="test1")
    req2 = Request(command="test2")
    id1 = queue.enqueue(req1)
    id2 = queue.enqueue(req2)
    queue.dequeue()  # Move id1 to running

    # List pending
    pending = queue.list_requests(status_filter="pending")
    assert any(r.req_id == id2 for r in pending)

    # List running
    running = queue.list_requests(status_filter="running")
    assert any(r.req_id == id1 for r in running)


def test_requeue_failed(queue: RequestQueue):
    """Test requeuing failed requests."""
    req = Request(command="test")
    req_id = queue.enqueue(req)
    queue.dequeue()  # Move to running
    queue.fail(req_id, error_reason="Retry test")

    requeued_count = queue.requeue_failed()
    assert requeued_count >= 1

    retrieved = queue.get_request(req_id)
    assert retrieved.status == "pending"


def test_requeue_stale(queue: RequestQueue):
    """Test requeuing stale requests."""
    req = Request(command="test")
    req_id = queue.enqueue(req)
    queue.dequeue()  # Move to running

    # With stale_after_minutes=0, should be marked as stale immediately
    stale_count = queue.requeue_stale(stale_after_minutes=0)
    assert stale_count >= 1

    retrieved = queue.get_request(req_id)
    assert retrieved.status == "pending"
