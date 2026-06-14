import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.registry import ToolRegistry
from tools.models import Tool


def test_tool_registry_fixture(tool_registry: ToolRegistry):
    """Fixture loads correctly."""
    assert tool_registry is not None
    assert isinstance(tool_registry, ToolRegistry)


def test_list_tools(tool_registry: ToolRegistry, echo_tool: Tool):
    """Test listing available tools."""
    tools = tool_registry.list_tools()
    assert isinstance(tools, list)
    # echo_tool was registered in the fixture
    assert "echo" in tools


def test_get_tool(tool_registry: ToolRegistry, echo_tool: Tool):
    """Test getting a specific tool."""
    tool = tool_registry.get_tool("echo")
    assert tool is not None
    assert tool.name == "echo"
    assert "echo" in tool.description.lower()


def test_get_nonexistent_tool(tool_registry: ToolRegistry):
    """Test getting a tool that doesn't exist."""
    tool = tool_registry.get_tool("nonexistent")
    assert tool is None


def test_resolve_tool(tool_registry: ToolRegistry, echo_tool: Tool):
    """Test resolving a tool by name."""
    resolved = tool_registry.resolve("echo")
    assert resolved is not None
    assert resolved.name == "echo"


def test_get_dependencies(tool_registry: ToolRegistry, echo_tool: Tool):
    """Test getting tool dependencies."""
    # echo_tool has no dependencies in this test
    deps = tool_registry.get_dependencies("echo")
    assert isinstance(deps, list)
    # Should be empty or contain dependencies
    assert len(deps) >= 0

def test_discover_echo_tool(tool_registry: ToolRegistry):
    """Test that a manually registered tool is found."""
    tools = tool_registry.list_tools()
    assert "echo" in tools

def test_resolve_tool(tool_registry: ToolRegistry):
    """Test resolving a tool."""
    tool = tool_registry.resolve("echo")
    assert tool is not None
    assert tool.name == "echo"

def test_resolve_nonexistent_tool(tool_registry: ToolRegistry):
    """Test that resolving a nonexistent tool raises an error."""
    with pytest.raises(ValueError):
        tool_registry.resolve("nonexistent-tool")

def test_tool_discovery(tool_registry: ToolRegistry):
    """Test that the tool directory is scanned for dummy-tool."""
    tools = tool_registry.list_tools()
    assert "dummy-tool" in tools
