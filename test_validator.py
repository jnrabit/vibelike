import pytest
from vibelike.validator import RegexPatternEngine, ExtendedReport

def test_env_var_cred_detection():
    """Tests the detection of environment variable credentials."""
    line = "os.environ.get('SECRET_KEY')"
    report = ExtendedReport()
    engine = RegexPatternEngine(RegexPatternEngine.SECURITY_PATTERNS, "security")
    engine.scan_line(line, 42, "example.py", report, disabled=set(), overrides={})
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.severity == "high"
    assert finding.check == "security:env_var_cred"
    assert "Environment variable 'SECRET_KEY' contains hardcoded credential" in finding.message

def test_env_var_cred_ignored_if_disabled():
    """Tests that environment variable credentials are ignored if disabled."""
    line = "os.environ.get('SECRET_KEY')"
    report = ExtendedReport()
    engine = RegexPatternEngine(RegexPatternEngine.SECURITY_PATTERNS, "security")
    engine.scan_line(line, 42, "example.py", report, disabled={"env_var_cred"}, overrides={})
    assert len(report.findings) == 0