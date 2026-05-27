"""
static_validator_v2.py — Erweiterter deterministischer Validator
======================================================================

Erweitert static_validator.py mit umfassenderen Checks ohne LLM:
- Erbt alle Checks von StaticValidator
- Fügt hinzu: Type-Hints, Docstrings, Best Practices, Performance, 
  Dependency-Checks, Config-Validierung, Git-Checks, Docker-Checks

Public API:
    StaticValidatorV2().validate_code(planned_changes, plan_text) -> Report
    StaticValidatorV2().validate_plan(plan_text, plan_kind="detail") -> Report
    StaticValidatorV2().validate_full(changes, plan_text, context) -> Report

Konsumiert von workflow_agent.py als Drop-in-Replacement oder zusätzlich.
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

# Import basisklasse
from static_validator import StaticValidator, Report, Finding


# ─────────────────────────────────────────────────────────────────────────────
# Erweiterte Datenmodelle
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtendedReport(Report):
    """Erweiterter Report mit Kategorisierung."""
    
    @property
    def by_category(self) -> dict[str, list[Finding]]:
        """Gruppiert Findings nach Check-Kategorie."""
        categories = {}
        for f in self.findings:
            cat = f.check.split(":")[0]  # "security" aus "security:eval"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f)
        return categories
    
    @property
    def stats(self) -> dict[str, int]:
        """Statistik pro Severity."""
        return {
            "high": len([f for f in self.findings if f.severity == "high"]),
            "medium": len([f for f in self.findings if f.severity == "medium"]),
            "low": len([f for f in self.findings if f.severity == "low"]),
            "total": len(self.findings),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Erweiterte Patterns
# ─────────────────────────────────────────────────────────────────────────────

# Security-Patterns (erweitert) - kombiniert originale und neue
_EXTENDED_SECURITY_PATTERNS = [
    # Original patterns aus StaticValidator
    (r"\beval\s*\(", "high", "eval() — RCE-Risiko, fast immer vermeidbar"),
    (r"\bexec\s*\(", "high", "exec() — RCE-Risiko"),
    (r"shell\s*=\s*True", "medium", "subprocess shell=True — Command Injection wenn Input nicht kontrolliert"),
    (r"pickle\.loads?\s*\(", "medium", "pickle.load — RCE bei untrusted input"),
    (r"yaml\.load\s*\(\s*[^,)]+\)", "medium", "yaml.load ohne Loader — nutze yaml.safe_load"),
    (r"\.\./", "low", "'../' im Code — Pfad-Traversal-Verdacht"),
    (r"(?i)\b(password|secret|api_key|token)\s*=\s*[\"'][A-Za-z0-9_\-]{8,}[\"']", "high",
     "hardcoded credential — gehört in env/secret-store, nicht in Code"),
    (r"verify\s*=\s*False", "medium", "TLS-Verification deaktiviert"),
    (r"input\s*\(.*\)\.*os\.system", "high", "os.system mit user input — Command Injection"),
    
    # Neue Security-Patterns
    (r"\bcreate_engine\s*\(.*\btrusted\s*=\s*True\b", "high", 
     "SQLAlchemy trusted=True — SQL Injection Risiko"),
    (r"\bexecute\s*\(.*\btext\s*=\s*[^)]*\+", "high", 
     "Dynamische SQL-Query-Konstruktion — SQL Injection Risiko"),
    (r'\bcursor\.execute\s*\(.*f"[^"]*\{[^}]*\}[^"]*"', "high", 
     "f-String in SQL-Query — SQL Injection Risiko"),
    (r'\bformat\s*\(.*"[^"]*SELECT[^"]*"', "medium", 
     "format() für SQL-Query — SQL Injection Risiko"),
    (r"\bboto3\.client\s*\(.*aws_access_key_id\s*=", "high", 
     "AWS Credentials hardcoded — nutze IAM Roles oder Environment"),
    (r'\bprivate_key\s*=\s*[\"\'].*-----BEGIN[^-]+-----', "high", 
     "Private Key hardcoded — gehört in sicheres Secret-Store"),
    (r"\bCORS\s*\(.*allow_origins\s*=\s*\*", "medium", 
     "CORS allow_origins='*' — zu permissiv für Produktion"),
    (r"\bdebug\s*=\s*True", "low", "Debug-Modus aktiviert — deaktiviere für Produktion"),
    (r"\btempfile\.mktemp\s*\(", "medium", 
     "tempfile.mktemp() — Race Condition Risiko, nutze mkstemp() oder NamedTemporaryFile"),
    (r"\bchmod\s*\(.*0o?777", "medium", "chmod 777 — zu permissiv, nutze 755 oder 644"),
    (r"\bos\.chmod\s*\(.*0o?777", "medium", "os.chmod 777 — zu permissiv"),
    (r"\blxml\.etree\.parse\s*\(.*resolve_entities\s*=\s*True", "high", 
     "XML External Entity Processing — XXE-Risiko"),
    (r"\bdisable_ssl\s*=\s*True", "medium", "SSL/TLS deaktiviert"),
    (r"\binsecure\s*=\s*True", "medium", "Insecure-Modus aktiviert"),
]

# Best Practice Patterns
_BEST_PRACTICE_PATTERNS = [
    (r"^\s*except\s*:", "high", "bare except: — fängt alle Exceptions inkl. KeyboardInterrupt, SystemExit"),
    (r"^\s*except\s*Exception\s*:", "medium", "except Exception: — fängt zu allgemein, nutze spezifische Exceptions"),
    (r"\bprint\s*\(", "low", "print() statement — nutze Logger für Produktion-Code"),
    (r"^\s*def\s+\w+\(\s*\)\s*:", "low", "Funktion ohne Typ-Hints — Type-Hints verbessern Code-Qualität"),
    (r"\blambda\s+.*", "low", "Lambda — prüfe ob Typ-Hints möglich"),
    (r"\b\d{3,}\b", "low", "Magic Number (>2 Zeichen) — nutze Named Constants"),
    (r"\b[0-9]{4,}\b", "low", "Magic Number (>=4 digits) — nutze Named Constants"),
    (r"TODO|FIXME|XXX|HACK", "low", "TODO/FIXME Kommentar — technische Schuld markieren"),
    (r"\bpass\s*$", "low", "pass statement — möglicherweise Dead Code oder unvollständige Implementierung"),
    (r"^\s*if\s+.*:\s*pass\s*$", "low", "if-Block mit nur pass — nutze Guard Clauses oder entferne"),
    (r"\bglobal\s+\w+", "medium", "global statement — vermeide globale State-Mutation"),
    (r"\bnonlocal\s+\w+", "low", "nonlocal statement — kann Code schwer lesbar machen"),
    (r"\bdel\s+\w+", "low", "del statement — selten notwendig, kann Debugging erschweren"),
    (r"\bassert\s+", "low", "assert statement — wird mit -O optimiert, nutze Exceptions für Produktion"),
    (r"\b\.\s*import\s*\*", "medium", "Wildcard Import — explizite Imports bevorzugen"),
    (r"\bfrom\s+\w+\s+import\s+\*", "medium", "Wildcard Import — explizite Imports bevorzugen"),
    (r"\bmutate\s*=\s*True", "medium", "Pydantic mutate=True — Sicherheitsrisiko, deaktiviere"),
    (r"\bargh\s*=\s*False", "medium", "FastAPI argh=False — deaktiviere für Produktion"),
]

# Performance Patterns
_PERFORMANCE_PATTERNS = [
    (r"\bfor\s+\w+\s+in\s+range\(len\(", "medium", 
     "range(len()) Iteration — nutze enumerate() für bessere Lesbarkeit und Performance"),
    (r"\bfor\s+\w+\s+in\s+\w+\s*:", "low", 
     "Iteration ohne xrange/range — für große Listen: nutze Generator Expressions"),
    (r"\blist\(.*\bmap\s*\(", "medium", 
     "list(map()) — nutze List Comprehension für bessere Lesbarkeit"),
    (r"\blist\(.*\bfilter\s*\(", "medium", 
     "list(filter()) — nutze List Comprehension für bessere Lesbarkeit"),
    (r"\b\.keys\(\)\s*\+", "low", "dict.keys() + list — O(n) Operation, nutze Set-Operationen"),
    (r"\b\.values\(\)\s*\+", "low", "dict.values() + list — O(n) Operation"),
    (r"\bfor\s+\w+\s+in\s+\w+\s*:\s*\w+\.append\s*\(", "medium", 
     "List append in Loop — nutze List Comprehension"),
    (r"\bwhile\s+True\s*:", "low", "while True — möglicherweise Endlosschleife, nutzeTimeout oder Bedingung"),
    (r"\bsleep\s*\(\s*[0-9]+\s*\)", "low", "sleep() in kritischem Pfad — Blocking Call, nutze async"),
    (r"\btime\.sleep\s*\(", "low", "time.sleep() — Blocking Call, nutze asyncio.sleep() für async Code"),
    (r"\bjson\.loads\s*\(.*\bread\(\)", "medium", 
     "json.loads(read()) — liest gesamte Datei in Memory, nutze Streaming für große Files"),
    (r"\b\.read\(\)\s*\+", "low", "read() + String Concatenation — ineffizient für große Dateien"),
    (r"\bN\s*\+\s*1\s+loop", "medium", "N+1 Query Pattern — nutze Batch-Operationen oder JOINs"),
    (r"\bfor\s+.*\sin\s+.*\s*:\s*.*\bquery\s*\(", "medium", 
     "Query in Loop — N+1 Problem, nutze Bulk-Operationen"),
    (r"\b\.save\(\)", "low", "ORM .save() in Loop — nutze bulk_create() oder batch-Operationen"),
]

# Test Patterns
_TEST_PATTERNS = [
    (r"\bdef\s+test_\w+", "high", "Test Funktion gefunden"),
    (r"\bdef\s+test_.*\bskip\b", "medium", "Test mit skip — prüfe ob absichtlich"),
    (r"\b@pytest\.mark\.skip", "medium", "Test mit skip-Marker"),
    (r"\b@pytest\.mark\.xfail", "low", "Test mit xfail-Marker"),
    (r"\bassert\s+True", "high", "assert True — sinnloser Test, entferne"),
    (r"\bassert\s+\d+\s*[=!]=\s*\d+", "low", "assert mit Magic Numbers — nutze Named Constants"),
    (r"\bassert\s+[^=]+\s*==\s*[^=]+", "low", "assert == — nutze pytest's assert Ausdruck für bessere Fehler-meldungen"),
    (r"\bself\.fail\s*\(", "medium", "self.fail() — veraltet, nutze pytest's assert oder raise"),
    (r"\bunittest\.TestCase", "medium", "unittest.TestCase — nutze pytest für bessere Syntax"),
    (r"\b@patch", "low", "Mocking mit @patch — prüfe ob notwendig oder zu viel Mocking"),
    (r"\bsleep\s*\(\s*[0-9]+", "low", "sleep() in Test — nutze pytest's Monkeypatch oder Mock"),
    (r"\btime\.sleep\s*\(", "low", "time.sleep() in Test — langsam, nutze Mock"),
]


class StaticValidatorV2(StaticValidator):
    """Erweiterter deterministischer Code- und Plan-Validator mit umfassenden Checks."""

    def __init__(self, project_root: Path | None = None):
        super().__init__(project_root)
        self.root = (project_root or Path(__file__).parent).resolve()

    # ─── Code-Validierung (erweitert) ────────────────────────────────────────

    def validate_code(self, planned_changes: list[dict], plan_text: str = "") -> ExtendedReport:
        """Hauptcheck für die EXECUTION-Phase mit erweiterten Checks.
        
        planned_changes: aus workflow_agent._parse_code() ->
            [{"path": str, "content": str, "exists": bool}, ...]
        plan_text: der genehmigte Detail-Plan (für Drift-Check)
        """
        report = ExtendedReport()

        for change in planned_changes:
            path = change["path"]
            content = change["content"]
            rel = self._rel(path)

            # Basis-Checks vom Parent
            if not path.endswith(".py"):
                # Non-Python files: andere Checks
                self._check_file_general(rel, content, path, report)
                continue

            tree = self._check_syntax(rel, content, report)
            if tree is not None:
                # Erweitert: Type-Hints Check
                self._check_type_hints(rel, tree, content, report)
                # Erweitert: Docstrings Check
                self._check_docstrings(rel, tree, report)
                # Basis
                self._check_imports(rel, tree, report)
                self._check_complexity(rel, tree, report)
                # Erweitert: Unused Imports
                self._check_unused_imports(rel, tree, content, report)
                # Erweitert: Circular Imports
                self._check_circular_imports(rel, tree, report)

            # Security: nur erweiterte Checks (enthält alle originalen + neue)
            self._check_extended_security(rel, content, report)
            # Erweitert: Best Practices
            self._check_best_practices(rel, content, report)
            # Erweitert: Performance
            self._check_performance(rel, content, report)
            # Basis
            self._check_external_linter(rel, content, report)
            
            # Datei-spezifische Checks
            self._check_file_encoding(rel, content, report)
            self._check_line_length(rel, content, report)

        # Cross-File Checks
        self._check_plan_drift(plan_text, planned_changes, report)
        self._check_loc_sanity(plan_text, planned_changes, report)
        self._check_test_existence(plan_text, planned_changes, report)
        
        # Erweitert: Dependency Checks
        self._check_dependencies(planned_changes, report)
        
        # Erweitert: Git Checks
        self._check_git_issues(planned_changes, report)
        
        # Erweitert: Config Files Validation
        self._check_config_files(planned_changes, report)
        
        # Erweitert: Docker Checks
        self._check_docker_files(planned_changes, report)

        return report

    def validate_plan(self, plan_text: str, plan_kind: str = "detail") -> ExtendedReport:
        """Hauptcheck für Plan-Phasen mit erweiterten Checks."""
        report = ExtendedReport()
        # Basis-Checks
        self._check_plan_structure(plan_text, plan_kind, report)
        self._check_plan_specificity(plan_text, plan_kind, report)
        # Erweitert
        self._check_plan_completeness(plan_text, plan_kind, report)
        self._check_plan_consistency(plan_text, plan_kind, report)
        return report

    def validate_full(self, changes: list[dict], plan_text: str, context: dict = None) -> ExtendedReport:
        """Vollständige Validierung inkl. Kontext-Checks."""
        report = self.validate_code(changes, plan_text)
        if context:
            self._check_context_consistency(changes, plan_text, context, report)
        return report

    # ─────────────────────────────────────────────────────────────────────
    # Erweiterte Einzel-Checks (Code)
    # ─────────────────────────────────────────────────────────────────────

    def _check_type_hints(self, rel: str, tree: ast.AST, content: str, report: ExtendedReport) -> None:
        """Prüft Type-Hints auf Funktionen und Methoden."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Prüfe ob Funktion Type-Hints hat
                has_return_annotation = node.returns is not None
                has_arg_annotations = any(arg.annotation is not None for arg in node.args.args)
                
                if not has_return_annotation and not has_arg_annotations:
                    report.add(Finding(
                        severity="medium",
                        check="type_hints",
                        location=f"{rel}:{node.lineno}",
                        message=f"Funktion '{node.name}' hat keine Type-Hints — Type-Hints verbessern Code-Qualität und IDE-Support",
                    ))
                elif not has_return_annotation:
                    report.add(Finding(
                        severity="low",
                        check="type_hints",
                        location=f"{rel}:{node.lineno}",
                        message=f"Funktion '{node.name}' hat keine Return-Type-Annotation",
                    ))
                
                # Prüfe auf Any-Typen (schlechte Praxis)
                for arg in node.args.args:
                    if arg.annotation is not None:
                        if self._is_any_type(arg.annotation):
                            report.add(Finding(
                                severity="low",
                                check="type_hints",
                                location=f"{rel}:{node.lineno}",
                                message=f"Funktion '{node.name}' hat Any-Type für Argument '{arg.arg}' — präzisere Typen bevorzugen",
                            ))
                
                if node.returns is not None and self._is_any_type(node.returns):
                    report.add(Finding(
                        severity="low",
                        check="type_hints",
                        location=f"{rel}:{node.lineno}",
                        message=f"Funktion '{node.name}' hat Any als Return-Type — präzisere Typen bevorzugen",
                    ))

    def _is_any_type(self, annotation: ast.AST) -> bool:
        """Prüft ob Annotation 'Any' oder 'typing.Any' ist."""
        if isinstance(annotation, ast.Name):
            return annotation.id == "Any"
        elif isinstance(annotation, ast.Attribute):
            if annotation.attr == "Any":
                if isinstance(annotation.value, ast.Name):
                    return annotation.value.id == "typing"
        elif isinstance(annotation, ast.Subscript):
            # Any[...] oder Union[..., Any] etc.
            if isinstance(annotation.value, ast.Name) and annotation.value.id == "Any":
                return True
        return False

    def _check_docstrings(self, rel: str, tree: ast.AST, report: ExtendedReport) -> None:
        """Prüft auf Docstrings in Modulen, Klassen und Funktionen."""
        has_module_docstring = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Module):
                # Modul-Docstring
                if (node.body and isinstance(node.body[0], ast.Expr) and 
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    has_module_docstring = True
            
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                # Klassen- und Funktions-Docstrings
                name = node.name
                node_type = "Klasse" if isinstance(node, ast.ClassDef) else "Funktion"
                
                if node.body and isinstance(node.body[0], ast.Expr) and \
                   isinstance(node.body[0].value, (ast.Constant, ast.Str)):
                    # Hat Docstring
                    docstring = node.body[0].value
                    if isinstance(docstring, ast.Constant):
                        docstring_text = docstring.value or ""
                    else:
                        docstring_text = docstring.s or ""
                    
                    # Prüfe Docstring-Qualität
                    if len(docstring_text.strip()) < 10:
                        report.add(Finding(
                            severity="low",
                            check="docstrings",
                            location=f"{rel}:{node.lineno}",
                            message=f"{node_type} '{name}' hat zu kurzen Docstring (<10 Zeichen)",
                        ))
                else:
                    # Kein Docstring
                    severity = "medium" if isinstance(node, ast.ClassDef) or \
                              (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and 
                               node.name.startswith("_")) else "low"
                    
                    # Public Methoden und Klassen sollten Docstrings haben
                    if not node.name.startswith("_"):
                        report.add(Finding(
                            severity=severity,
                            check="docstrings",
                            location=f"{rel}:{node.lineno}",
                            message=f"{node_type} '{name}' hat keinen Docstring — Dokumentation fehlend",
                        ))
        
        if not has_module_docstring:
            report.add(Finding(
                severity="medium",
                check="docstrings",
                location=rel,
                message="Modul hat keinen Docstring — Modul-Zweck unklar",
            ))

    def _check_unused_imports(self, rel: str, tree: ast.AST, content: str, report: ExtendedReport) -> None:
        """Prüft auf unbenutzte Imports."""
        try:
            # Nutze ast.bitwise_or Überprung — einfacher: prüfe ob Import-Name im Code vorkommt
            imports = self._extract_imports(tree)
            lines = content.splitlines()
            
            for mod, lineno in imports:
                # Splite Modul-Path
                parts = mod.split(".")
                top_level = parts[0]
                
                # Prüfe ob der Import irgendwo verwendet wird
                # Einfache Heuristik: suche nach dem Namen im Code
                name_used = False
                for line in lines[lineno:]:  # Nur nach der Import-Zeile suchen
                    for part in parts:
                        # Match Wort-Grenzen
                        if re.search(rf"\b{re.escape(part)}\b", line):
                            name_used = True
                            break
                    if name_used:
                        break
                
                # Auch prüfen: from X import Y as Z
                # AST basierte Analyse wäre besser, aber für v2 reicht Heuristik
                if not name_used:
                    report.add(Finding(
                        severity="low",
                        check="unused_imports",
                        location=f"{rel}:{lineno}",
                        message=f"Import '{mod}' wird nicht verwendet — entferne unnötige Imports",
                    ))
        except Exception:
            pass  # Soft-Fail

    def _check_circular_imports(self, rel: str, tree: ast.AST, report: ExtendedReport) -> None:
        """Prüft auf zirkuläre Imports (einfache Heuristik)."""
        imports = self._extract_imports(tree)
        current_file = Path(rel).stem
        
        for mod, lineno in imports:
            parts = mod.split(".")
            import_file = parts[-1]
            
            # Wenn Import-Datei denselben Namen hat wie aktuelle Datei
            if import_file == current_file:
                report.add(Finding(
                    severity="medium",
                    check="circular_imports",
                    location=f"{rel}:{lineno}",
                    message=f"Möglicher zirkulärer Import: '{mod}' importiert sich selbst",
                ))
            
            # Prüfe ob importierte Datei aktuelle Datei importiert
            try:
                import_path = Path(rel).parent / f"{import_file}.py"
                if import_path.exists():
                    import_content = import_path.read_text()
                    if f"from {current_file} import" in import_content or \
                       f"import {current_file}" in import_content:
                        report.add(Finding(
                            severity="high",
                            check="circular_imports",
                            location=f"{rel}:{lineno}",
                            message=f"Zirkulärer Import: '{mod}' importiert {current_file}",
                        ))
            except Exception:
                pass

    def _check_extended_security(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Erweiterte Security-Checks."""
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in _EXTENDED_SECURITY_PATTERNS:
                if re.search(pattern, line):
                    report.add(Finding(
                        severity=severity,
                        check="security",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_best_practices(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Best Practice Checks."""
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in _BEST_PRACTICE_PATTERNS:
                if re.search(pattern, line):
                    report.add(Finding(
                        severity=severity,
                        check="best_practice",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_performance(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Performance Anti-Pattern Checks."""
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in _PERFORMANCE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    report.add(Finding(
                        severity=severity,
                        check="performance",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_file_general(self, rel: str, content: str, path: str, report: ExtendedReport) -> None:
        """Generische Checks für nicht-Python-Dateien."""
        # JSON Validierung
        if path.endswith(".json"):
            self._check_json_file(rel, content, report)
        # YAML Validierung
        elif path.endswith((".yaml", ".yml")):
            self._check_yaml_file(rel, content, report)
        # TOML Validierung
        elif path.endswith(".toml"):
            self._check_toml_file(rel, content, report)
        # Dockerfile Checks
        elif path.endswith("Dockerfile") or "/Dockerfile" in path:
            self._check_dockerfile_content(rel, content, report)
        # Shell-Skripte
        elif path.endswith(".sh"):
            self._check_shell_script(rel, content, report)
        # Markdown
        elif path.endswith(".md"):
            self._check_markdown(rel, content, report)
        # Gitignore
        elif path.endswith(".gitignore"):
            self._check_gitignore(rel, content, report)
        # Requirements
        elif path.endswith(("requirements.txt", "requirements-dev.txt")):
            self._check_requirements(rel, content, report)
        # Pyproject
        elif path.endswith("pyproject.toml"):
            self._check_pyproject(rel, content, report)

    def _check_file_encoding(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Prüft Datei-Codierung."""
        # Prüfe auf UTF-8 BOM (sollte nicht da sein)
        if content.startswith("\ufeff"):
            report.add(Finding(
                severity="low",
                check="encoding",
                location=rel,
                message="Datei hat UTF-8 BOM — unnötig in Python-Dateien",
            ))
        
        # Prüfe auf nicht-UTF-8 Zeichen (kann Probleme machen)
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            report.add(Finding(
                severity="medium",
                check="encoding",
                location=rel,
                message="Datei enthält nicht-UTF-8 Zeichen — konvertiere zu UTF-8",
            ))

    def _check_line_length(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Prüft Zeilenlänge (PEP 8: max 79 für Code, 88 für Docstrings/Comments)."""
        for i, line in enumerate(content.splitlines(), start=1):
            length = len(line)
            # Ignoriere Kommentare und Docstrings
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                if length > 100:
                    report.add(Finding(
                        severity="low",
                        check="line_length",
                        location=f"{rel}:{i}",
                        message=f"Zeile ist {length} Zeichen lang (>100 für Kommentare/Docstrings)",
                    ))
            else:
                if length > 88:
                    report.add(Finding(
                        severity="low",
                        check="line_length",
                        location=f"{rel}:{i}",
                        message=f"Zeile ist {length} Zeichen lang (PEP 8: max 79, wir erlauben 88)",
                    ))

    # ─────────────────────────────────────────────────────────────────────
    # Datei-spezifische Checks
    # ─────────────────────────────────────────────────────────────────────

    def _check_json_file(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Validiert JSON-Dateien."""
        try:
            data = json.loads(content)
            # Prüfe auf leere Datei
            if not data:
                report.add(Finding(
                    severity="low",
                    check="json",
                    location=rel,
                    message="JSON-Datei ist leer",
                ))
        except json.JSONDecodeError as e:
            report.add(Finding(
                severity="high",
                check="json",
                location=rel,
                message=f"Ungültiges JSON: {e}",
            ))

    def _check_yaml_file(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Validiert YAML-Dateien."""
        try:
            import yaml
            yaml.safe_load(content)
        except ImportError:
            pass  # yaml nicht installiert, skip
        except yaml.YAMLError as e:
            report.add(Finding(
                severity="high",
                check="yaml",
                location=rel,
                message=f"Ungültiges YAML: {e}",
            ))
        except Exception as e:
            report.add(Finding(
                severity="medium",
                check="yaml",
                location=rel,
                message=f"YAML Parsing-Fehler: {e}",
            ))

    def _check_toml_file(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Validiert TOML-Dateien."""
        try:
            import tomllib
            tomllib.loads(content)
        except ImportError:
            # Python < 3.11
            try:
                import tomli
                tomli.loads(content)
            except ImportError:
                pass
            except Exception as e:
                report.add(Finding(
                    severity="high",
                    check="toml",
                    location=rel,
                    message=f"Ungültiges TOML: {e}",
                ))
        except Exception as e:
            report.add(Finding(
                severity="high",
                check="toml",
                location=rel,
                message=f"Ungültiges TOML: {e}",
            ))

    def _check_dockerfile_content(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Dockerfile-spezifische Checks."""
        docker_patterns = [
            (r"^FROM\s+.*:latest\b", "medium", 
             "':latest' Tag — nutze spezifische Version für Reproduzierbarkeit"),
            (r"^RUN\s+.*--no-cache-dir", "low", 
             "--no-cache-dir wird ignoriert — nutze separate RUN-Befehle"),
            (r"^FROM\s+.*\broot\b", "high", 
             "Container läuft als root — nutze USER für Sicherheit"),
            (r"^USER\s+root", "high", 
             "Container läuft als root — nutze nicht-root User"),
            (r"^EXPOSE\s+\d+", "low", 
             "EXPOSE ohne Port-Beschränkung — präzisiere welche Ports exponiert werden"),
            (r'^CMD\s*\["/bin/bash"\]', "medium", 
             'CMD ["/bin/bash"] — nutze spezifischen Befehl statt Shell'),
            (r'^ENTRYPOINT\s*\["/bin/sh"\]', "medium", 
             'ENTRYPOINT ["/bin/sh"] — nutze spezifischen Befehl statt Shell'),
            (r"\bapt\s+get\s+update\b", "medium", 
             "apt-get update ohne apt-get install — nutze kombinierten Befehl"),
            (r"\bapt\s+get\s+install\s+.*--yes", "low", 
             "apt-get install --yes — vermeide --yes in Dockerfiles"),
            (r"\bpip\s+install\s+.*--upgrade", "medium", 
             "pip install --upgrade — vermeide in Dockerfiles, pinne Versionen"),
            (r"\bADD\s+.*\s+/", "medium", 
             "ADD mit URL — nutze wget/curl + RUN für bessere Cache-Nutzung"),
            (r"\bCOPY\s+\.\s+/", "low", 
             "COPY . / — zu allgemein, kopiere nur notwendige Files"),
            (r"\bVOLUME\s+", "low", 
             "VOLUME — sollte explizit sein, nicht generisch"),
            (r"\bENV\s+.*\s*=", "low", 
             "ENV ohne Wert — setze Default-Werte"),
        ]
        
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in docker_patterns:
                if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                    report.add(Finding(
                        severity=severity,
                        check="docker",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_shell_script(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Shell-Skript Checks."""
        shell_patterns = [
            (r"^#!/bin/sh\b", "low", 
             "Shebang ist #!/bin/sh — nutze #!/bin/bash für bessere Kompatibilität"),
            (r"\beval\s+\$\(", "high", "eval() mit Command Substitution — RCE-Risiko"),
            (r"\beval\s+[^$]", "high", "eval() — RCE-Risiko"),
            (r"\bsource\s+\w+", "low", "source — nutze . (Dot) für bessere Portabilität"),
            (r"\b\.\s+\w+", "low", "Sourcing von Dateien — prüfe ob notwendige Dateien existieren"),
            (r"\bchmod\s+777\b", "medium", "chmod 777 — zu permissiv"),
            (r"\bwget\s+.*\b--no-check-certificate\b", "medium", 
             "wget --no-check-certificate — Sicherheitsrisiko"),
            (r"\bcurl\s+.*\b-k\b", "medium", "curl -k — TLS-Verification deaktiviert"),
            (r"\bcurl\s+.*\b--insecure\b", "medium", "curl --insecure — TLS-Verification deaktiviert"),
            (r"\brm\s+\-rf\s+/\b", "high", "rm -rf / — Katastrophales Risiko"),
            (r"\b>\s+/dev/null\s*2>&1", "low", 
             "Output zu /dev/null — Debugging erschwert"),
            (r"\bset\s+\-e", "low", "set -e — gut, aber prüfe ob alle Befehle korrekt handhabt"),
            (r"\bset\s+\-x", "low", "set -x — Debug-Output, entferne für Produktion"),
        ]
        
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in shell_patterns:
                if re.search(pattern, line):
                    report.add(Finding(
                        severity=severity,
                        check="shell",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_markdown(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Markdown-Datei Checks."""
        md_patterns = [
            (r"^\[.*\]\(<.*>\)", "low", "Markdown Link mit < > — möglicherweise HTML, prüfe"),
            (r"^#\s+#", "low", "Doppelte # in Überschrift — Syntax-Fehler"),
            (r"^\s*#\s*$", "low", "Leere Überschrift — entferne"),
            (r"\bhttp://", "low", "HTTP-URL (nicht HTTPS) — nutze HTTPS wo möglich"),
            (r"\bTODO\b", "low", "TODO in Markdown — technisch Schuld markieren"),
            (r"\bFIXME\b", "low", "FIXME in Markdown — technisch Schuld markieren"),
        ]
        
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") and not stripped.startswith("# "):
                report.add(Finding(
                    severity="low",
                    check="markdown",
                    location=f"{rel}:{i}",
                    message="Überschrift ohne Leerzeichen nach #",
                ))
            
            for pattern, severity, msg in md_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    report.add(Finding(
                        severity=severity,
                        check="markdown",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_gitignore(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Gitignore Checks."""
        gitignore_patterns = [
            (r"^\.env$", "medium", "*.env nicht ignoriert — sollte .env* sein"),
            (r"^env$", "medium", "env nicht ignoriert — sollte .env* sein"),
            (r"^\.vscode/$", "low", ".vscode/ sollte spezifischer sein (z.B. .vscode/*.json)"),
            (r"^\.idea/$", "low", ".idea/ sollte spezifischer sein"),
            (r"^\.DS_Store$", "low", ".DS_Store — gut, aber prüfe ob auch ._* ignoriert"),
            (r"^__pycache__", "low", "__pycache__ nicht ignoriert — füge *.py[cod] hinzu"),
            (r"^\.Python$", "low", ".Python — alte Python-Cache-Dateien"),
            (r"^\.mypy_cache$", "low", ".mypy_cache sollte ignoriert werden"),
            (r"^\.pytest_cache$", "low", ".pytest_cache sollte ignoriert werden"),
            (r"^\.coverage$", "low", ".coverage sollte ignoriert werden"),
            (r"^htmlcov/$", "low", "htmlcov/ sollte ignoriert werden"),
            (r"^\.venv$", "low", ".venv sollte ignoriert werden"),
            (r"^venv/$", "low", "venv/ sollte ignoriert werden"),
            (r"^\.eggs/$", "low", ".eggs/ sollte ignoriert werden"),
            (r"^dist/$", "low", "dist/ sollte ignoriert werden"),
            (r"^build/$", "low", "build/ sollte ignoriert werden"),
        ]
        
        essential_patterns = [
            ".env", "*.pyc", "__pycache__", ".DS_Store", ".vscode", ".idea",
            ".mypy_cache", ".pytest_cache", ".coverage", "*.egg-info", "dist/", "build/"
        ]
        
        for pattern in essential_patterns:
            if pattern not in content and pattern.replace("/", "") not in content:
                report.add(Finding(
                    severity="low",
                    check="gitignore",
                    location=rel,
                    message=f"Empfohlenes Pattern '{pattern}' fehlt in .gitignore",
                ))
        
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            
            for pattern, severity, msg in gitignore_patterns:
                if re.search(pattern, line, re.MULTILINE):
                    report.add(Finding(
                        severity=severity,
                        check="gitignore",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_requirements(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Requirements.txt Checks."""
        req_patterns = [
            (r"^[^=<>\s]+", "low", "Package ohne Version — pinne spezifische Version"),
            (r"^[^=<>\s]+\s*==\s*\*", "high", "==* — ungültige Version-Spezifikation"),
            (r"\bgit\+https://", "medium", 
             "Git-URL in requirements — nutze stattdessen installierbare Package"),
            (r"\b-\s*e\s", "low", "-e (editable) in requirements.txt — gehöre in requirements-dev.txt"),
            (r"\b#\s*.*requirements", "low", 
             "Kommentar mit requirements — nutze separate Dateien"),
        ]
        
        # Prüfe auf Version-Pinning
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            
            # Prüfe ob Package Version hat
            if not re.search(r"[=<>~!]", stripped):
                report.add(Finding(
                    severity="medium",
                    check="requirements",
                    location=f"{rel}:{i}",
                    message=f"Package '{stripped.split()[0]}' ohne Version-Pin — pinne Version für Reproduzierbarkeit",
                ))
            
            for pattern, severity, msg in req_patterns:
                if re.search(pattern, line):
                    report.add(Finding(
                        severity=severity,
                        check="requirements",
                        location=f"{rel}:{i}",
                        message=f"{msg} → `{line.strip()[:80]}`",
                    ))

    def _check_pyproject(self, rel: str, content: str, report: ExtendedReport) -> None:
        """Pyproject.toml Checks."""
        try:
            import tomllib
            data = tomllib.loads(content)
            
            # Prüfe auf notwendig Felder
            if "project" not in data:
                report.add(Finding(
                    severity="medium",
                    check="pyproject",
                    location=rel,
                    message="pyproject.toml fehlt [project] Sektion",
                ))
            elif "name" not in data["project"]:
                report.add(Finding(
                    severity="medium",
                    check="pyproject",
                    location=rel,
                    message="pyproject.toml [project] fehlt 'name'",
                ))
            elif "version" not in data["project"]:
                report.add(Finding(
                    severity="medium",
                    check="pyproject",
                    location=rel,
                    message="pyproject.toml [project] fehlt 'version'",
                ))
            
            if "build-system" not in data:
                report.add(Finding(
                    severity="low",
                    check="pyproject",
                    location=rel,
                    message="pyproject.toml fehlt [build-system] Sektion",
                ))
            
            # Prüfe auf sinnvolle Dependencies
            project = data.get("project", {})
            deps = project.get("dependencies", [])
            if len(deps) == 0:
                report.add(Finding(
                    severity="low",
                    check="pyproject",
                    location=rel,
                    message="pyproject.toml hat keine Dependencies definiert",
                ))
                
        except Exception as e:
            report.add(Finding(
                severity="high",
                check="pyproject",
                location=rel,
                message=f"Ungültiges pyproject.toml: {e}",
            ))

    # ─────────────────────────────────────────────────────────────────────
    # Cross-File Checks
    # ─────────────────────────────────────────────────────────────────────

    def _check_dependencies(self, changes: list[dict], report: ExtendedReport) -> None:
        """Prüft Dependencies und Versions-Konflikte."""
        py_files = [c for c in changes if c["path"].endswith(".py")]
        
        # Sammle alle Imports
        all_imports = set()
        for c in py_files:
            try:
                tree = ast.parse(c["content"], filename=c["path"])
                imports = self._extract_imports(tree)
                all_imports.update(mod for mod, _ in imports)
            except Exception:
                pass
        
        # Prüfe auf bekannte Problem-Packages
        problematic_packages = {
            "requests": "2.28.0",  # Älter als 2.28.0 hat Sicherheitslücken
            "urllib3": "1.26.0",    # Älter als 1.26.0
            "cryptography": "35.0.0",
            "pyopenssl": "22.0.0",
            "pyyaml": "5.4.0",
        }
        
        for pkg in all_imports:
            top = pkg.split(".")[0]
            if top in problematic_packages:
                # Prüfe ob Package installiert ist und Version OK
                try:
                    spec = importlib.util.find_spec(top)
                    if spec is not None:
                        import importlib.metadata
                        version = importlib.metadata.version(top)
                        min_version = problematic_packages[top]
                        
                        # Einfache Version-Vergleich (nur Major.Minor)
                        if self._compare_versions(version, min_version) < 0:
                            report.add(Finding(
                                severity="high",
                                check="dependencies",
                                location="<requirements>",
                                message=f"Package '{top}' Version {version} < {min_version} — Sicherheitsupdate verfügbar",
                            ))
                except Exception:
                    pass

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Vergleicht zwei Versions-Strings. Return: -1, 0, 1"""
        def parse_version(v):
            return tuple(int(x) for x in v.split(".") if x.isdigit())
        
        v1_parts = parse_version(v1)
        v2_parts = parse_version(v2)
        
        return (v1_parts > v2_parts) - (v1_parts < v2_parts)

    def _check_git_issues(self, changes: list[dict], report: ExtendedReport) -> None:
        """Prüft auf Git-spezifische Issues."""
        # Prüfe ob .gitignore aktuell ist
        gitignore_path = self.root / ".gitignore"
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()
            
            # Prüfe ob neue Dateitypen ignoriert werden müssen
            new_extensions = set()
            for c in changes:
                path = Path(c["path"])
                ext = path.suffix
                if ext and ext not in (".py", ".pyc", ".md", ".txt", ".json"):
                    new_extensions.add(ext)
            
            if new_extensions:
                for ext in new_extensions:
                    if f"*{ext}" not in gitignore_content and ext not in gitignore_content:
                        report.add(Finding(
                            severity="low",
                            check="git",
                            location=".gitignore",
                            message=f"Neue Datei-Endung '{ext}' sollte evtl. in .gitignore aufgenommen werden",
                        ))
        else:
            report.add(Finding(
                severity="medium",
                check="git",
                location=self.root,
                message=".gitignore fehlt — wichtige Dateien werden möglicherweise commited",
            ))
        
        # Prüfe auf sensible Dateien in Changes
        sensitive_files = [".env", ".env.local", ".env.prod", "secrets.json", 
                          "config.ini", "credentials.py", "passwords.txt"]
        for c in changes:
            path = Path(c["path"])
            for sensitive in sensitive_files:
                if sensitive in str(path):
                    report.add(Finding(
                        severity="high",
                        check="git",
                        location=str(path),
                        message=f"Sensible Datei '{path.name}' wird geändert — prüfe ob diese Datei in .gitignore ist",
                    ))

    def _check_config_files(self, changes: list[dict], report: ExtendedReport) -> None:
        """Prüft Konfigurations-Dateien auf Best Practices."""
        config_files = [c for c in changes if any(
            c["path"].endswith(ext) 
            for ext in [".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"]
        )]
        
        for c in config_files:
            path = c["path"]
            content = c["content"]
            
            if path.endswith(".json"):
                self._check_json_config(path, content, report)
            elif path.endswith((".yaml", ".yml")):
                self._check_yaml_config(path, content, report)
            elif path.endswith(".toml"):
                self._check_toml_config(path, content, report)

    def _check_json_config(self, path: str, content: str, report: ExtendedReport) -> None:
        """JSON-Konfig Checks."""
        try:
            data = json.loads(content)
            
            # Prüfe auf sensible Keys
            sensitive_keys = ["password", "secret", "api_key", "token", "private_key", "credentials"]
            for key in sensitive_keys:
                if self._find_key_recursive(data, key):
                    report.add(Finding(
                        severity="high",
                        check="config",
                        location=path,
                        message=f"Konfigurations-Datei enthält '{key}' — prüfe ob dies sicher ist",
                    ))
            
            # Prüfe auf hardcoded IPs
            ip_pattern = r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
            for key, value in self._flatten_dict(data).items():
                if isinstance(value, str) and re.search(ip_pattern, value):
                    report.add(Finding(
                        severity="medium",
                        check="config",
                        location=f"{path}:{key}",
                        message=f"Hardcoded IP-Adresse gefunden: {value}",
                    ))
                    
        except Exception:
            pass

    def _check_yaml_config(self, path: str, content: str, report: ExtendedReport) -> None:
        """YAML-Konfig Checks."""
        try:
            import yaml
            data = yaml.safe_load(content)
            if data is None:
                return
            
            # Prüfe auf sensible Keys
            sensitive_keys = ["password", "secret", "api_key", "token", "private_key", "credentials"]
            for key in sensitive_keys:
                if self._find_key_recursive(data, key):
                    report.add(Finding(
                        severity="high",
                        check="config",
                        location=path,
                        message=f"Konfigurations-Datei enthält '{key}' — prüfe ob dies sicher ist",
                    ))
        except ImportError:
            pass
        except Exception:
            pass

    def _check_toml_config(self, path: str, content: str, report: ExtendedReport) -> None:
        """TOML-Konfig Checks."""
        try:
            import tomllib
            data = tomllib.loads(content)
            
            # Prüfe auf sensible Keys (flach)
            sensitive_keys = ["password", "secret", "api_key", "token", "private_key", "credentials"]
            for key in sensitive_keys:
                if key in data or any(key in d for d in data.values() if isinstance(d, dict)):
                    report.add(Finding(
                        severity="high",
                        check="config",
                        location=path,
                        message=f"Konfigurations-Datei enthält '{key}' — prüfe ob dies sicher ist",
                    ))
        except Exception:
            pass

    def _check_docker_files(self, changes: list[dict], report: ExtendedReport) -> None:
        """Prüft Docker-bezogene Dateien."""
        docker_files = [c for c in changes if "Dockerfile" in c["path"] or c["path"].endswith(".dockerignore")]
        
        for c in docker_files:
            if "Dockerfile" in c["path"]:
                self._check_dockerfile_content(c["path"], c["content"], report)

    # ─────────────────────────────────────────────────────────────────────
    # Erweiterte Plan-Checks
    # ─────────────────────────────────────────────────────────────────────

    def _check_plan_completeness(self, plan_text: str, plan_kind: str, report: ExtendedReport) -> None:
        """Prüft ob der Plan alle wichtigen Aspekte abdeckt."""
        if plan_kind != "detail":
            return
        
        # Wichtige Keywords für verschiedene Bereiche
        completeness_checks = {
            "Error Handling": ["Error", "Exception", "try", "except", "Fehler", "Error-Handling"],
            "Logging": ["Log", "Logger", "logging", "print"],
            "Documentation": ["Docstring", "Dokumentation", "Kommentar", "Comment"],
            "Type Hints": ["Type", "Hint", "Typ", "Annotation"],
            "Security": ["Security", "Sicherheit", "Sicher", "Security-Check"],
            "Testing": ["Test", "pytest", "unittest", "Testfall"],
            "Performance": ["Performance", "Leistung", "Performance-Check", "Effizienz"],
        }
        
        for category, keywords in completeness_checks.items():
            found = any(re.search(rf"\b({kw})\b", plan_text, re.IGNORECASE) 
                       for kw in keywords)
            if not found:
                report.add(Finding(
                    severity="low",
                    check="plan_completeness",
                    location="<plan>",
                    message=f"Detail-Plan erwähnt nichts zu '{category}' — möglicherweise unvollständig",
                ))

    def _check_plan_consistency(self, plan_text: str, plan_kind: str, report: ExtendedReport) -> None:
        """Prüft auf Konsistenz im Plan (z.B. widersprüchliche Aussagen)."""
        if plan_kind != "detail":
            return
        
        # Prüfe auf widersprüchliche LOC-Angaben
        loc_matches = re.findall(r"(\d{2,4})\s*(?:LOC|loc|Zeilen|lines)", plan_text, re.IGNORECASE)
        if len(set(loc_matches)) > 1:
            report.add(Finding(
                severity="low",
                check="plan_consistency",
                location="<plan>",
                message=f"Mehrere unterschiedliche LOC-Angaben gefunden: {loc_matches} — prüfe Konsistenz",
            ))
        
        # Prüfe auf widersprüchliche Datei-Angaben
        file_pattern = r"\b([a-z_][\w\-/]*\.py)\b"
        file_matches = re.findall(file_pattern, plan_text, re.IGNORECASE)
        if len(file_matches) > 0:
            # Prüfe ob dieselbe Datei mit unterschiedlichen Namen erwähnt wird
            file_counts = {f: file_matches.count(f) for f in set(file_matches)}
            for f, count in file_counts.items():
                if count > 1:
                    report.add(Finding(
                        severity="low",
                        check="plan_consistency",
                        location="<plan>",
                        message=f"Datei '{f}' wird {count}x erwähnt — möglicherweise Redundanz",
                    ))

    def _check_context_consistency(self, changes: list[dict], plan_text: str, context: dict, report: ExtendedReport) -> None:
        """Prüft Konsistenz zwischen Changes, Plan und Kontext."""
        # Prüfe ob Plan den Kontext berücksichtigt
        if "existing_files" in context:
            existing = set(context["existing_files"])
            changed_files = {Path(c["path"]).name for c in changes}
            
            # Warnung wenn Plan Dateien ändert die nicht im Kontext sind
            for plan_file in re.findall(r"\b([a-z_][\w\-/]*\.py)\b", plan_text, re.IGNORECASE):
                basename = Path(plan_file).name
                if basename not in changed_files and basename not in existing:
                    report.add(Finding(
                        severity="medium",
                        check="context",
                        location="<plan>",
                        message=f"Plan erwähnt '{basename}' — existiert weder in Changes noch im Kontext",
                    ))

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _flatten_dict(self, d, parent_key="", sep="."):
        """Flach ein verschachteltes Dict machen."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _find_key_recursive(self, data, target_key):
        """Sucht rekursiv nach einem Key in einem Dict."""
        if isinstance(data, dict):
            if target_key in data:
                return True
            return any(self._find_key_recursive(v, target_key) for v in data.values())
        elif isinstance(data, list):
            return any(self._find_key_recursive(item, target_key) for item in data)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Self-Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    v = StaticValidatorV2()

    # Demo: bewusst kaputter Code
    demo_changes = [{
        "path": "demo_buggy.py",
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
            "\n"
            "class MyClass:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n"
            "# TODO: fix this\n"
            "def test_example():\n"
            "    assert True == True\n"
        ),
        "exists": False,
    }]
    
    demo_plan = """
Files: demo_buggy.py (~30 LOC)
Tests: test_demo.py mit pytest
Rollback: git revert
Strategy: refactor existing code
"""

    print("=== Demo: StaticValidatorV2 mit bewusst kaputtem Code ===")
    rep = v.validate_code(demo_changes, demo_plan)
    print(rep.render())
    print()
    print(f"Verdict: {rep.verdict}, {len(rep.findings)} findings")
    print()
    print("Stats:", rep.stats)
    print()
    print("By Category:")
    for cat, findings in rep.by_category.items():
        print(f"  {cat}: {len(findings)} findings")
