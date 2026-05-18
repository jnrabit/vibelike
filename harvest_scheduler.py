#!/usr/bin/env python3
"""
HarvestScheduler - Submit harvest jobs to the request queue.
Provides a simple API for enqueueing harvesting tasks.
"""

import os
import sys
import logging
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from reqqueue.manager import RequestQueue
from models import Request

logger = logging.getLogger(__name__)


class HarvestScheduler:
    """Submit and manage harvest jobs."""

    def __init__(self, queue_db: str = "logs/queue.db"):
        """
        Initialize the scheduler.

        Args:
            queue_db: Path to request queue database
        """
        self.queue = RequestQueue(db_path=queue_db)

    def schedule_wikipedia_harvest(
        self,
        source: str = "wikipedia",
        limit: int = 100,
        user: str = "scheduler",
        priority: int = 0
    ) -> str:
        """
        Schedule a Wikipedia harvest job.

        Args:
            source: Data source name
            limit: Maximum documents to harvest
            user: User submitting the request
            priority: Job priority (higher = sooner)

        Returns:
            Request ID
        """
        request = Request(
            tool_name="harvest",
            operation="harvest_wikipedia",
            env={"source": source, "limit": str(limit)},
            user=user,
            priority=priority,
            comment=f"Wikipedia harvest: {source} (limit={limit})"
        )
        return self.queue.enqueue(request, user=user)

    def schedule_rfc_harvest(
        self,
        limit: int = 50,
        user: str = "scheduler",
        priority: int = 0
    ) -> str:
        """Schedule an RFC harvest job."""
        request = Request(
            tool_name="harvest",
            operation="harvest_rfcs",
            env={"limit": str(limit)},
            user=user,
            priority=priority,
            comment=f"RFC harvest (limit={limit})"
        )
        return self.queue.enqueue(request, user=user)

    def schedule_pep_harvest(
        self,
        limit: int = 50,
        user: str = "scheduler",
        priority: int = 0
    ) -> str:
        """Schedule a PEP harvest job."""
        request = Request(
            tool_name="harvest",
            operation="harvest_peps",
            env={"limit": str(limit)},
            user=user,
            priority=priority,
            comment=f"PEP harvest (limit={limit})"
        )
        return self.queue.enqueue(request, user=user)

    def schedule_tools_harvest(
        self,
        limit: int = 50,
        user: str = "scheduler",
        priority: int = 0
    ) -> str:
        """Schedule a tools harvest job."""
        request = Request(
            tool_name="harvest",
            operation="harvest_tools",
            env={"limit": str(limit)},
            user=user,
            priority=priority,
            comment=f"Tools harvest (limit={limit})"
        )
        return self.queue.enqueue(request, user=user)

    def schedule_batch(
        self,
        operations: list[dict],
        user: str = "scheduler"
    ) -> list[str]:
        """
        Schedule multiple harvest jobs.

        Args:
            operations: List of operation dicts with keys:
                - operation: "harvest_wikipedia", "harvest_rfcs", etc.
                - limit: Maximum documents (optional)
                - priority: Job priority (optional)
            user: User submitting requests

        Returns:
            List of request IDs
        """
        request_ids = []
        for op in operations:
            operation = op.get("operation")
            if operation == "harvest_wikipedia":
                req_id = self.schedule_wikipedia_harvest(
                    limit=op.get("limit", 100),
                    user=user,
                    priority=op.get("priority", 0)
                )
            elif operation == "harvest_rfcs":
                req_id = self.schedule_rfc_harvest(
                    limit=op.get("limit", 50),
                    user=user,
                    priority=op.get("priority", 0)
                )
            elif operation == "harvest_peps":
                req_id = self.schedule_pep_harvest(
                    limit=op.get("limit", 50),
                    user=user,
                    priority=op.get("priority", 0)
                )
            elif operation == "harvest_tools":
                req_id = self.schedule_tools_harvest(
                    limit=op.get("limit", 50),
                    user=user,
                    priority=op.get("priority", 0)
                )
            else:
                logger.warning(f"Unknown operation: {operation}")
                continue

            request_ids.append(req_id)

        return request_ids

    def get_status(self) -> dict:
        """Get queue status."""
        status = self.queue.get_status()
        return {
            "pending": status.pending,
            "running": status.running,
            "completed": status.completed,
            "failed": status.failed,
            "timeout": status.timeout,
            "next_request": status.next_request
        }


def main():
    """CLI for scheduling harvest jobs."""
    import argparse

    parser = argparse.ArgumentParser(description="Schedule harvest jobs")
    parser.add_argument(
        "operation",
        choices=["wikipedia", "rfcs", "peps", "tools", "batch"],
        help="Harvest operation to schedule"
    )
    parser.add_argument("--limit", type=int, default=50, help="Document limit")
    parser.add_argument("--user", default="cli", help="User name")
    parser.add_argument("--priority", type=int, default=0, help="Job priority")
    parser.add_argument("--queue-db", default="logs/queue.db", help="Queue database path")

    args = parser.parse_args()

    scheduler = HarvestScheduler(queue_db=args.queue_db)

    # Schedule job
    if args.operation == "wikipedia":
        req_id = scheduler.schedule_wikipedia_harvest(
            limit=args.limit,
            user=args.user,
            priority=args.priority
        )
    elif args.operation == "rfcs":
        req_id = scheduler.schedule_rfc_harvest(
            limit=args.limit,
            user=args.user,
            priority=args.priority
        )
    elif args.operation == "peps":
        req_id = scheduler.schedule_pep_harvest(
            limit=args.limit,
            user=args.user,
            priority=args.priority
        )
    elif args.operation == "tools":
        req_id = scheduler.schedule_tools_harvest(
            limit=args.limit,
            user=args.user,
            priority=args.priority
        )
    elif args.operation == "batch":
        # Schedule all operations
        req_ids = scheduler.schedule_batch(
            [
                {"operation": "harvest_wikipedia", "limit": args.limit},
                {"operation": "harvest_rfcs", "limit": args.limit},
                {"operation": "harvest_peps", "limit": args.limit},
                {"operation": "harvest_tools", "limit": args.limit},
            ],
            user=args.user
        )
        print(f"Scheduled {len(req_ids)} jobs:")
        for rid in req_ids:
            print(f"  - {rid}")
        print()
        print("Queue status:")
        status = scheduler.get_status()
        print(f"  Pending: {status['pending']}")
        print(f"  Running: {status['running']}")
        print(f"  Completed: {status['completed']}")
        return

    print(f"✓ Scheduled {args.operation} harvest job: {req_id}")
    print()
    print("Queue status:")
    status = scheduler.get_status()
    print(f"  Pending: {status['pending']}")
    print(f"  Running: {status['running']}")
    print(f"  Completed: {status['completed']}")


if __name__ == "__main__":
    main()
