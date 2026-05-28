import pytest
from validator2 import ExtendedReport, RegexPatternEngine, SECURITY_PATTERNS

def test_none_comparison_flags():
    report = ExtendedReport()
    line = "if x == None:"
    RegexPatternEngine(SECURITY_PATTERNS).scan_line(line, 1, "test.py", report, disabled=set(), overrides={})
    assert any(f.check == "none_comparison" for f in report.findings)

def test_none_comparison_flags_negative():
    report = ExtendedReport()
    line = "if x is None:"
    RegexPatternEngine(SECURITY_PATTERNS).scan_line(line, 1, "test.py", report, disabled=set(), overrides={})
    assert not any(f.check == "none_comparison" for f in report.findings)

def test_not_none_comparison_flags():
    report = ExtendedReport()
    line = "if x != None:"
    RegexPatternEngine(SECURITY_PATTERNS).scan_line(line, 1, "test.py", report, disabled=set(), overrides={})
    assert any(f.check == "none_comparison" for f in report.findings)

def test_not_none_comparison_flags_negative():
    report = ExtendedReport()
    line = "if x is not None:"
    RegexPatternEngine(SECURITY_PATTERNS).scan_line(line, 1, "test.py", report, disabled=set(), overrides={})
    assert not any(f.check == "none_comparison" for f in report.findings)