"""
static_validator.py — Deterministische Validierung für Workflow-Phasen
======================================================================

Pure-Python Static Analyzer, der ohne LLM auskommt und deshalb:
- nie halluziniert
- in < 500ms pro Code-Block läuft
- reproduzierbar dasselbe Ergebnis liefert

Komplementär zum LLM-Validator: hardcoded Checks finden Fakten
(Syntax-Bugs, Pfad-Drift, Security-Patterns), das LLM macht Reasoning
(Annahmen, Plan-Logik). Beide laufen parallel im Workflow.

Public API:
    StaticValidator().validate_code(planned_changes, plan_text) -> Report
    StaticValidator().validate_plan(plan_text, plan_kind="detail") -> Report

Konsumiert von workflow_agent.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ─────────────────────────────────────────────────────────────────────────────
# Datenmodell
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    severity: str        # "high" | "medium" | "low"
    check: str           # Name des Checks für Gruppierung
    location: str        # "file.py:42" oder "<plan>" oder ""
    message: str         # Kurze, konkrete Beschreibung


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """🔴/🟡/🟢 basierend auf höchster Severity."""
        sevs = {f.severity for f in self.findings}
        if "high" in sevs:
            return "🔴"
        if "medium" in sevs:
            return "🟡"
        if "low" in sevs:
            return "🟡"
        return "🟢"

    def add(self, *findings: Finding) -> None:
        self.findings.extend(findings)

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def render(self) -> str:
        """Lesbares Render für Konsolen-Output."""
        if not self.findings:
            return f"{self.verdict} kein deterministischer Bug gefunden"

        lines = [f"{self.verdict} {len(self.findings)} Befund(e):"]
        # Nach Severity gruppieren
        for sev_label in ("high", "medium", "low"):
            group = [f for f in self.findings if f.severity == sev_label]
            if not group:
                continue
            icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}[sev_label]
            for f in group:
                loc = f" ({f.location})" if f.location else ""
                lines.append(f"  {icon} [{f.check}]{loc} {f.message}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────


# Module die "external" sind aber wir nicht installieren wollen → ok
_KNOWN_EXTERNAL = {
    "requests", "numpy", "pandas", "sentence_transformers", "torch",
    "transformers", "ollama", "openai", "anthropic", "fastapi", "flask",
    "django", "sqlalchemy", "pydantic", "bs4", "beautifulsoup4", "lxml",
    "yaml", "ruff", "pytest", "click", "rich", "tqdm",
}

# Security-Patterns, die wir konkret als Bug ankreiden
_SECURITY_PATTERNS = [
    (r"\beval\s*\(", "high", "eval() — RCE-Risiko, fast immer vermeidbar"),
    (r"\bexec\s*\(", "high", "exec() — RCE-Risiko"),
    (r"shell\s*=\s*True", "medium", "subprocess shell=True — Command Injection wenn Input nicht kontrolliert"),
    (r"pickle\.loads?\s*\(", "medium", "pickle.load — RCE bei untrusted input"),
    (r"yaml\.load\s*\(\s*[^,)]+\)", "medium", "yaml.load ohne Loader — nutze yaml.safe_load"),
    (r"\.\./", "low", "'../' im Code — Pfad-Traversal-Verdacht"),
    (r"(?i)\b(password|secret|api_key|token)\s*=\s*[\"'][A-Za-z0-9_\-]{8,}[\"']", "high",
     "hardcoded credential — gehört in env/secret-store, nicht in Code"),
    (r"verify\s*=\s*False", "medium", "TLS-Verification deaktiviert"),
    (r"input\s*\(.*\).*os\.system", "high", "os.system mit user input — Command Injection"),
]


class StaticValidator:
    """Deterministischer Code- und Plan-Validator."""

    def __init__(self, project_root: Path | None = None):
        self.root = (project_root or Path(__file__).parent).resolve()

    # ─── Code-Validierung ────────────────────────────────────────────────

    def validate_code(self, planned_changes: list[dict], plan_text: str = "") -> Report:
        """Hauptcheck für die EXECUTION-Phase.

        planned_changes: aus workflow_agent._parse_code() →
            [{"path": str, "content": str, "exists": bool}, ...]
        plan_text: der genehmigte Detail-Plan (für Drift-Check)
        """
        report = Report()

        for change in planned_changes:
            path = change["path"]
            content = change["content"]
            rel = self._rel(path)

            # Python-spezifische Checks nur auf .py-Files
            if not path.endswith(".py"):
                continue

            tree = self._check_syntax(rel, content, report)
            if tree is not None:
                self._check_imports(rel, tree, report)
                self._check_complexity(rel, tree, report)

            self._check_security_patterns(rel, content, report)
            self._check_external_linter(rel, content, report)

        self._check_plan_drift(plan_text, planned_changes, report)
        self._check_loc_sanity(plan_text, planned_changes, report)
        self._check_test_existence(plan_text, planned_changes, report)

        return report

    # ─── Plan-Validierung ────────────────────────────────────────────────

    def validate_plan(self, plan_text: str, plan_kind: str = "detail") -> Report:
        """Hauptcheck für Plan-Phasen (Briefing / Strategy / Detail-Plan)."""
        report = Report()
        self._check_plan_structure(plan_text, plan_kind, report)
        self._check_plan_specificity(plan_text, plan_kind, report)
        return report

    # ─────────────────────────────────────────────────────────────────────
    # Einzel-Checks (Code)
    # ─────────────────────────────────────────────────────────────────────

    def _check_syntax(self, rel: str, content: str, report: Report) -> ast.AST | None:
        """ast.parse — kompiliert der Code überhaupt?"""
        try:
            return ast.parse(content, filename=rel)
        except SyntaxError as e:
            report.add(Finding(
                severity="high",
                check="syntax",
                location=f"{rel}:{e.lineno or '?'}",
                message=f"SyntaxError: {e.msg}",
            ))
            return None

    def _check_imports(self, rel: str, tree: ast.AST, report: Report) -> None:
        """Imports auf Existenz prüfen (find_spec für top-level Module)."""
        imports = self._extract_imports(tree)
        for mod, lineno in imports:
            top = mod.split(".")[0]
            # Stdlib, bekannte externals, eigene Projektmodule → ok
            if top in sys.stdlib_module_names or top in _KNOWN_EXTERNAL:
                continue
            if (self.root / f"{top}.py").exists() or (self.root / top).is_dir():
                continue
            try:
                spec = importlib.util.find_spec(top)
            except (ModuleNotFoundError, ValueError):
                spec = None
            if spec is None:
                report.add(Finding(
                    severity="high",
                    check="imports",
                    location=f"{rel}:{lineno}",
                    message=f"Import '{mod}' nicht auflösbar (Modul nicht installiert/nicht im Projekt)",
                ))

    def _check_complexity(self, rel: str, tree: ast.AST, report: Report) -> None:
        """Heuristik: zu lange Funktionen / zu tiefe Nesting."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno
                if length > 80:
                    report.add(Finding(
                        severity="low",
                        check="complexity",
                        location=f"{rel}:{node.lineno}",
                        message=f"Funktion '{node.name}' ist {length} Zeilen lang (>80 deutet auf zu viel Verantwortung)",
                    ))
                depth = self._max_nesting_depth(node)
                if depth > 5:
                    report.add(Finding(
                        severity="low",
                        check="complexity",
                        location=f"{rel}:{node.lineno}",
                        message=f"Funktion '{node.name}' nested {depth} Level tief (>5 schwer lesbar)",
                    ))

    def _check_security_patterns(self, rel: str, content: str, report: Report) -> None:
        """Regex-basierte Security-Anti-Patterns."""
        for i, line in enumerate(content.splitlines(), start=1):
            # Kommentare grob ignorieren (einfache Heuristik)
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern, severity, msg in _SECURITY_PATTERNS:
                if re.search(pattern, line):
                    report.add(Finding(
                        severity=severity,
                        check="security",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_external_linter(self, rel: str, content: str, report: Report) -> None:
        """Wenn ruff installiert ist: JSON-Diagnostik abgreifen."""
        ruff = shutil.which("ruff")
        if not ruff:
            return  # Soft-Skip — kein optionaler Bug

        try:
            proc = subprocess.run(
                [ruff, "check", "--output-format=json", "--stdin-filename", rel, "-"],
                input=content,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if not proc.stdout.strip():
                return
            try:
                diagnostics = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return

            for diag in diagnostics[:20]:  # Cap: viele Linter-Hits würden überfluten
                code = diag.get("code", "ruff")
                msg = diag.get("message", "")
                loc = diag.get("location", {})
                line = loc.get("row", "?")
                # ruff Severity → unsere Skala
                severity = "medium" if code and code.startswith(("F", "E9")) else "low"
                report.add(Finding(
                    severity=severity,
                    check=f"ruff:{code}",
                    location=f"{rel}:{line}",
                    message=msg,
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return

    def _check_plan_drift(self, plan_text: str, changes: list[dict], report: Report) -> None:
        """Plan nennt Pfade — sind sie auch in den Änderungen?"""
        if not plan_text:
            return

        # Pfade aus Plan extrahieren: "harvest.py", "tests/test_x.py"
        # Erlaubt: alphanumerisch, /, _, -, .
        plan_paths = set(re.findall(
            r"\b([a-z_][\w\-/]*\.(?:py|md|json|yaml|yml|toml|cfg|ini))\b",
            plan_text, re.IGNORECASE,
        ))
        # Pfade die zu allgemein sind (z.B. setup.py, __init__.py) skippen
        plan_paths = {p for p in plan_paths if p not in {
            "setup.py", "__init__.py", "conftest.py", "config.py",
        }}

        changed_files = {Path(c["path"]).name for c in changes}
        # Auch relative Pfade aus dem Projekt einbeziehen
        changed_files |= {self._rel(c["path"]) for c in changes}

        for plan_path in plan_paths:
            # Match by basename or relative path
            basename = Path(plan_path).name
            if basename in changed_files:
                continue
            if any(plan_path in cf for cf in changed_files):
                continue
            report.add(Finding(
                severity="medium",
                check="plan_drift",
                location="<plan>",
                message=f"Plan erwähnt '{plan_path}' — keine entsprechende Änderung in den Files",
            ))

    def _check_loc_sanity(self, plan_text: str, changes: list[dict], report: Report) -> None:
        """Plan schätzt LOC — Realität deutlich darüber?"""
        if not plan_text:
            return
        # Suche nach "150 LOC", "~50 Zeilen", "100 lines"
        match = re.search(
            r"(\d{2,4})\s*(?:LOC|loc|Zeilen|lines)\b",
            plan_text,
        )
        if not match:
            return
        estimated = int(match.group(1))
        actual = sum(len(c["content"].splitlines()) for c in changes)
        if actual > estimated * 3 and actual - estimated > 100:
            report.add(Finding(
                severity="medium",
                check="loc_sanity",
                location="<diff>",
                message=f"Plan schätzte ~{estimated} LOC, tatsächlich {actual} ({actual//estimated}× über) — möglicher Scope-Creep oder Halluzination",
            ))

    def _check_test_existence(self, plan_text: str, changes: list[dict], report: Report) -> None:
        """Plan verspricht Tests — gibt es welche?"""
        if not plan_text:
            return
        # "Tests:", "test_", "pytest", "Testfälle" im Plan?
        plan_mentions_tests = bool(re.search(
            r"\b(test_|tests?:|pytest|Testf(ä|ae)lle?|Unit-Tests?|unittest)\b",
            plan_text, re.IGNORECASE,
        ))
        if not plan_mentions_tests:
            return

        # Definiert irgendein generierter File `test_*` oder eine `def test_*` Funktion?
        has_test_file = any(
            Path(c["path"]).name.startswith("test_") or "/tests/" in c["path"]
            for c in changes
        )
        has_test_func = False
        for c in changes:
            if not c["path"].endswith(".py"):
                continue
            if re.search(r"^\s*def test_\w+\s*\(", c["content"], re.MULTILINE):
                has_test_func = True
                break

        if not (has_test_file or has_test_func):
            report.add(Finding(
                severity="medium",
                check="test_existence",
                location="<diff>",
                message="Plan erwähnt Tests, aber keine test_*-Datei oder def test_*-Funktion in den Änderungen",
            ))

    # ─────────────────────────────────────────────────────────────────────
    # Einzel-Checks (Plan)
    # ─────────────────────────────────────────────────────────────────────

    def _check_plan_structure(self, plan_text: str, plan_kind: str, report: Report) -> None:
        """Hat der Detail-Plan die erwarteten Sektionen?"""
        if plan_kind != "detail":
            return
        required_keywords = {
            "files":    r"\b(Datei|File|Pfad|Path)\b",
            "tests":    r"\b(Test|pytest|unittest)\b",
            "rollback": r"\b(Rollback|revert|undo|zur(ü|ue)ck)\b",
        }
        for label, pattern in required_keywords.items():
            if not re.search(pattern, plan_text, re.IGNORECASE):
                report.add(Finding(
                    severity="low",
                    check="plan_structure",
                    location="<plan>",
                    message=f"Detail-Plan erwähnt nichts zum Bereich '{label}' — möglicherweise zu vage",
                ))

    def _check_plan_specificity(self, plan_text: str, plan_kind: str, report: Report) -> None:
        """Nennt der Plan konkrete Funktions-Signaturen oder Code-Identifier?"""
        if plan_kind != "detail":
            return
        # Heuristik: zumindest ein `funktion(`-artiges Token oder `Class:` ?
        if not re.search(r"\b\w+\s*\([^)]*\)", plan_text):
            report.add(Finding(
                severity="low",
                check="plan_specificity",
                location="<plan>",
                message="Detail-Plan enthält keine konkreten Funktions-Signaturen — zu abstrakt für Code-Gen",
            ))

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _extract_imports(self, tree: ast.AST) -> list[tuple[str, int]]:
        """[(modulname, lineno), ...]"""
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    out.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    out.append((node.module, node.lineno))
        return out

    def _max_nesting_depth(self, func_node: ast.AST, current: int = 0) -> int:
        """Tiefe von if/for/while/with/try-Nesting."""
        nest_types = (ast.If, ast.For, ast.While, ast.With,
                      ast.AsyncFor, ast.AsyncWith, ast.Try)
        max_depth = current
        for child in ast.iter_child_nodes(func_node):
            if isinstance(child, nest_types):
                d = self._max_nesting_depth(child, current + 1)
            else:
                d = self._max_nesting_depth(child, current)
            if d > max_depth:
                max_depth = d
        return max_depth

    def _rel(self, path: str) -> str:
        """Relativen Pfad zum Projekt-Root oder Basename."""
        p = Path(path)
        try:
            return str(p.relative_to(self.root))
        except (ValueError, TypeError):
            return p.name


# ─────────────────────────────────────────────────────────────────────────────
# Self-Test (nur wenn direkt aufgerufen)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    v = StaticValidator()

    # Demo: bewusst kaputter Code
    demo_changes = [{
        "path": str(v.root / "demo_buggy.py"),
        "content": (
            "import nonexistent_module_xyz\n"
            "import os\n"
            "\n"
            "API_KEY = 'sk_live_abcdef1234567890'\n"
            "\n"
            "def fetch(url):\n"
            "    return eval(url)\n"
            "\n"
            "def syntax(\n"
        ),
        "exists": False,
    }]
    demo_plan = """
Files: demo_buggy.py (~30 LOC)
Tests: test_demo.py mit pytest
Rollback: git revert
"""

    print("=== Demo: validate_code mit bewusst kaputtem Code ===")
    rep = v.validate_code(demo_changes, demo_plan)
    print(rep.render())
    print()
    print(f"Verdict: {rep.verdict}, {len(rep.findings)} findings")
