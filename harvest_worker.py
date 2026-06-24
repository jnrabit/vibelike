#!/usr/bin/env python3
"""
HarvesterWorker - Background worker for harvesting tasks.
Dequeues harvest requests and processes them, storing results via adapters.
"""

import os
import sys
import time
import logging
from typing import Optional

ROOT = os.path.dirname(os.path.abspath(__file__))

from vibelike.reqqueue.manager import RequestQueue
from vibelike.adapters import HarvestAdapter
from vibelike.models import Request
from vibelike.harvest import (
    harvest_wikipedia_worker,
    harvest_rfcs_worker,
    harvest_peps_worker,
    harvest_tools_worker
)

# Configure logging with more detailed output
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Make harvest operations more verbose
logging.getLogger('harvest').setLevel(logging.INFO)

# Harvest operations mapping
HARVEST_OPERATIONS = {
    "harvest_wikipedia": harvest_wikipedia_worker,
    "harvest_rfcs": harvest_rfcs_worker,
    "harvest_peps": harvest_peps_worker,
    "harvest_tools": harvest_tools_worker,
}


class HarvesterWorker:
    """Background worker that processes harvest requests from the queue."""

    def __init__(
        self,
        queue_db: str = "logs/queue.db",
        harvest_db: str = "ossifikat/data/ossifikat.db",
        poll_interval: float = 5.0
    ):
        """
        Initialize the harvester worker.

        Args:
            queue_db: Path to request queue database
            harvest_db: Path to ossifikat database
            poll_interval: Seconds between queue checks
        """
        self.queue = RequestQueue(db_path=queue_db)
        self.adapter = HarvestAdapter(ossifikat_db_path=harvest_db)
        self.poll_interval = poll_interval
        self.running = False
        logger.info("✓ HarvesterWorker initialized")

    def process_harvest(self, operation: str, **kwargs) -> bool:
        """
        Execute a harvest operation.

        Args:
            operation: Name of operation (harvest_wikipedia, harvest_rfcs, etc.)
            **kwargs: Operation-specific arguments

        Returns:
            True if successful
        """
        if operation not in HARVEST_OPERATIONS:
            logger.error(f"Unknown operation: {operation}")
            return False

        try:
            harvest_fn = HARVEST_OPERATIONS[operation]
            logger.info(f"Running {operation}...")
            result = harvest_fn(**kwargs)
            logger.info(f"✓ {operation} completed: {result}")
            return True
        except Exception as e:
            logger.error(f"✗ {operation} failed: {e}", exc_info=True)
            return False

    def process_request(self, request: Request) -> bool:
        """
        Process a single harvest request.

        Args:
            request: Request object from queue

        Returns:
            True if successful
        """
        logger.info(f"Processing request: {request.req_id} ({request.operation})")

        # Extract operation and arguments from request
        operation = request.operation
        args = {k: v for k, v in request.env.items()} if request.env else {}

        # Execute harvest operation
        success = self.process_harvest(operation, **args)

        # Mark request as completed or failed
        if success:
            self.queue.complete(request.req_id, exit_code=0)
            logger.info(f"✓ Request {request.req_id} completed")
        else:
            self.queue.fail(
                request.req_id,
                error=f"Harvest operation {operation} failed",
                retries=request.retries
            )
            logger.warning(f"✗ Request {request.req_id} failed (retry {request.retries})")

        return success

    def run_once(self) -> bool:
        """
        Process one request from the queue.

        Returns:
            True if a request was processed, False if queue was empty
        """
        # Check queue status
        status = self.queue.get_status()
        logger.debug(f"Queue status: {status.pending} pending, {status.running} running, {status.completed} completed")

        # Dequeue next request
        request = self.queue.dequeue()
        if not request:
            logger.debug("Queue empty, waiting...")
            return False

        # Check if this is a harvest request
        if not request.operation.startswith("harvest_"):
            logger.warning(f"Skipping non-harvest request: {request.operation}")
            self.queue.fail(request.req_id, error="Not a harvest operation")
            return True

        # Process the request
        logger.info(f"[JOB] Starting: {request.req_id[:8]}... ({request.operation})")
        self.process_request(request)
        return True

    def run(self, max_iterations: Optional[int] = None) -> None:
        """
        Run the worker loop (process requests until stopped).

        Args:
            max_iterations: Max requests to process (None = infinite)
        """
        self.running = True
        iteration = 0
        last_status_time = time.time()

        logger.info("HarvesterWorker starting...")
        print("=" * 60)
        print("HARVESTER WORKER")
        print("=" * 60)
        print("[Press Ctrl+C to stop]")
        print("-" * 60)
        print(f"[{time.strftime('%H:%M:%S')}] Ready. Waiting for harvest jobs...")
        print("-" * 60)

        try:
            while self.running:
                # Check iteration limit
                if max_iterations and iteration >= max_iterations:
                    logger.info(f"Reached max iterations ({max_iterations})")
                    break

                # Process one request
                if not self.run_once():
                    # Queue was empty, wait and retry
                    current_time = time.time()

                    # Print status every 30 seconds
                    if current_time - last_status_time >= 30:
                        status = self.queue.get_status()
                        print(f"[{time.strftime('%H:%M:%S')}] Polling... | "
                              f"Pending: {status.pending} | "
                              f"Running: {status.running} | "
                              f"Completed: {status.completed} | "
                              f"Failed: {status.failed}")
                        last_status_time = current_time

                    time.sleep(self.poll_interval)
                else:
                    # Job was processed, show status
                    iteration += 1
                    status = self.queue.get_status()
                    print(f"[{time.strftime('%H:%M:%S')}] ✓ Job completed | "
                          f"Pending: {status.pending} | Completed: {status.completed}")
                    last_status_time = time.time()

        except KeyboardInterrupt:
            print()
            logger.info("Stopping HarvesterWorker...")
        finally:
            self.running = False
            status = self.queue.get_status()
            print("-" * 60)
            logger.info("HarvesterWorker stopped")
            print(f"[{time.strftime('%H:%M:%S')}] Final status: "
                  f"Completed: {status.completed}, Failed: {status.failed}, "
                  f"Pending: {status.pending}")
            print("[BYE] Auf Wiedersehen")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Vibelike Harvester Worker")
    parser.add_argument(
        "--queue-db",
        default="logs/queue.db",
        help="Path to request queue database"
    )
    parser.add_argument(
        "--harvest-db",
        default="ossifikat/data/ossifikat.db",
        help="Path to ossifikat database"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between queue checks"
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Maximum requests to process (default: infinite)"
    )
    parser.add_argument(
        "--full-mode",
        action="store_true",
        help="Auto-schedule harvest jobs (Wikipedia, RFCs, PEPs, Tools)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Document limit per harvest operation (for --full-mode, default: Wikipedia=all phases, RFCs=200, PEPs=300, Tools=50)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show queue and vault status, then exit"
    )

    args = parser.parse_args()

    # Status mode: show queue and vault status, then exit
    if args.status:
        from vibelike.harvest_scheduler import HarvestScheduler
        from vibelike.harvest import CodeVaultWriter

        scheduler = HarvestScheduler(queue_db=args.queue_db)
        status = scheduler.get_status()

        print("\n" + "=" * 60)
        print("VIBELIKE STATUS")
        print("=" * 60)

        print("\n📊 Queue Status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Running: {status['running']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")

        if status['next_request']:
            print(f"\n⏭️  Next Job:")
            print(f"  ID: {status['next_request']['req_id'][:12]}...")
            print(f"  Priority: {status['next_request']['priority']}")

        # Show vault stats
        try:
            vault = CodeVaultWriter(device="cpu")
            print(f"\n📚 Code-Vault:")
            print(f"  Documents: {len(vault.archive)}")
            print(f"  Embeddings: {len(vault.cache)}")
        except Exception as e:
            print(f"\n⚠️  Could not load vault: {e}")

        print("\n" + "=" * 60)
        return

    # Initialize worker
    worker = HarvesterWorker(
        queue_db=args.queue_db,
        harvest_db=args.harvest_db,
        poll_interval=args.poll_interval
    )

    # Full mode: auto-schedule all harvest operations
    if args.full_mode:
        print("\n" + "=" * 60)
        print("FULL MODE: Auto-scheduling all harvest operations")
        print("=" * 60)
        from vibelike.harvest_scheduler import HarvestScheduler
        scheduler = HarvestScheduler(queue_db=args.queue_db)

        ops = [
            ("Wikipedia", lambda: scheduler.schedule_wikipedia_harvest(limit=args.limit, priority=1)),
            ("RFCs", lambda: scheduler.schedule_rfc_harvest(limit=args.limit, priority=2)),
            ("PEPs", lambda: scheduler.schedule_pep_harvest(limit=args.limit, priority=2)),
            ("Tools", lambda: scheduler.schedule_tools_harvest(limit=args.limit, priority=3)),
        ]

        for name, sched_fn in ops:
            req_id = sched_fn()
            print(f"  ✓ {name:12} scheduled: {req_id[:12]}...")

        status = scheduler.get_status()
        print(f"\nQueue ready: {status['pending']} jobs pending")
        print("-" * 60 + "\n")

    # Run worker
    worker.run(max_iterations=args.max_requests)


if __name__ == "__main__":
    main()
