#!/usr/bin/env python3
"""
vibelike doctor — deterministischer Selbst-Check der Codebase.

Bündelt die nicht-LLM-Anker, die diese Session aus manuellen Funden lehrte, zu
permanenten Checks. Fängt genau die Bug-Klassen, die der grosse Refactor erst
beim Testen offenbarte:

  • syntax        — jede .py kompiliert (py_compile)
  • config        — jeder `from config import X` löst auf (die TOOLS_DIR-Breakage)
  • imports       — Kernmodule importieren ohne Fehler (broken-import-Schutz)
  • regression    — regression_guard auf den Working Tree (destruktive Edits)

Usage:
  python3 doctor.py            # alle Checks
  python3 doctor.py --fast     # nur syntax + config (kein schwerer Import, CI-Gate)

Exit-Code: 0 wenn alles ✓, 1 bei mindestens einem ✗.
"""

from __future__ import annotations

import argparse
import ast
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent

# Verzeichnisse, die NICHT gescannt werden (Wegwerf/Experiment/vendored).
_SKIP_DIRS = {
    "__pycache__", ".git", "experiments", "attic", "choose_tests",
    "chaosgarten", "build", "dist", "venv", "env", ".venv", "framework",
    "ossifikat",
}

# Kernmodule für den Import-Check (entry points + diese Session). Bewusst kuratiert
# statt „alles importieren" — vermeidet Seiteneffekte von Skripten + torch-Last je Modul.
_CORE_MODULES = [
    "config", "errors", "regression_guard", "model_fallback", "idiom_feedback",
    "phase_idiom_router", "task_classifier", "vault_router",
    "tools.registry", "tools.cache", "reqqueue.manager", "sandbox.manager",
    "models.request",
]


def _iter_py_files() -> List[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return out


# ───────────────────────────────── Checks ─────────────────────────────────

def check_syntax() -> Tuple[bool, List[str]]:
    """Jede .py kompiliert sauber."""
    errors = []
    for path in _iter_py_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{path.relative_to(ROOT)}: {e.msg.splitlines()[0]}")
    return (not errors, errors)


def check_config_imports() -> Tuple[bool, List[str]]:
    """Jeder `from (vibelike.)config import X` löst auf settings/Shim auf.

    Genau die Bug-Klasse der Pydantic-Migration: config.py exportierte Konstanten
    nicht mehr, Importer brachen erst zur Laufzeit. AST-basiert (fängt auch
    parenthesierte Multi-Line-Importe).
    """
    import config as cfg

    errors = []
    for path in _iter_py_files():
        if path.name == "config.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("config", "vibelike.config"):
                for alias in node.names:
                    name = alias.name
                    if name == "*":
                        continue
                    try:
                        getattr(cfg, name)
                    except AttributeError:
                        errors.append(f"{path.relative_to(ROOT)}: from {node.module} import {name} → fehlt")
    return (not errors, errors)


def check_core_imports() -> Tuple[bool, List[str]]:
    """Kernmodule importieren ohne Fehler (jeweils im Subprozess, isoliert)."""
    errors = []
    for mod in _CORE_MODULES:
        r = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120,
        )
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or ["?"])[-1]
            errors.append(f"import {mod} → {last}")
    return (not errors, errors)


def check_regression() -> Tuple[bool, List[str]]:
    """regression_guard auf den Working Tree (destruktiver Symbol-Verlust = ✗)."""
    try:
        from regression_guard import check_git
    except Exception as e:
        return (True, [f"(übersprungen: {e})"])
    result = check_git()  # working tree vs HEAD
    if result["verdict"] == "🔴":
        return (False, [f"{i['file']}: {i['detail']}"
                        for i in result["issues"] if i["kind"] == "symbol_loss"])
    return (True, [])


# ───────────────────────────────── Runner ─────────────────────────────────

CHECKS_FAST = [("syntax", check_syntax), ("config", check_config_imports)]
CHECKS_FULL = CHECKS_FAST + [("imports", check_core_imports), ("regression", check_regression)]


def main() -> int:
    ap = argparse.ArgumentParser(description="vibelike doctor — Selbst-Check")
    ap.add_argument("--fast", action="store_true",
                    help="nur syntax + config (kein schwerer Import) — CI-Gate")
    args = ap.parse_args()

    checks = CHECKS_FAST if args.fast else CHECKS_FULL
    print("=" * 60)
    print(f"vibelike doctor {'(--fast)' if args.fast else ''}")
    print("=" * 60)

    all_ok = True
    for name, fn in checks:
        try:
            ok, problems = fn()
        except Exception as e:
            ok, problems = False, [f"Check-Fehler: {e}"]
        icon = "✓" if ok else "✗"
        print(f"\n[{icon}] {name}")
        if not ok:
            all_ok = False
            for p in problems[:15]:
                print(f"      {p}")
            if len(problems) > 15:
                print(f"      … (+{len(problems) - 15} weitere)")

    print("\n" + "=" * 60)
    print("✓ Alles gesund" if all_ok else "✗ Probleme gefunden — siehe oben")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
