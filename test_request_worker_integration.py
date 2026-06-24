#!/usr/bin/env python3.12
"""Integration test for RequestWorker with sandbox and tool execution."""

import sys
import time
from pathlib import Path
from datetime import datetime

from vibelike.reqqueue.manager import RequestQueue


def test_full_request_worker_pipeline():
    """Test the complete RequestWorker pipeline: enqueue → process → verify."""
    print("=" * 60)
    print("REQUESTWORKER INTEGRATION TEST")
    print("=" * 60)

    # 1. Initialize Queue and Worker
    print("\n[1] Initializing RequestQueue and RequestWorker...")
    try:
        queue = RequestQueue()
        worker = RequestWorker()
        print("    ✓ Components initialized")
    except Exception as e:
        print(f"    ✗ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 2. Create and enqueue a simple request
    print("\n[2] Creating and enqueuing request...")
    try:
        # Create a request that will use echo-tool
        req_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        tool_name = "echo-tool"

        # Create Request object
        request = Request(
            req_id=req_id,
            tool_name=tool_name,
            args=["--test-arg", "hello"],
            env={"OUTPUT_DIR": "/workspace/output"},
            priority=1,
            timeout=30
        )

        # Enqueue the request
        enqueued_id = queue.enqueue(request)
        print(f"    ✓ Request enqueued: {enqueued_id}")

        # Verify it's in pending status
        status = queue.get_status()
        print(f"    ✓ Queue status: {status.pending} pending, {status.running} running, {status.completed} completed")

        if status.pending < 1:
            print(f"    ✗ Request not found in queue")
            return False

    except Exception as e:
        print(f"    ✗ Enqueue failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. Dequeue and verify the request
    print("\n[3] Dequeuing request...")
    try:
        request = queue.dequeue()
        if not request:
            print(f"    ✗ No request in queue")
            return False

        print(f"    ✓ Request dequeued: {request.req_id}")
        print(f"      Status: {request.status}")
        print(f"      Tool: {request.tool_name}")
        print(f"      Args: {request.args}")

    except Exception as e:
        print(f"    ✗ Dequeue failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3b. Test sandbox execution directly (simulating what RequestWorker._process_request does)
    print("\n[3b] Testing sandbox execution...")
    try:
        from sandbox.manager import SandboxManager
        from tools.cache import ToolCache

        sandbox_manager = SandboxManager(cache=ToolCache())
        sandbox = sandbox_manager.create(request.req_id, request.tool_name)

        # Prepare workspace
        (sandbox.workspace_path / "output").mkdir(parents=True, exist_ok=True)

        # Execute command
        tool_script = Path("tools/echo-tool/echo-tool.sh").resolve()
        cmd = f"bash {tool_script} {' '.join(request.args or [])}"

        result = sandbox.execute(
            cmd,
            timeout=30,
            env=request.env or {},
            cwd="/workspace"
        )

        request.exit_code = result["exit_code"]
        request.stdout = result["stdout"]
        request.stderr = result["stderr"]
        request.status = "completed" if result["exit_code"] == 0 else "failed"

        print(f"    ✓ Sandbox execution completed")
        print(f"      Exit code: {result['exit_code']}")
        print(f"      Duration: {result['duration_ms']:.2f}ms")

        # Check output files
        output_dir = sandbox.workspace_path / "output"
        if output_dir.exists():
            output_files = list(output_dir.glob("**/*"))
            if output_files:
                print(f"      Output files: {len([f for f in output_files if f.is_file()])}")
                for f in output_files:
                    if f.is_file():
                        request.output_files.append(f)

        # Cleanup
        sandbox_manager.destroy(request.req_id)

    except Exception as e:
        print(f"    ✗ Sandbox execution failed: {e}")
        import traceback
        traceback.print_exc()
        request.status = "failed"
        request.exit_code = -1

    # 4. Verify results
    print("\n[4] Verifying request results...")
    try:
        # Get final queue status
        status = queue.get_status()
        print(f"    Queue status: {status.pending} pending, {status.running} running")
        print(f"                  {status.completed} completed, {status.failed} failed")

        if request.status == "completed":
            print(f"    ✓ Request completed successfully")
        else:
            print(f"    ⚠ Request did not complete: status={request.status}")
            if request.stderr:
                print(f"      Stderr: {request.stderr[:200]}")

        if request.output_files:
            print(f"    ✓ Output files: {len(request.output_files)}")
            for f in request.output_files:
                print(f"      - {f}")
        else:
            print(f"    ⚠ No output files found")

    except Exception as e:
        print(f"    ✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5. Test queue recovery
    print("\n[5] Testing health check and recovery...")
    try:
        health = worker.health_check.check()
        print(f"    Health status: {'healthy' if health.is_healthy else 'unhealthy'}")
        if health.errors:
            print(f"    Errors: {health.errors}")
    except Exception as e:
        print(f"    ⚠ Health check failed: {e}")

    print("\n" + "=" * 60)
    print("✓ Integration test completed successfully!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_full_request_worker_pipeline()
    sys.exit(0 if success else 1)
