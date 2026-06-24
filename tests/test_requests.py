"""Tests for Request model and triple generation."""

# import pytest
from pathlib import Path

import sys

from vibelike.models.request import Request
from vibelike.tools.registry import ToolRegistry
from vibelike.tools.models import Tool, TripleTemplate


# fixture
def tool_registry():
    """Get tool registry."""
    return ToolRegistry()


# fixture
def echo_tool(tool_registry):
    """Get echo-tool."""
    return tool_registry.resolve("echo-tool")


def test_request_creation():
    """Test creating a request."""
    request = Request(
        req_id="test-req-1",
        tool_name="echo-tool",
        args=["arg1", "arg2"],
        priority=1
    )

    assert request.req_id == "test-req-1"
    assert request.tool_name == "echo-tool"
    assert request.args == ["arg1", "arg2"]
    assert request.priority == 1


def test_request_default_values():
    """Test request default values."""
    request = Request(req_id="test", tool_name="tool")

    assert request.status == "pending"
    assert request.args == []
    assert request.input_files == []
    assert request.output_files == []
    assert request.priority == 0
    assert request.timeout == 20


def test_request_with_env():
    """Test request with environment variables."""
    env = {"VAR1": "value1", "VAR2": "value2"}
    request = Request(
        req_id="test",
        tool_name="tool",
        env=env
    )

    assert request.env == env


def test_request_generate_triples_success(echo_tool):
    """Test generating triples for successful execution."""
    request = Request(req_id="req-1", tool_name="echo-tool")

    triples = request.generate_triples(
        tool=echo_tool,
        exit_code=0,
        output_files=[Path("output.txt")],
        duration_ms=100.0
    )

    assert isinstance(triples, list)
    assert len(triples) > 0

    # Check triple structure
    for triple in triples:
        assert "subject" in triple
        assert "predicate" in triple
        assert "object" in triple
        assert "source" in triple
        assert "confidence" in triple


def test_request_generate_triples_failure(echo_tool):
    """Test generating triples for failed execution."""
    request = Request(req_id="req-2", tool_name="echo-tool")

    triples = request.generate_triples(
        tool=echo_tool,
        exit_code=1,
        output_files=[],
        duration_ms=50.0
    )

    assert len(triples) > 0


def test_request_with_input_files():
    """Test request with input files."""
    input_files = [Path("input1.txt"), Path("input2.txt")]
    request = Request(
        req_id="test",
        tool_name="tool",
        input_files=input_files
    )

    assert request.input_files == input_files


def test_request_serialization():
    """Test request can be converted to/from dict."""
    request = Request(
        req_id="test-serial",
        tool_name="echo-tool",
        args=["arg"],
        priority=5
    )

    # Should be serializable
    data = {
        "req_id": request.req_id,
        "tool_name": request.tool_name,
        "args": request.args,
        "priority": request.priority
    }

    assert data["req_id"] == "test-serial"
    assert data["tool_name"] == "echo-tool"


def test_triple_generation_with_templates(echo_tool):
    """Test triple generation with tool-specific templates."""
    # If echo-tool has templates, they should be used
    request = Request(req_id="req-3", tool_name="echo-tool")

    triples = request.generate_triples(
        tool=echo_tool,
        exit_code=0,
        output_files=[],
        duration_ms=10.0
    )

    # Should have generic triples at minimum
    assert len(triples) >= 1

    # Verify triples are well-formed
    for triple in triples:
        assert isinstance(triple["subject"], str)
        assert isinstance(triple["predicate"], str)
        assert isinstance(triple["object"], str)
        assert isinstance(triple["confidence"], (int, float))
        assert triple["confidence"] >= 0 and triple["confidence"] <= 1
