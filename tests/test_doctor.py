"""Tests für doctor.py — beweisen, dass die Checks echt anschlagen (nicht nur grün)."""

import sys
import textwrap
from pathlib import Path

import pytest

import doctor


def test_syntax_ok_on_clean_tree():
    ok, errors = doctor.check_syntax()
    assert ok, f"unerwartete Syntaxfehler: {errors}"


def test_config_imports_ok_on_clean_tree():
    ok, errors = doctor.check_config_imports()
    assert ok, f"unaufgelöste config-Importe: {errors}"


def test_config_check_catches_missing_name(tmp_path, monkeypatch):
    """check_config_imports MUSS einen erfundenen config-Import flaggen."""
    # Scratch-Datei mit kaputtem Import in einen temporären ROOT legen
    bad = tmp_path / "broken_importer.py"
    bad.write_text("from config import TOTALLY_MISSING_CONST\n")
    (tmp_path / "config.py").write_text("settings = object()\n")
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    # config-Modul-Stub ohne das Symbol
    import types
    stub = types.ModuleType("config")
    monkeypatch.setitem(sys.modules, "config", stub)

    ok, errors = doctor.check_config_imports()
    assert not ok
    assert any("TOTALLY_MISSING_CONST" in e for e in errors)


def test_syntax_check_catches_broken_file(tmp_path, monkeypatch):
    """check_syntax MUSS eine Datei mit Syntaxfehler flaggen."""
    bad = tmp_path / "broken_syntax.py"
    bad.write_text("def (: this is not valid python\n")
    monkeypatch.setattr(doctor, "ROOT", tmp_path)

    ok, errors = doctor.check_syntax()
    assert not ok
    assert any("broken_syntax.py" in e for e in errors)


def test_skip_dirs_excluded(tmp_path, monkeypatch):
    """Dateien in Skip-Verzeichnissen (experiments/) werden nicht geprüft."""
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments" / "junk.py").write_text("def (: broken\n")
    monkeypatch.setattr(doctor, "ROOT", tmp_path)

    ok, errors = doctor.check_syntax()
    assert ok  # broken file in experiments/ wird ignoriert
