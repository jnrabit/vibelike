"""Tests for Tool Registry and Tool Models."""

# import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.registry import ToolRegistry
from tools.models import Tool, TripleTemplate


# fixture
def tool_registry():
    """Create a tool registry with test tools."""
    return ToolRegistry()


def test_tool_registry_initialization(tool_registry):
    """Test registry initializes properly."""
    assert tool_registry.tools_dir.exists()
    assert isinstance(tool_registry._tools, dict)


def test_discover_echo_tool(tool_registry):
    """Test that echo-tool is discovered."""
    tools = tool_registry.list_tools()
    assert "echo-tool" in tools


def test_resolve_tool(tool_registry):
    """Test resolving a tool by name."""
    tool = tool_registry.resolve("echo-tool")
    assert tool.name == "echo-tool"
    assert tool.path.exists()
    assert tool.binary == "echo-tool.sh"


def test_resolve_nonexistent_tool(tool_registry):
    """Test that resolving nonexistent tool raises error."""
    with pytest.raises(ValueError):
        tool_registry.resolve("nonexistent-tool-xyz")


def test_tool_discovery(tool_registry):
    """Test that tools are discovered from filesystem."""
    tools = tool_registry.list_tools()
    # Should have at least echo-tool
    assert len(tools) > 0
    assert "echo-tool" in tools


def test_triple_template_evaluate():
    """Test TripleTemplate evaluation."""
    template = TripleTemplate(
        subject="tool:{tool_name}",
        predicate="executed",
        object="{req_id}",
        condition="exit_code == 0"
    )

    # Success case
    context = {"exit_code": 0, "tool_name": "gcc", "req_id": "req-1"}
    assert template.evaluate(**context) is True

    # Failure case
    context["exit_code"] = 1
    assert template.evaluate(**context) is False


def test_triple_template_render():
    """Test TripleTemplate rendering with variable substitution."""
    template = TripleTemplate(
        subject="tool:{tool_name}",
        predicate="executed_by",
        object="request:{req_id}"
    )

    subject, predicate, obj, confidence = template.render(
        tool_name="gcc-13",
        req_id="req-123"
    )

    assert subject == "tool:gcc-13"
    assert predicate == "executed_by"
    assert obj == "request:req-123"
    assert confidence == 1.0


def test_tool_model():
    """Test Tool model creation."""
    tool = Tool(
        name="test-tool",
        path=Path("/tools/test-tool"),
        type="utility",
        binary="test",
        version="1.0.0"
    )

    assert tool.name == "test-tool"
    assert tool.version == "1.0.0"
    assert tool.type == "utility"


def test_tool_binary_path():
    """Test Tool.get_full_binary_path()."""
    tool = Tool(
        name="gcc",
        path=Path("/tools/gcc-13"),
        binary="gcc"
    )

    binary_path = tool.get_full_binary_path()
    assert "gcc" in str(binary_path)
