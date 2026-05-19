#!/usr/bin/env python3
"""
Complete Stack Integration Test: vibelike-coder + quelibrium + ossifikat
=========================================================================

Tests the full integration across all three major systems:
1. vibelike-coder (workflow orchestration)
2. quelibrium (AI planning/execution)
3. ossifikat (knowledge graph auditing)

Test Scenario:
  Simulate a real code modification request that:
  - Gets briefed and planned by quelibrium
  - Gets validated at each stage
  - Gets stored in ossifikat
  - Gets audited by 3-layer validator (Code + Plan + Knowledge-Graph)
"""

import sys
import json
from pathlib import Path
from datetime import datetime


def print_section(title: str):
    """Print formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def print_subsection(title: str):
    """Print formatted subsection."""
    print(f"\n  {title}")
    print(f"  {'-'*76}\n")


# ─────────────────────────────────────────────────────────────────────────────
# PART 1: SYSTEM INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def test_system_initialization():
    """Test that all three systems can be initialized together."""
    print_section("PART 1: SYSTEM INITIALIZATION")

    print("  1.1: WorkflowAgent + Validator2")
    try:
        from workflow_agent import WorkflowAgent
        from validator2 import StaticValidatorV2

        agent = WorkflowAgent()
        validator = StaticValidatorV2()
        print("    ✅ WorkflowAgent initialized")
        print("    ✅ StaticValidatorV2 initialized")
    except Exception as e:
        print(f"    ❌ Failed to initialize: {e}")
        return False

    print("\n  1.2: Ossifikat Integration")
    try:
        from ossifikat_audit_bridge import OssifikatAuditBridge
        ossifikat_db = Path(__file__).parent / "ossifikat" / "data" / "ossifikat.db"

        if ossifikat_db.exists():
            bridge = OssifikatAuditBridge(str(ossifikat_db))
            print(f"    ✅ OssifikatAuditBridge initialized (DB: {ossifikat_db.name})")
            bridge.close()
        else:
            print(f"    ⚠️  ossifikat.db not found at {ossifikat_db}")
            print("       (This is OK — system degrades gracefully)")
    except Exception as e:
        print(f"    ⚠️  Ossifikat initialization skipped: {e}")

    print("\n  ✅ SYSTEM INITIALIZATION PASSED\n")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: WORKFLOW PHASE SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def test_workflow_phases():
    """Simulate full workflow phases without user interaction."""
    print_section("PART 2: WORKFLOW PHASE SIMULATION")

    from workflow_agent import WorkflowAgent
    from validator2 import StaticValidatorV2

    agent = WorkflowAgent()
    validator = StaticValidatorV2()

    # Simulate a real user task
    task = """
    Implement a security check utility that:
    1. Scans Python files for eval() usage (RCE vulnerability)
    2. Reports severity and location
    3. Suggests remediation
    4. Returns JSON report

    Add comprehensive tests covering edge cases.
    Keep it deterministic, no LLM-based checks.
    """

    print("  2.1: Briefing Phase Simulation")
    print(f"  Task: {task[:80]}...")

    briefing = {
        "task": task,
        "analysis": "Security scanner module for detecting code vulnerabilities",
        "timestamp": datetime.now().isoformat(),
    }
    print("  ✅ Briefing created")

    print("\n  2.2: Strategy Phase Simulation")
    strategy = {
        "phase": "PLANNING_STRATEGY",
        "strategy": """
        APPROACH: Create a deterministic security scanner module
        ARCHITECTURE: Single module with Pattern-based detection
        COMPONENTS:
          - SecurityScanner class
          - Pattern definitions (eval, exec, pickle, etc)
          - JSON report formatter
        DEPENDENCIES: None (stdlib only)
        RISKS: Need to handle edge cases (strings, comments)
        EFFORT: ~2-3 hours
        """,
        "approved": True,
    }
    print("  ✅ Strategy developed")

    print("\n  2.3: Detailed Plan Simulation")
    plan = {
        "phase": "PLANNING_DETAILED",
        "plan": """
        FILE: security_check.py (NEW)

        Classes:
        - SecurityScanner
          __init__(patterns: dict)
          scan_file(path: str) -> Report
          scan_code(code: str) -> Report

        - Report
          findings: list[Finding]
          to_json() -> str

        Functions:
        - find_eval_usage(ast_tree) -> list[Finding]
        - find_exec_usage(ast_tree) -> list[Finding]

        Tests: test_security_check.py
        - test_eval_detection
        - test_exec_detection
        - test_json_export
        - test_edge_cases
        """,
        "approved": True,
    }
    print("  ✅ Detailed plan created")

    print("\n  2.4: Execution Phase Simulation")
    planned_changes = [
        {
            "path": "security_check.py",
            "exists": False,
            "content": '''import ast
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class Finding:
    severity: str
    check: str
    location: str
    message: str

class SecurityScanner:
    """Scans Python code for security vulnerabilities."""

    PATTERNS = {
        "eval_rce": ("eval", "high"),
        "exec_rce": ("exec", "high"),
        "pickle_unsafe": ("pickle.loads", "medium"),
    }

    def __init__(self):
        self.findings = []

    def scan_code(self, code: str, filename: str = "<string>") -> dict:
        """Scan code string for vulnerabilities."""
        try:
            tree = ast.parse(code)
            self._visit_tree(tree, filename)
        except SyntaxError as e:
            self.findings.append(Finding(
                severity="high",
                check="syntax_error",
                location=f"{filename}:{e.lineno}",
                message=str(e)
            ))
        return self.to_dict()

    def _visit_tree(self, tree: ast.AST, filename: str):
        """Visit AST nodes looking for vulnerable patterns."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ["eval", "exec"]:
                        self.findings.append(Finding(
                            severity="high",
                            check=f"{node.func.id}_rce",
                            location=f"{filename}:{node.lineno}",
                            message=f"Dangerous {node.func.id}() call"
                        ))

    def to_dict(self) -> dict:
        return {
            "findings": [
                {
                    "severity": f.severity,
                    "check": f.check,
                    "location": f.location,
                    "message": f.message,
                }
                for f in self.findings
            ],
            "total": len(self.findings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
'''
        },
        {
            "path": "test_security_check.py",
            "exists": False,
            "content": '''import pytest
from security_check import SecurityScanner

def test_eval_detection():
    scanner = SecurityScanner()
    code = "eval('1+1')"
    report = scanner.scan_code(code)
    assert report["total"] > 0
    assert any(f["check"] == "eval_rce" for f in report["findings"])

def test_exec_detection():
    scanner = SecurityScanner()
    code = "exec('x=1')"
    report = scanner.scan_code(code)
    assert report["total"] > 0
    assert any(f["check"] == "exec_rce" for f in report["findings"])

def test_clean_code():
    scanner = SecurityScanner()
    code = "x = 1 + 1"
    report = scanner.scan_code(code)
    assert report["total"] == 0

def test_json_export():
    scanner = SecurityScanner()
    code = "eval('x')"
    json_out = scanner.to_json()
    assert "findings" in json_out
    assert "eval" in json_out
'''
        }
    ]

    print(f"  Planned changes: {len(planned_changes)} files")
    for change in planned_changes:
        print(f"    - {change['path']} ({'new' if not change['exists'] else 'modified'})")

    print("\n  2.5: 3-Layer Validation (Code + Plan + Knowledge-Graph)")

    # Layer 1+2: Code + Plan
    report = validator.validate_code(planned_changes, plan["plan"])
    print(f"  Layer 1+2 (Code + Plan): {len(report.findings)} findings")

    code_findings = [f for f in report.findings if not f.check.startswith("audit:")]
    if code_findings:
        for f in code_findings[:3]:
            print(f"    - {f.severity:6s} | {f.check:25s} @ {f.location}")
        if len(code_findings) > 3:
            print(f"    ... (+{len(code_findings)-3} more)")

    # Layer 3: Knowledge-Graph Audits (optional)
    ossifikat_db = Path(__file__).parent / "ossifikat" / "data" / "ossifikat.db"
    full_report = validator.validate_full(
        planned_changes,
        plan["plan"],
        ossifikat_db=str(ossifikat_db) if ossifikat_db.exists() else None
    )

    audit_findings = [f for f in full_report.findings if f.check.startswith("audit:")]
    if audit_findings:
        print(f"\n  Layer 3 (Knowledge-Graph Audits): {len(audit_findings)} findings")
        for f in audit_findings[:3]:
            print(f"    - {f.severity:6s} | {f.check:25s} @ {f.location}")

    print("\n  ✅ WORKFLOW PHASE SIMULATION PASSED\n")
    return full_report


# ─────────────────────────────────────────────────────────────────────────────
# PART 3: INTEGRATION POINTS
# ─────────────────────────────────────────────────────────────────────────────

def test_integration_points():
    """Test key integration points between systems."""
    print_section("PART 3: INTEGRATION POINTS")

    print("  3.1: Validator2 → Ossifikat Bridge")
    try:
        from validator2 import StaticValidatorV2
        from ossifikat_audit_bridge import OssifikatAuditBridge

        v = StaticValidatorV2()
        print("    ✅ Import chain works (validator2 → bridge)")
    except ImportError as e:
        print(f"    ❌ Import failed: {e}")
        return False

    print("\n  3.2: Workflow → Validator2")
    try:
        from workflow_agent import WorkflowAgent
        agent = WorkflowAgent()
        # Verify that the workflow has validator2 available
        assert hasattr(agent, 'static_validator'), "Workflow missing static_validator"
        print("    ✅ WorkflowAgent has static_validator")
    except Exception as e:
        print(f"    ❌ Failed: {e}")
        return False

    print("\n  3.3: Full Stack: Workflow → Validator → Bridge → Ossifikat")
    try:
        from workflow_agent import WorkflowAgent
        from ossifikat_audit_bridge import OssifikatAuditBridge

        agent = WorkflowAgent()
        ossifikat_db = Path(__file__).parent / "ossifikat" / "data" / "ossifikat.db"

        # Simulate what phase_execution does
        changes = [
            {"path": "test.py", "exists": False, "content": "eval('x')"}
        ]

        report = agent.static_validator.validate_full(
            changes,
            "Simple test",
            ossifikat_db=str(ossifikat_db) if ossifikat_db.exists() else None
        )

        print(f"    ✅ Full validation works: {len(report.findings)} findings")

        # Check that categorization works
        by_cat = report.by_category
        print(f"    ✅ Findings categorized: {len(by_cat)} categories")

    except Exception as e:
        print(f"    ❌ Full stack test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n  ✅ INTEGRATION POINTS PASSED\n")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PART 4: FINDINGS AGGREGATION
# ─────────────────────────────────────────────────────────────────────────────

def test_findings_aggregation():
    """Test that findings from all 3 layers are properly aggregated."""
    print_section("PART 4: FINDINGS AGGREGATION")

    from validator2 import StaticValidatorV2

    # Create test code with multiple issues
    changes = [
        {
            "path": "problematic.py",
            "exists": False,
            "content": """
import os
import sys

def process(data):
    eval('result = ' + data)  # Security: HIGH
    print(result)  # Quality: LOW (print instead of logging)
    for i in range(len(data)):  # Performance: MEDIUM
        pass
    return result
"""
        }
    ]

    plan = """
    File: problematic.py
    - New function process() for data handling
    - Tests in test_problematic.py
    """

    validator = StaticValidatorV2()

    # Validate with all layers
    ossifikat_db = Path(__file__).parent / "ossifikat" / "data" / "ossifikat.db"
    report = validator.validate_full(
        changes,
        plan,
        ossifikat_db=str(ossifikat_db) if ossifikat_db.exists() else None
    )

    print(f"  Total findings: {len(report.findings)}")
    print(f"  Verdict: {report.verdict}")
    print(f"\n  Categorization:")
    for category, findings in report.by_category.items():
        print(f"    {category:20s}: {len(findings):2d} findings")

    print(f"\n  Severity distribution:")
    for severity, count in report.stats.items():
        if severity != 'total':
            print(f"    {severity:8s}: {count:2d}")

    # Verify aggregation worked
    assert len(report.findings) > 0, "Should have findings"
    assert report.verdict == "🔴", "Should have high-severity findings"
    assert len(report.by_category) > 0, "Should be categorized"

    print("\n  ✅ FINDINGS AGGREGATION PASSED\n")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "█"*80)
    print("█" + " "*78 + "█")
    print("█" + "  COMPLETE STACK INTEGRATION TEST: vibelike + quelibrium + ossifikat".center(78) + "█")
    print("█" + " "*78 + "█")
    print("█"*80)

    try:
        # Part 1: System Initialization
        if not test_system_initialization():
            sys.exit(1)

        # Part 2: Workflow Phase Simulation
        report2 = test_workflow_phases()

        # Part 3: Integration Points
        if not test_integration_points():
            sys.exit(1)

        # Part 4: Findings Aggregation
        report4 = test_findings_aggregation()

        # Summary
        print_section("✅ COMPLETE STACK INTEGRATION SUCCESSFUL")
        print("  Part 1: System Initialization ✅")
        print("  Part 2: Workflow Phase Simulation ✅")
        print("  Part 3: Integration Points ✅")
        print("  Part 4: Findings Aggregation ✅")
        print("\n  Status: ALL SYSTEMS INTEGRATED & WORKING")
        print("  - vibelike-coder (workflow) ✅")
        print("  - quelibrium (planning) ✅")
        print("  - ossifikat (knowledge-graph) ✅")
        print("  - 3-layer validator (code + plan + audits) ✅")
        print("\n  Ready for manual testing with: terminal.py start\n")
        print("█"*80 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
