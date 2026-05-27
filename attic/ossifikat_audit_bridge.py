"""
ossifikat_audit_bridge.py — Bridge zwischen Ossifikat Audits und validator2 Reports
====================================================================================

Konvertiert ossifikat Triple-Audit-Findings zu validator2-kompatiblen Befunden.
Ermöglicht 3-schichtige Validation: Code + Knowledge-Graph + Aggregation.

Public API:
    bridge = OssifikatAuditBridge(db_path)
    report = bridge.run_all_audits()  # -> ExtendedReport
    bridge.close()
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from validator2 import Finding, ExtendedReport
except ImportError:
    # Fallback
    from static_validator import Finding
    from validator2 import ExtendedReport


class OssifikatAuditBridge:
    """Bridge zwischen ossifikat Audit-Checks und validator2 Report-Format."""

    def __init__(self, ossifikat_db_path: str | Path,
                 disabled_audits: set | None = None,
                 confidence_threshold: float = 0.0):
        """
        Initialize bridge to ossifikat database.

        Args:
            ossifikat_db_path: Path to ossifikat.db
            disabled_audits: Set of audit types to skip (e.g. {"unclassified_predicate"})
            confidence_threshold: Only include findings with confidence >= this value
        """
        self.db_path = str(ossifikat_db_path)
        self.disabled_audits = disabled_audits or set()
        self.confidence_threshold = confidence_threshold
        self.view = None

        try:
            from ossifikat.audit import AuditView
            self.view = AuditView(self.db_path)
        except Exception as e:
            print(f"[WARN] Could not initialize AuditView: {e}")
            self.view = None

    def run_all_audits(self) -> ExtendedReport:
        """
        Run all ossifikat audits and return validator2-compatible report.

        Returns:
            ExtendedReport with audit findings mapped to Finding objects
        """
        report = ExtendedReport()

        if not self.view:
            return report

        try:
            from ossifikat.audit import (
                find_orphan_retracts,
                find_functional_predicate_conflicts,
                find_unclassified_predicates,
            )

            # Audit 1: Orphan Retracts (High Confidence → High Severity)
            if "orphan_retract" not in self.disabled_audits:
                self._process_findings(
                    find_orphan_retracts(self.view),
                    audit_type="orphan_retract",
                    severity_map={1.0: "high", 0.8: "medium", 0.5: "medium"},
                    report=report,
                )

            # Audit 2: Functional Conflicts (1.0 confidence → High Severity)
            if "functional_conflict" not in self.disabled_audits:
                self._process_findings(
                    find_functional_predicate_conflicts(self.view),
                    audit_type="functional_conflict",
                    severity_map={1.0: "high"},
                    report=report,
                )

            # Audit 3: Unclassified Predicates (0.4 confidence → Low Severity hint)
            if "unclassified_predicate" not in self.disabled_audits:
                self._process_findings(
                    find_unclassified_predicates(self.view),
                    audit_type="unclassified_predicate",
                    severity_map={0.4: "low"},
                    report=report,
                )

        except Exception as e:
            print(f"[WARN] Audit execution failed: {e}")

        return report

    def _process_findings(
        self,
        findings: list,
        audit_type: str,
        severity_map: dict,
        report: ExtendedReport,
    ) -> None:
        """
        Process audit findings and add to report.

        Args:
            findings: List of AuditFinding objects
            audit_type: Type of audit (for check_id)
            severity_map: Dict mapping confidence to severity
            report: ExtendedReport to add findings to
        """
        for finding in findings:
            # Skip if below confidence threshold
            if finding.confidence < self.confidence_threshold:
                continue

            # Map confidence to severity
            severity = self._map_confidence_to_severity(finding.confidence, severity_map)

            # Create location from subject (triple hash)
            location = f"triple:{finding.subject[:12]}" if finding.subject else "knowledge_graph"

            # Add to report
            report.add(
                Finding(
                    severity=severity,
                    check=f"audit:{audit_type}",
                    location=location,
                    message=finding.object,
                )
            )

    def _map_confidence_to_severity(self, confidence: float, severity_map: dict) -> str:
        """Map confidence score to severity level."""
        for conf_threshold in sorted(severity_map.keys(), reverse=True):
            if confidence >= conf_threshold:
                return severity_map[conf_threshold]
        return "low"

    def close(self) -> None:
        """Close ossifikat view."""
        if self.view:
            try:
                self.view.close()
            except Exception:
                pass
            self.view = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
