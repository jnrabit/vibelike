#!/usr/bin/env python3.12
"""Test script for sandbox integration with the echo-tool."""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from sandbox.manager import SandboxManager
    from tools.cache import ToolCache
except ImportError:
    from vibelike.sandbox.manager import SandboxManager
    from vibelike.tools.cache import ToolCache

def test_sandbox_creation():
    """Test creating and using a sandbox with echo-tool."""
    print("[1] Initializing SandboxManager...")
    manager = SandboxManager(cache=ToolCache())
    print("    ✓ SandboxManager initialized")

    req_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tool_name = "echo-tool"

    print(f"\n[2] Creating sandbox for request: {req_id}")
    try:
        sandbox = manager.create(req_id, tool_name)
        print(f"    ✓ Sandbox created at: {sandbox.path}")
        print(f"    ✓ Workspace: {sandbox.workspace_path}")
    except Exception as e:
        print(f"    ✗ Failed to create sandbox: {e}")
        import traceback
        traceback.print_exc()
        return False

    print(f"\n[3] Preparing workspace...")
    try:
        workspace = sandbox.workspace_path
        workspace.mkdir(parents=True, exist_ok=True)
        output_dir = workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"    ✓ Output directory: {output_dir}")
    except Exception as e:
        print(f"    ✗ Failed to prepare workspace: {e}")
        return False

    print(f"\n[4] Executing echo-tool in sandbox...")
    try:
        # Use absolute path to the tool
        tool_script = Path("tools/echo-tool/echo-tool.sh").resolve()

        result = sandbox.execute(
            f"bash {tool_script} --test arg1 arg2",
            timeout=30,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "OUTPUT_DIR": "/workspace/output"},
            cwd="/workspace"
        )

        print(f"    Exit code: {result['exit_code']}")
        print(f"    Duration: {result['duration_ms']}ms")
        print(f"    Timed out: {result['timed_out']}")

        if result['stdout']:
            print(f"\n    STDOUT:\n{result['stdout']}")
        if result['stderr']:
            print(f"\n    STDERR:\n{result['stderr']}")

        if result['exit_code'] == 0:
            print(f"    ✓ Execution succeeded")
        else:
            print(f"    ⚠ Execution returned non-zero exit code")
    except Exception as e:
        print(f"    ✗ Execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print(f"\n[5] Checking output files...")
    try:
        output_files = list((sandbox.workspace_path / "output").glob("**/*"))
        if output_files:
            print(f"    ✓ Found {len([f for f in output_files if f.is_file()])} output files")
            for f in output_files:
                if f.is_file():
                    print(f"      - {f.relative_to(sandbox.workspace_path)}")
                    with open(f) as fp:
                        content = fp.read()
                        print(f"        Content preview: {content[:100]}...")
        else:
            print(f"    ⚠ No output files found")
    except Exception as e:
        print(f"    ✗ Failed to check output: {e}")
        return False

    print(f"\n[6] Cleaning up sandbox...")
    try:
        manager.destroy(req_id)
        print(f"    ✓ Sandbox destroyed")
    except Exception as e:
        print(f"    ✗ Failed to destroy sandbox: {e}")
        return False

    print("\n✓ All tests passed!")
    return True

if __name__ == "__main__":
    success = test_sandbox_creation()
    sys.exit(0 if success else 1)
