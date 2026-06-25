"""Tests für den standalone Regression-Guard (④)."""

import pytest

from regression_guard import (
    check_change,
    top_level_symbols,
    verdict_for,
)


# ───────────────────────── top_level_symbols ─────────────────────────

def test_symbols_extracts_class_func_const():
    src = "X = 1\ndef foo(): pass\nclass Bar: pass\nasync def baz(): pass\n"
    assert top_level_symbols(src) == {"X", "foo", "Bar", "baz"}


def test_symbols_syntax_error_returns_none():
    assert top_level_symbols("def (: bad") is None


def test_symbols_ignores_nested():
    src = "class A:\n    def method(self): pass\n"
    # nur A ist top-level, method nicht
    assert top_level_symbols(src) == {"A"}


# ───────────────────────────── check_change ──────────────────────────

OLD = "import os\nA = 1\ndef foo():\n    return 1\nclass Bar:\n    pass\n"


def test_symbol_loss_flagged():
    new = "import os\nA = 1\nclass Bar:\n    pass\n"  # foo entfernt
    issues = check_change("m.py", OLD, new)
    assert any(i["kind"] == "symbol_loss" for i in issues)
    assert "foo" in str(issues)


def test_authorized_removal_not_flagged():
    new = "import os\nA = 1\nclass Bar:\n    pass\n"
    issues = check_change("m.py", OLD, new, plan_text="Entferne die Funktion foo")
    assert not any(i["kind"] == "symbol_loss" for i in issues)


def test_no_loss_when_symbols_kept():
    new = OLD + "\nB = 2\n"  # nur hinzugefügt
    issues = check_change("m.py", OLD, new)
    assert issues == []


def test_size_collapse_flagged():
    old = "\n".join(f"line_{i} = {i}" for i in range(40))  # 40 Symbole/Zeilen
    new = "line_0 = 0\nline_1 = 1\n"                       # massiv geschrumpft
    issues = check_change("m.py", old, new)
    assert any(i["kind"] == "size_collapse" for i in issues)


def test_small_file_no_collapse():
    old = "a = 1\nb = 2\n"   # < 20 Zeilen → kein Kollaps-Check
    new = "a = 1\n"
    issues = check_change("m.py", old, new)
    assert not any(i["kind"] == "size_collapse" for i in issues)


def test_non_python_skips_symbol_check():
    issues = check_change("notes.md", "# A\n## B\n", "# A\n")
    assert not any(i["kind"] == "symbol_loss" for i in issues)


# ────────────────────────────── verdict_for ──────────────────────────

def test_verdict_red_on_symbol_loss():
    assert verdict_for([{"kind": "symbol_loss"}]) == "🔴"


def test_verdict_yellow_on_size_only():
    assert verdict_for([{"kind": "size_collapse"}]) == "🟡"


def test_verdict_green_on_moved_only():
    # Cross-File-Move eskaliert NICHT
    assert verdict_for([{"kind": "symbol_moved"}]) == "🟢"


def test_verdict_green_on_empty():
    assert verdict_for([]) == "🟢"


def test_red_dominates_mixed():
    assert verdict_for([
        {"kind": "size_collapse"}, {"kind": "symbol_moved"}, {"kind": "symbol_loss"},
    ]) == "🔴"
