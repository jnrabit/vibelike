"""Tests for Sandbox creation and execution."""

# import pytest
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sandbox.manager import SandboxManager
from sandbox.models import Sandbox
from tools.cache import ToolCache


# fixture
def sandbox_manager(tmp_path):
    """Create a test sandbox manager."""
    return SandboxManager(
        sandbox_base=tmp_path / "sandbox",
        cache=ToolCache()
    )


def test_sandbox_manager_initialization(sandbox_manager):
    """Test sandbox manager initializes."""
    assert sandbox_manager.sandbox_base.exists()


def test_sandbox_creation(sandbox_manager):
    """Test creating a sandbox."""
    req_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    sandbox = sandbox_manager.create(req_id, "echo-tool")

    assert sandbox is not None
    assert sandbox.path.exists()
    assert sandbox.workspace_path.exists()


def test_sandbox_cleanup(sandbox_manager):
    """Test destroying a sandbox."""
    req_id = "test-cleanup"

    sandbox = sandbox_manager.create(req_id, "echo-tool")
    sandbox_path = sandbox.path

    assert sandbox_path.exists()

    sandbox_manager.destroy(req_id)

    # Path should still exist (we don't rm -rf in local dev)
    # but it should no longer be tracked
    assert req_id not in sandbox_manager.active_sandboxes


def test_sandbox_execute(sandbox_manager):
    """Test executing a command in sandbox."""
    req_id = "test-exec"

    sandbox = sandbox_manager.create(req_id, "echo-tool")
    (sandbox.workspace_path / "output").mkdir(parents=True, exist_ok=True)

    tool_script = Path("tools/echo-tool/echo-tool.sh").resolve()
    result = sandbox.execute(
        f"bash {tool_script} --test",
        timeout=30,
        env={},
        cwd="/workspace"
    )

    assert result["exit_code"] == 0
    assert "Echo Tool Execution" in result["stdout"]

    sandbox_manager.destroy(req_id)


def test_sandbox_output_files(sandbox_manager):
    """Test that output files are created and accessible."""
    req_id = "test-output"

    sandbox = sandbox_manager.create(req_id, "echo-tool")
    (sandbox.workspace_path / "output").mkdir(parents=True, exist_ok=True)

    tool_script = Path("tools/echo-tool/echo-tool.sh").resolve()
    sandbox.execute(
        f"bash {tool_script} --test",
        timeout=30,
        env={},
        cwd="/workspace"
    )

    # Check output directory
    output_dir = sandbox.workspace_path / "output"
    assert output_dir.exists()

    # Should have created output.txt
    output_files = list(output_dir.glob("**/*"))
    assert len([f for f in output_files if f.is_file()]) > 0

    sandbox_manager.destroy(req_id)


def test_sandbox_multiple_creation(sandbox_manager):
    """Test creating multiple sandboxes."""
    sandbox1 = sandbox_manager.create("req-1", "echo-tool")
    sandbox2 = sandbox_manager.create("req-2", "echo-tool")

    assert sandbox1.path != sandbox2.path
    assert "req-1" in sandbox_manager.active_sandboxes
    assert "req-2" in sandbox_manager.active_sandboxes

    sandbox_manager.destroy("req-1")
    sandbox_manager.destroy("req-2")


def test_sandbox_model():
    """Test Sandbox model directly."""
    sandbox = Sandbox(
        req_id="test",
        path=Path("/tmp/test-sandbox"),
        user_uid=1000,
        user_gid=1000
    )

    assert sandbox.req_id == "test"
    assert sandbox.workspace_path.name == "workspace"
    assert sandbox.tools_path.name == "tools"
