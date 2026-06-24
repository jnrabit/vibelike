import pytest
from pathlib import Path
import sys
from vibelike.sandbox.manager import SandboxManager


def test_sandbox_manager_fixture(sandbox_manager: SandboxManager):
    """Fixture loads correctly."""
    assert sandbox_manager is not None
    assert isinstance(sandbox_manager, SandboxManager)


def test_create_sandbox(sandbox_manager: SandboxManager):
    """Test creating a sandbox environment."""
    sandbox_id = sandbox_manager.create_sandbox(
        image="python:3.12-slim",
        timeout=30
    )
    assert sandbox_id is not None
    assert isinstance(sandbox_id, str)


def test_run_command_in_sandbox(sandbox_manager: SandboxManager):
    """Test running a command in sandbox."""
    sandbox_id = sandbox_manager.create_sandbox(
        image="python:3.12-slim",
        timeout=30
    )

    result = sandbox_manager.run(
        sandbox_id,
        command="echo 'hello world'"
    )
    assert result is not None


def test_cleanup_sandbox(sandbox_manager: SandboxManager):
    """Test cleaning up a sandbox."""
    sandbox_id = sandbox_manager.create_sandbox(
        image="python:3.12-slim",
        timeout=30
    )

    # Cleanup should not raise
    sandbox_manager.cleanup(sandbox_id)


def test_sandbox_isolation(sandbox_manager: SandboxManager):
    """Test that sandboxes are isolated."""
    sb1 = sandbox_manager.create_sandbox(image="python:3.12-slim", timeout=30)
    sb2 = sandbox_manager.create_sandbox(image="python:3.12-slim", timeout=30)

    # Two different sandbox IDs should be created
    assert sb1 != sb2
