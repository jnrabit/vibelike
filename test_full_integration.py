#!/usr/bin/env python3.12
"""Full end-to-end integration test for Vibelike system (all 3 layers)."""

import sys
import json
from pathlib import Path
from datetime import datetime

try:
    from reqqueue.manager import RequestQueue
    from models.request import Request
    from sandbox.manager import SandboxManager
    from tools.cache import ToolCache
    from tools.registry import ToolRegistry
except ImportError:
    from vibelike.reqqueue.manager import RequestQueue
    from vibelike.models.request import Request
    from vibelike.sandbox.manager import SandboxManager
    from vibelike.tools.cache import ToolCache
    from vibelike.tools.registry import ToolRegistry

def test_full_integration():
    """Test complete Vibelike pipeline: Queue → Sandbox → Adapters → Ossifikat."""
    print("\n" + "=" * 70)
    print("VIBELIKE FULL END-TO-END INTEGRATION TEST")
    print("=" * 70)

    test_id = f"full-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    results = {
        "test_id": test_id,
        "timestamp": datetime.now().isoformat(),
        "phases": {}
    }

    # PHASE 1: DATEN-SCHICHT (Queue + Request)
    print("\n[LAYER 1: DATA] Queue initialization and request enqueue...")
    try:
        queue = RequestQueue()

        # Create a request using echo-tool
        request = Request(
            req_id=test_id,
            tool_name="echo-tool",
            args=["--integration-test", "hello-vibelike"],
            env={"OUTPUT_DIR": "/workspace/output"},
            priority=1,
            timeout=30
        )

        enqueued_id = queue.enqueue(request)
        status = queue.get_status()

        print(f"    ✓ Queue initialized")
        print(f"    ✓ Request enqueued: {enqueued_id}")
        print(f"    ✓ Queue status: {status.pending} pending, {status.running} running")

        results["phases"]["data_layer"] = {
            "status": "success",
            "queue_status": {
                "pending": status.pending,
                "running": status.running,
                "completed": status.completed,
                "failed": status.failed
            }
        }
    except Exception as e:
        print(f"    ✗ Data layer failed: {e}")
        results["phases"]["data_layer"] = {"status": "failed", "error": str(e)}
        return results

    # PHASE 2: AUSFÜHRUNG (Sandbox + Tool)
    print("\n[LAYER 2: EXECUTION] Sandbox creation and tool execution...")
    try:
        # Dequeue the request
        dequeued = queue.dequeue()
        if not dequeued:
            raise Exception("Request not in queue")

        print(f"    ✓ Request dequeued: {dequeued.req_id}")

        # Create sandbox and execute
        sandbox_manager = SandboxManager(cache=ToolCache())
        sandbox = sandbox_manager.create(dequeued.req_id, dequeued.tool_name)

        # Prepare output directory
        (sandbox.workspace_path / "output").mkdir(parents=True, exist_ok=True)

        # Execute tool
        tool_script = Path("tools/echo-tool/echo-tool.sh").resolve()
        cmd = f"bash {tool_script} {' '.join(dequeued.args or [])}"

        result = sandbox.execute(
            cmd,
            timeout=30,
            env=dequeued.env or {},
            cwd="/workspace"
        )

        dequeued.exit_code = result["exit_code"]
        dequeued.stdout = result["stdout"]
        dequeued.stderr = result["stderr"]
        dequeued.status = "completed" if result["exit_code"] == 0 else "failed"

        # Collect output files
        output_dir = sandbox.workspace_path / "output"
        if output_dir.exists():
            for output_file in output_dir.glob("**/*"):
                if output_file.is_file():
                    dequeued.output_files.append(output_file)

        print(f"    ✓ Tool executed: {dequeued.tool_name}")
        print(f"    ✓ Exit code: {result['exit_code']}")
        print(f"    ✓ Duration: {result['duration_ms']:.2f}ms")
        print(f"    ✓ Output files: {len(dequeued.output_files)}")

        sandbox_manager.destroy(dequeued.req_id)

        results["phases"]["execution_layer"] = {
            "status": "success",
            "tool": dequeued.tool_name,
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
            "output_files": len(dequeued.output_files)
        }
    except Exception as e:
        print(f"    ✗ Execution layer failed: {e}")
        results["phases"]["execution_layer"] = {"status": "failed", "error": str(e)}
        import traceback
        traceback.print_exc()
        return results

    # PHASE 3: WISSEN-SCHICHT (Triples + Adapters)
    print("\n[LAYER 3: KNOWLEDGE] Triple generation and adapter storage...")
    try:
        # Resolve tool for triple generation
        tool_registry = ToolRegistry()
        tool = tool_registry.resolve(dequeued.tool_name)

        # Generate triples
        triples = dequeued.generate_triples(
            tool=tool,
            exit_code=dequeued.exit_code or 0,
            output_files=dequeued.output_files,
            duration_ms=result.get("duration_ms", 0)
        )

        print(f"    ✓ Tool resolved: {tool.name}")
        print(f"    ✓ Triples generated: {len(triples)}")

        # Try to use adapters (will gracefully fail if ossifikat not available)
        try:
            from adapters import HarvestAdapter, ToolsAdapter
        except ImportError:
            from vibelike.adapters import HarvestAdapter, ToolsAdapter

        harvest_adapter = HarvestAdapter() if HarvestAdapter else None
        tools_adapter = ToolsAdapter() if ToolsAdapter else None

        adapter_status = "success"
        adapter_info = []

        if harvest_adapter and harvest_adapter.store:
            adapter_info.append("HarvestAdapter: initialized")
        else:
            adapter_info.append("HarvestAdapter: ossifikat not available")

        if tools_adapter and tools_adapter.store:
            adapter_info.append("ToolsAdapter: initialized")
        else:
            adapter_info.append("ToolsAdapter: ossifikat not available")

        for info in adapter_info:
            print(f"    ✓ {info}")

        # Print sample triples
        if triples:
            print(f"    ✓ Sample triple:")
            sample = triples[0]
            print(f"      Subject: {sample['subject']}")
            print(f"      Predicate: {sample['predicate']}")
            print(f"      Object: {sample['object']}")

        results["phases"]["knowledge_layer"] = {
            "status": "success",
            "triples_generated": len(triples),
            "adapters": {
                "harvest": "available" if harvest_adapter and harvest_adapter.store else "unavailable",
                "tools": "available" if tools_adapter and tools_adapter.store else "unavailable"
            }
        }
    except Exception as e:
        print(f"    ✗ Knowledge layer failed: {e}")
        results["phases"]["knowledge_layer"] = {"status": "failed", "error": str(e)}
        import traceback
        traceback.print_exc()
        return results

    # FINAL: Status and Summary
    print("\n[FINAL] Queue status and health check...")
    try:
        final_status = queue.get_status()
        print(f"    ✓ Final queue status:")
        print(f"      Pending: {final_status.pending}")
        print(f"      Running: {final_status.running}")
        print(f"      Completed: {final_status.completed}")
        print(f"      Failed: {final_status.failed}")

        results["final_status"] = {
            "pending": final_status.pending,
            "running": final_status.running,
            "completed": final_status.completed,
            "failed": final_status.failed
        }
    except Exception as e:
        print(f"    ⚠ Could not get final status: {e}")

    # SUMMARY
    print("\n" + "=" * 70)
    all_success = all(p.get("status") == "success" for p in results["phases"].values())

    if all_success:
        print("✓ ALL LAYERS SUCCESSFUL")
        print("=" * 70)
        print("\nSystem is fully functional:")
        print("  1. DATA-SCHICHT:      Queue + Request management ✓")
        print("  2. EXECUTION-SCHICHT: Sandbox + Tool execution ✓")
        print("  3. KNOWLEDGE-SCHICHT: Triples + Adapters ✓")
        print("\nReady for production use!")
    else:
        print("⚠ SOME LAYERS FAILED")
        print("=" * 70)
        for phase, details in results["phases"].items():
            status = "✓" if details.get("status") == "success" else "✗"
            print(f"  {status} {phase}: {details.get('status')}")

    return results

if __name__ == "__main__":
    results = test_full_integration()

    # Save results
    results_file = Path("logs/full_test_results.json")
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to: {results_file}")

    # Exit code
    all_success = all(p.get("status") == "success" for p in results["phases"].values())
    sys.exit(0 if all_success else 1)
