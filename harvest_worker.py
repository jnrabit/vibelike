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
sys.path.insert(0, ROOT)

try:
    from reqqueue.manager import RequestQueue
except ImportError:
    from vibelike.reqqueue.manager import RequestQueue

try:
    from adapters import HarvestAdapter
except ImportError:
    from vibelike.adapters import HarvestAdapter

try:
    from models import Request
except ImportError:
    from vibelike.models import Request

try:
    from harvest import (
        harvest_wikipedia_worker,
        harvest_rfcs_worker,
        harvest_peps_worker,
        harvest_tools_worker
    )
except ImportError:
    from vibelike.harvest import (
        harvest_wikipedia_worker,
        harvest_rfcs_worker,
        harvest_peps_worker,
        harvest_tools_worker
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

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
        # Dequeue next request
        request = self.queue.dequeue()
        if not request:
            return False

        # Check if this is a harvest request
        if not request.operation.startswith("harvest_"):
            logger.warning(f"Skipping non-harvest request: {request.operation}")
            self.queue.fail(request.req_id, error="Not a harvest operation")
            return True

        # Process the request
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

        logger.info("HarvesterWorker starting...")
        print("=" * 60)
        print("HARVESTER WORKER")
        print("=" * 60)
        print("[Press Ctrl+C to stop]")
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
                    logger.debug(f"Queue empty, waiting {self.poll_interval}s...")
                    time.sleep(self.poll_interval)
                else:
                    iteration += 1

        except KeyboardInterrupt:
            logger.info("Stopping HarvesterWorker...")
        finally:
            self.running = False
            logger.info("HarvesterWorker stopped")
            print("-" * 60)
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

    args = parser.parse_args()

    # Initialize and run worker
    worker = HarvesterWorker(
        queue_db=args.queue_db,
        harvest_db=args.harvest_db,
        poll_interval=args.poll_interval
    )
    worker.run(max_iterations=args.max_requests)


if __name__ == "__main__":
    main()
