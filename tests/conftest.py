import pytest
from pathlib import Path
import tempfile
import os

# This is a basic conftest.py to resolve the "fixture not found" errors.
# It sets up temporary resources for tests to run in isolation.

# Add project root to sys.path to allow imports from the project
# This is crucial for the test environment
import sys


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Create a temporary database file path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def queue(temp_db_path: str):
    """Fixture for the RequestQueue."""
    from vibelike.reqqueue.manager import RequestQueue
    # Use a temporary database for isolation
    return RequestQueue(db_path=temp_db_path)


@pytest.fixture
def sandbox_manager(tmp_path: Path):
    """Fixture for the SandboxManager."""
    from vibelike.sandbox.manager import SandboxManager
    # Use a temporary directory for sandboxes
    return SandboxManager(sandbox_base=tmp_path)


@pytest.fixture
def tool_registry(tmp_path: Path):
    """Fixture for the ToolRegistry."""
    from vibelike.tools.registry import ToolRegistry
    from vibelike.tools.cache import ToolCache
    # tools_dir und cache GETRENNT halten — sonst landet die Cache-DB (index.db) im
    # tools_dir und wird vom Scan als Phantom-Tool aufgelesen.
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "dummy-tool").mkdir()  # für test_tool_discovery (Verzeichnis-Scan)
    cache = ToolCache(cache_dir=str(tmp_path / "cache"))
    return ToolRegistry(tools_dir=tools_dir, cache=cache)


@pytest.fixture
def harvest_adapter(temp_db_path: str):
    """Fixture for the HarvestAdapter."""
    from vibelike.adapters.harvest_adapter import HarvestAdapter
    return HarvestAdapter(ossifikat_db_path=temp_db_path)


@pytest.fixture
def tools_adapter(temp_db_path: str):
    """Fixture for the ToolsAdapter."""
    from vibelike.adapters.tools_adapter import ToolsAdapter
    return ToolsAdapter(ossifikat_db_path=temp_db_path)


@pytest.fixture
def terminal_adapter(temp_db_path: str):
    """Fixture for the TerminalAdapter."""
    from vibelike.adapters.terminal_adapter import TerminalAdapter
    return TerminalAdapter(ossifikat_db_path=temp_db_path)

@pytest.fixture
def echo_tool(tool_registry: "ToolRegistry"):
    """A simple 'echo' tool for testing, which is manually registered."""
    from vibelike.tools.models import Tool

    # Aktuelles Tool-Dataclass-Schema (name/path/binary/description), nicht das
    # alte executable/args/triples-Schema (Tool.from_dict existiert nicht mehr).
    tool = Tool(
        name="echo",
        path=Path("/bin/echo"),
        binary="echo",
        description="A simple echo tool.",
    )
    tool_registry._tools[tool.name] = tool  # Direct registration for test purposes
    return tool
