"""
validator2.py — Performance-optimierter deterministischer Code-Validator
=====================================================================

Single-Pass Architektur mit vorkompilierten Pattern-Engines:
  - RegexPatternEngine: Zeilenbasierte Patterns (Security, Best Practice, Performance)
  - UnifiedASTVisitor: Strukturelle Checks in einem AST-Durchlauf
  - Ökosystem-Checks: Git, Config, Docker, Dependencies, Test-Coverage

Public API:
    v = StaticValidatorV2(
        project_root=Path(...),
        disabled_checks={"quality:unused_import"},  # Optional
        severity_overrides={"eval_rce": "critical"}  # Optional
    )
    report = v.validate_code(planned_changes, plan_text) -> Report
    report = v.validate_plan(plan_text, plan_kind="detail") -> Report
    report = v.validate_full(changes, plan_text, context) -> Report
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Findings & Report (vormals static_validator.py — hierher gefaltet)
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
        if "medium" in sevs or "low" in sevs:
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
        for sev_label in ("high", "medium", "low"):
            group = [f for f in self.findings if f.severity == sev_label]
            if not group:
                continue
            icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}[sev_label]
            for f in group:
                loc = f" ({f.location})" if f.location else ""
                lines.append(f"  {icon} [{f.check}]{loc} {f.message}")
        return "\n".join(lines)


@dataclass
class ExtendedReport(Report):
    """Report mit Kategorisierung und Statistik."""

    @property
    def by_category(self) -> dict[str, list[Finding]]:
        """Gruppiert Findings nach Check-Kategorie."""
        categories: dict[str, list[Finding]] = {}
        for f in self.findings:
            cat = f.check.split(":")[0]
            categories.setdefault(cat, []).append(f)
        return categories

    @property
    def stats(self) -> dict[str, int]:
        """Statistiken pro Severity."""
        return {
            "high": len([f for f in self.findings if f.severity == "high"]),
            "medium": len([f for f in self.findings if f.severity == "medium"]),
            "low": len([f for f in self.findings if f.severity == "low"]),
            "total": len(self.findings),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Vorkompilierte Pattern-Engines
# ─────────────────────────────────────────────────────────────────────────────

class RegexPatternEngine:
    """Compiles und führt Regex-Patterns performant aus."""

    def __init__(self, patterns: list[tuple[str, str, str, str]], category_prefix: str):
        # (regex, severity, check_id, message)
        self.compiled_patterns = [
            (re.compile(regex), severity, f"{category_prefix}:{check_id}", check_id, message)
            for regex, severity, check_id, message in patterns
        ]

    def scan_line(self, line: str, lineno: int, rel_path: str, report: ExtendedReport,
                  disabled: set, overrides: dict) -> None:
        """Scannt eine Zeile gegen alle Patterns."""
        for regex, severity, full_check_id, check_id, message in self.compiled_patterns:
            if check_id in disabled or full_check_id in disabled:
                continue

            if regex.search(line):
                final_severity = overrides.get(check_id, severity)
                if final_severity is None:
                    continue

                report.add(Finding(
                    severity=final_severity,
                    check=full_check_id,
                    location=f"{rel_path}:{lineno}",
                    message=message
                ))


# Pattern-Definitionen mit expliziten Check-IDs
_SECURITY_PATTERNS = [
    (r"\beval\s*\(", "high", "eval_rce", "eval() — RCE-Risiko, fast immer vermeidbar"),
    (r"\bexec\s*\(", "high", "exec_rce", "exec() — RCE-Risiko"),
    (r"shell\s*=\s*True", "medium", "subprocess_shell", "subprocess shell=True — Command Injection"),
    (r"pickle\.loads?\s*\(", "medium", "pickle_unsafe", "pickle.load — RCE bei untrusted input"),
    (r"yaml\.load\s*\(\s*[^,)]+\)", "medium", "yaml_unsafe", "yaml.load ohne Loader — nutze yaml.safe_load"),
    (r"\.\./", "low", "path_traversal", "'../' im Code — Pfad-Traversal-Verdacht"),
    (r"(?i)\b(password|secret|api_key|token)\s*=\s*[\"'][A-Za-z0-9_\-]{8,}[\"']", "high", "hardcoded_cred", "hardcoded credential gefunden"),
    (r"verify\s*=\s*False", "medium", "ssl_disabled", "TLS-Verification deaktiviert"),
    (r"input\s*\(.*\)\.*os\.system", "high", "shell_injection", "os.system mit user input — Command Injection"),
    (r"\bcreate_engine\s*\(.*\btrusted\s*=\s*True\b", "high", "sql_trusted", "SQLAlchemy trusted=True — SQL Injection Risiko"),
    (r"\bexecute\s*\(.*\btext\s*=\s*[^)]*\+", "high", "sql_dynamic", "Dynamische SQL-Query-Konstruktion"),
    (r'\bcursor\.execute\s*\(.*f"[^"]*\{[^}]*\}[^"]*"', "high", "sql_fstring", "f-String in SQL-Query — SQL Injection Risiko"),
    (r'\bformat\s*\(.*"[^"]*SELECT[^"]*"', "medium", "sql_format", "format() für SQL-Query"),
    (r"\bboto3\.client\s*\(.*aws_access_key_id\s*=", "high", "aws_cred", "AWS Credentials hardcoded"),
    (r'\bprivate_key\s*=\s*[\"\'].*-----BEGIN[^-]+-----', "high", "key_hardcoded", "Private Key hardcoded"),
    (r"\bCORS\s*\(.*allow_origins\s*=\s*\*", "medium", "cors_open", "CORS allow_origins='*' — zu permissiv"),
    (r"\bdebug\s*=\s*True", "low", "debug_on", "Debug-Modus aktiviert — deaktiviere für Produktion"),
    (r"\btempfile\.mktemp\s*\(", "medium", "tempfile_race", "tempfile.mktemp() — Race Condition Risiko"),
    (r"\bchmod\s*\(.*0o?777", "medium", "chmod_777", "chmod 777 — zu permissiv"),
    (r"\bos\.chmod\s*\(.*0o?777", "medium", "os_chmod_777", "os.chmod 777 — zu permissiv"),
    (r"\blxml\.etree\.parse\s*\(.*resolve_entities\s*=\s*True", "high", "xxe", "XML External Entity Processing — XXE"),
    (r"\bdisable_ssl\s*=\s*True", "medium", "ssl_disable_var", "SSL/TLS deaktiviert"),
    (r"\binsecure\s*=\s*True", "medium", "insecure_flag", "Insecure-Modus aktiviert"),
]

_BEST_PRACTICE_PATTERNS = [
    (r"^\s*except\s*:", "high", "bare_except", "bare except: — fängt alle Exceptions ab"),
    (r"^\s*except\s*Exception\s*:", "medium", "generic_except", "except Exception: — fängt zu allgemein ab"),
    (r"\bprint\s*\(", "low", "print_stmt", "print() statement — nutze Logger für Produktion"),
    (r"\b\d{3,}\b", "low", "magic_number", "Magic Number (>2 Zeichen) — nutze Named Constants"),
    (r"TODO|FIXME|XXX|HACK", "low", "technical_debt", "Technische Schuld offen (TODO/FIXME)"),
    (r"\bpass\s*$", "low", "dead_code", "pass statement — Möglicher toter Code"),
    (r"\bglobal\s+\w+", "medium", "global_state", "global statement — vermeide globale State-Mutation"),
    (r"\bassert\s+", "low", "assert_stmt", "assert statement — wird mit -O wegoptimiert"),
    (r"\bfrom\s+\w+\s+import\s+\*", "medium", "wildcard_import", "Wildcard Import — explizite Imports bevorzugen"),
]

_PERFORMANCE_PATTERNS = [
    (r"\bfor\s+\w+\s+in\s+range\(len\(", "medium", "range_len", "range(len()) Iteration — nutze enumerate()"),
    (r"\blist\(.*\bmap\s*\(", "medium", "list_map", "list(map()) — nutze List Comprehension"),
    (r"\blist\(.*\bfilter\s*\(", "medium", "list_filter", "list(filter()) — nutze List Comprehension"),
    (r"\bjson\.loads\s*\(.*\bread\(\)", "medium", "json_mem", "json.loads(read()) — lädt gesamtes File in Memory"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Unified AST Engine
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedASTVisitor(ast.NodeVisitor):
    """Single-Pass AST Traversal für strukturelle Checks."""

    def __init__(self, rel_path: str, report: ExtendedReport, disabled: set, overrides: dict):
        self.rel_path = rel_path
        self.report = report
        self.disabled = disabled
        self.overrides = overrides
        self.imported_names: dict[str, int] = {}
        self.used_names: set[str] = set()
        self._context_stack: list[ast.AST] = []

    def visit(self, node: ast.AST) -> None:
        is_loop = isinstance(node, (ast.For, ast.While, ast.AsyncFor))
        if is_loop:
            self._context_stack.append(node)
        super().visit(node)
        if is_loop:
            self._context_stack.pop()

    def _in_loop(self) -> bool:
        return len(self._context_stack) > 0

    def _add_finding(self, severity: str, check_id: str, location: str, message: str) -> None:
        if check_id in self.disabled:
            return
        severity = self.overrides.get(check_id, severity)
        if severity is None:
            return
        self.report.add(Finding(severity, check_id, location, message))

    def visit_Module(self, node: ast.Module) -> None:
        if not (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant)):
            self._add_finding("medium", "docstring:module", self.rel_path,
                "Modul hat keinen Docstring — Modul-Zweck ist unklar.")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._validate_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant)):
            if not node.name.startswith("_"):
                self._add_finding("medium", "docstring:class", f"{self.rel_path}:{node.lineno}",
                    f"Klasse '{node.name}' hat keinen Docstring.")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imported_names[name] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imported_names[name] = node.lineno
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_loop():
            if isinstance(node.func, ast.Attribute) and node.func.attr == "save":
                self._add_finding("medium", "performance:loop_save", f"{self.rel_path}:{node.lineno}",
                    "ORM .save() in Schleife erkannt. Nutze bulk_create() oder batch-Updates.")

            if isinstance(node.func, ast.Attribute) and node.func.attr in ("query", "execute", "filter", "get"):
                self._add_finding("high", "performance:n_plus_one", f"{self.rel_path}:{node.lineno}",
                    f"Potenzielle Datenbankabfrage (.{node.func.attr}) in Schleife. N+1 Problem vermeiden!")
        self.generic_visit(node)

    def _validate_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        has_return = node.returns is not None
        has_args = any(arg.annotation is not None for arg in node.args.args if arg.arg != "self")

        if not has_return and not has_args and not node.name.startswith("_"):
            self._add_finding("medium", "quality:type_hints", f"{self.rel_path}:{node.lineno}",
                f"Funktion '{node.name}' hat weder Argument- noch Return-Typ-Annotations.")

        if not (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant)):
            if not node.name.startswith("_"):
                self._add_finding("low", "docstring:function", f"{self.rel_path}:{node.lineno}",
                    f"Öffentliche Funktion '{node.name}' besitzt keinen Docstring.")

    def check_unused_imports(self) -> None:
        for name, lineno in self.imported_names.items():
            if name not in self.used_names:
                self._add_finding("low", "quality:unused_import", f"{self.rel_path}:{lineno}",
                    f"Unbenutzter Import '{name}' sollte entfernt werden.")


# ─────────────────────────────────────────────────────────────────────────────
# Hauptklasse StaticValidatorV2
# ─────────────────────────────────────────────────────────────────────────────

class StaticValidatorV2:
    """Performance-optimierter deterministischer Validator mit Konfigurierbarkeit.

    Self-contained — alle Code- und Plan-Checks sind hier definiert (vormals
    teilweise in static_validator.py, jetzt zusammengeführt).
    """

    def __init__(self, project_root: Path | None = None,
                 disabled_checks: set | None = None,
                 severity_overrides: dict | None = None):
        self.root = (project_root or Path(__file__).parent).resolve()

        self.disabled_checks = disabled_checks or set()
        self.severity_overrides = severity_overrides or {}

        # Vorkompilierte Pattern-Engines
        self.security_engine = RegexPatternEngine(_SECURITY_PATTERNS, "security")
        self.best_practice_engine = RegexPatternEngine(_BEST_PRACTICE_PATTERNS, "quality")
        self.performance_engine = RegexPatternEngine(_PERFORMANCE_PATTERNS, "performance")

    def _rel(self, path: str) -> str:
        """Relativen Pfad zum Projekt-Root oder Basename."""
        p = Path(path)
        try:
            return str(p.relative_to(self.root))
        except (ValueError, TypeError):
            return p.name

    def validate_code(self, planned_changes: list[dict], plan_text: str = "") -> ExtendedReport:
        """Validiert Code-Änderungen."""
        report = ExtendedReport()

        for change in planned_changes:
            path_str = change["path"]
            content = change["content"]
            rel = self._rel(path_str)

            if not path_str.endswith(".py"):
                self._check_file_general(rel, content, path_str, report)
                continue

            # --- SINGLE PASS: Zeilen ---
            lines = content.splitlines()
            for idx, line in enumerate(lines, 1):
                if len(line) > 120:
                    self._add_finding(report, "low", "quality:line_length", f"{rel}:{idx}",
                        f"Zeilenlänge überschreitet Limit ({len(line)} > 120 Zeichen).")

                self.security_engine.scan_line(line, idx, rel, report, self.disabled_checks, self.severity_overrides)
                self.best_practice_engine.scan_line(line, idx, rel, report, self.disabled_checks, self.severity_overrides)
                self.performance_engine.scan_line(line, idx, rel, report, self.disabled_checks, self.severity_overrides)

            # --- SINGLE PASS: AST ---
            tree = self._check_syntax(rel, content, report)
            if tree is not None:
                visitor = UnifiedASTVisitor(rel, report, self.disabled_checks, self.severity_overrides)
                visitor.visit(tree)
                visitor.check_unused_imports()

            self._check_file_encoding(rel, content, report)

        # --- Cross-File Checks ---
        self._track_imports_across_files(planned_changes, report)
        self._check_test_coverage(planned_changes, report)
        self._check_dependencies(planned_changes, report)
        self._check_git_issues(planned_changes, report)
        self._check_config_files(planned_changes, report)
        self._check_docker_files(planned_changes, report)

        # --- Plan Checks ---
        if plan_text:
            self._check_plan_drift(plan_text, planned_changes, report)
            self._check_loc_sanity(plan_text, planned_changes, report)
            self._check_test_existence(plan_text, planned_changes, report)

        return report

    def validate_plan(self, plan_text: str, plan_kind: str = "detail") -> ExtendedReport:
        """Validiert Plan-Struktur + Datei-Existenz (Anti-Halluzination)."""
        report = ExtendedReport()
        self._check_plan_structure(plan_text, plan_kind, report)
        self._check_plan_specificity(plan_text, plan_kind, report)
        self._check_plan_file_existence(plan_text, report)
        return report

    def _check_plan_file_existence(self, plan: str, report: ExtendedReport) -> None:
        """Findet Dateinamen die der Plan als 'BETROFFENE DATEIEN' deklariert,
        aber die im Projekt nicht existieren — typische Halluzination.

        Heuristik:
          1. Section ab "BETROFFENE DATEIEN" / "AFFECTED FILES" suchen
          2. Bis zur nächsten Section (NEUE DATEIEN, FUNKTIONEN, etc.) lesen
          3. Alle *.py / *.md / *.toml etc. Dateinamen extrahieren
          4. Existenz gegen self.root prüfen
        """
        import re as regex_module

        # Section "BETROFFENE DATEIEN" extrahieren
        # Stoppt bei nächstem Section-Header (NEUE/FUNKTIONEN/CODE-FLOW/TESTS/IMPORTS/...)
        section_pattern = regex_module.compile(
            r"(?:BETROFFENE\s+DATEIEN|AFFECTED\s+FILES|MODIFIED\s+FILES)"
            r"(.*?)"
            r"(?=\n\s*(?:\d+\.\s+)?(?:NEUE\s+DATEIEN|NEW\s+FILES|FUNKTIONEN|FUNCTIONS|"
            r"CODE-?FLOW|TESTS|IMPORTS|INTEGRATION|ROLLBACK|ESTIMATED|####|###|\Z))",
            regex_module.IGNORECASE | regex_module.DOTALL,
        )
        match = section_pattern.search(plan)
        if not match:
            return

        section = match.group(1)

        # Dateinamen extrahieren: *.py, *.md, *.toml, *.json, *.yml, *.yaml
        # Akzeptiert: **file.py**, `file.py`, file.py, path/to/file.py
        file_pattern = regex_module.compile(
            r"(?:[\*\`/\s]|^)([a-zA-Z_][\w/\-\.]*\.(?:py|md|toml|json|yml|yaml|cfg|ini|txt))"
            r"(?:[\*\`\s:,\)]|$)",
            regex_module.MULTILINE,
        )

        seen: set[str] = set()
        for fmatch in file_pattern.finditer(section):
            fname = fmatch.group(1).strip()
            if fname in seen:
                continue
            seen.add(fname)

            # Prüfen ob die Datei (relativ zum Projekt-Root) existiert
            path = self.root / fname
            if path.exists():
                continue

            # Auch im Tree suchen (rekursiv, aber nur Filename matchen)
            base = fname.split("/")[-1]
            matches = list(self.root.rglob(base))
            if matches:
                continue

            # Datei existiert nicht — Halluzination!
            self._add_finding(
                report,
                "high",
                "plan:hallucinated_file",
                "<plan>",
                f"Plan referenziert Datei '{fname}' als BETROFFENE DATEI, aber sie existiert nicht im Projekt"
            )

    def validate_full(self, changes: list[dict], plan_text: str, context: dict | None = None) -> ExtendedReport:
        """Kombiniert Code- + Plan-Validierung."""
        # Layer 1: Code-Validierung
        report = self.validate_code(changes, plan_text)

        # Layer 2: Plan-Validierung
        plan_report = self.validate_plan(plan_text)
        report.add(*plan_report.findings)

        return report

    def _add_finding(self, report: ExtendedReport, severity: str, check_id: str, location: str, message: str) -> None:
        """Helper für Findings mit Config-Anwendung."""
        if check_id in self.disabled_checks:
            return
        severity = self.severity_overrides.get(check_id, severity)
        if severity is None:
            return
        report.add(Finding(severity, check_id, location, message))

    # ─────────────────────────────────────────────────────────────────────
    # Cross-File Analyse
    # ─────────────────────────────────────────────────────────────────────

    def _track_imports_across_files(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Erkennt zirkuläre Imports."""
        # Baue Abhängigkeitsgraph
        imports_by_file: dict[str, set[str]] = {}

        for change in planned_changes:
            if not change["path"].endswith(".py"):
                continue

            try:
                tree = ast.parse(change["content"])
                imports = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.add(node.module.split(".")[0])

                rel_path = Path(change["path"]).stem
                imports_by_file[rel_path] = imports
            except Exception:
                pass

        # Suche nach Zyklen (vereinfachte DFS)
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str, path: list[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in imports_by_file.get(node, set()):
                if neighbor not in visited:
                    if has_cycle(neighbor, path + [node]):
                        return True
                elif neighbor in rec_stack:
                    cycle_path = " → ".join(path + [node, neighbor])
                    self._add_finding(report, "high", "circular_import", "",
                        f"Circular import chain: {cycle_path}")
                    return True

            rec_stack.discard(node)
            return False

        for node in imports_by_file:
            if node not in visited:
                has_cycle(node, [])

    def _check_test_coverage(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Prüft ob neue Funktionen Tests haben."""
        new_functions: dict[str, set[str]] = {}  # file -> set of function names
        test_functions: set[str] = set()

        for change in planned_changes:
            if not change["path"].endswith(".py"):
                continue

            try:
                tree = ast.parse(change["content"])
                functions = {node.name for node in ast.walk(tree)
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

                is_test_file = "test_" in change["path"] or "_test.py" in change["path"]

                if is_test_file:
                    test_functions.update(functions)
                else:
                    new_functions[change["path"]] = functions
            except Exception:
                pass

        # Check Coverage
        for file_path, functions in new_functions.items():
            untested = 0
            for func in functions:
                if not any(f"test_{func}" in tf or f"{func.title()}Test" in tf for tf in test_functions):
                    untested += 1

            if untested > 0 and len(functions) > 0:
                coverage = (len(functions) - untested) / len(functions) * 100
                self._add_finding(report, "low", "test_coverage", file_path,
                    f"Test Coverage: {int(coverage)}% ({untested} Functions ohne entsprechende Tests)")

    def _check_dependencies(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Prüft requirements.txt auf unpinned versions."""
        for change in planned_changes:
            if "requirements.txt" not in change["path"]:
                continue

            for idx, line in enumerate(change["content"].splitlines(), 1):
                if line.strip() and not line.startswith("#"):
                    if ">=" in line or "~=" in line or (("==" not in line) and ("@" not in line)):
                        self._add_finding(report, "medium", "dependencies:unpinned", f"{change['path']}:{idx}",
                            f"Dependency nicht exakt fixiert: '{line.strip()}'. Nutze '==' zur Absicherung.")

    def _check_git_issues(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Prüft auf sensible Dateien ohne .gitignore."""
        sensitive_patterns = [".env", "secrets/", "private_key", ".aws/credentials", ".ssh/"]

        for change in planned_changes:
            if any(pat in change["path"] for pat in sensitive_patterns):
                self._add_finding(report, "high", "security:git_exposure", change["path"],
                    "Sensible Datei — stelle sicher, dass .gitignore-Regel existiert")

    def _check_config_files(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Prüft YAML/JSON/TOML auf Syntax und Secrets."""
        for change in planned_changes:
            if change["path"].endswith((".yaml", ".yml", ".json", ".toml")):
                if "password" in change["content"].lower() or "secret" in change["content"].lower():
                    self._add_finding(report, "medium", "config:hardcoded_secret", change["path"],
                        "Mögliches Hardcoded Secret in Config-File erkannt")

    def _check_docker_files(self, planned_changes: list[dict], report: ExtendedReport) -> None:
        """Prüft Dockerfiles auf Best Practices."""
        for change in planned_changes:
            if "Dockerfile" in change["path"]:
                if ":latest" in change["content"]:
                    self._add_finding(report, "medium", "docker:latest_tag", change["path"],
                        "Docker :latest tag — spezifische Version verwenden")

                if "USER root" in change["content"] or "USER 0" in change["content"]:
                    self._add_finding(report, "high", "docker:root_user", change["path"],
                        "Docker Container läuft als root — nicht-root User verwenden")

    # ─────────────────────────────────────────────────────────────────────
    # Dateibasierte Checks
    # ─────────────────────────────────────────────────────────────────────

    def _check_file_encoding(self, rel: str, content: str, report: ExtendedReport) -> None:
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            self._add_finding(report, "medium", "quality:encoding", rel,
                "Datei enthält ungültige Nicht-UTF-8-Zeichen.")

    def _check_file_general(self, rel: str, content: str, path_str: str, report: ExtendedReport) -> None:
        """Allgemeine Datei-Checks (Placeholder für base class)."""
        pass

    # ─────────────────────────────────────────────────────────────────────
    # Plan-Checks (Placeholder - Base Implementation)
    # ─────────────────────────────────────────────────────────────────────

    def _check_plan_structure(self, plan: str, kind: str, report: ExtendedReport) -> None:
        if kind == "detail":
            keywords = ["Datei", "File", "Test", "pytest", "Rollback"]
            if not any(kw in plan for kw in keywords):
                self._add_finding(report, "medium", "plan:structure", "",
                    "Detail-Plan hat ungenügende Struktur — Dateien, Tests, Rollback-Plan erforderlich")

    def _check_plan_specificity(self, plan: str, kind: str, report: ExtendedReport) -> None:
        import re as regex_module
        # Suche nach Funktions-Signaturen
        if not regex_module.search(r"\w+\s*\([^)]*\)", plan):
            self._add_finding(report, "medium", "plan:specificity", "",
                "Plan enthält keine konkreten Funktions-Signaturen — zu vage")

    def _check_plan_drift(self, plan: str, changes: list[dict], report: ExtendedReport) -> None:
        """Basis-Stub — überschreiben wenn nötig."""
        pass

    def _check_loc_sanity(self, plan: str, changes: list[dict], report: ExtendedReport) -> None:
        """Basis-Stub — überschreiben wenn nötig."""
        pass

    def _check_test_existence(self, plan: str, changes: list[dict], report: ExtendedReport) -> None:
        """Basis-Stub — überschreiben wenn nötig."""
        pass

    def _check_syntax(self, rel: str, content: str, report: ExtendedReport) -> ast.AST | None:
        """Parst Python und gibt AST zurück."""
        try:
            return ast.parse(content, filename=rel)
        except SyntaxError as e:
            self._add_finding(report, "high", "syntax:error", f"{rel}:{e.lineno}",
                f"SyntaxError: {e.msg}")
            return None
        except Exception as e:
            self._add_finding(report, "high", "syntax:parse_error", rel,
                f"Parse Error: {str(e)}")
            return None
