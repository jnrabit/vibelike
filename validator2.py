import re
from collections import namedtuple

Finding = namedtuple('Finding', ['line_number', 'file_name', 'check', 'severity', 'message'])

class RegexPatternEngine:
    def __init__(self, patterns):
        self.patterns = patterns

    def scan_line(self, line, line_number, file_name, report, disabled=set(), overrides={}):
        for pattern, severity, check, message in self.patterns:
            if check not in disabled and (overrides.get(check) is None or overrides[check]):
                matches = re.findall(pattern, line)
                for match in matches:
                    report.findings.append(Finding(line_number, file_name, check, severity, message))

class ExtendedReport:
    def __init__(self):
        self.findings = []

    def render(self):
        for finding in self.findings:
            print(f"Line {finding.line_number} in {finding.file_name}: {finding.message}")

SECURITY_PATTERNS = [
    ...,
    (r"\b==\s*None\b", "medium", "none_comparison", "Vermeide == None, nutze is None stattdessen"),
    (r"\b!=\s*None\b", "medium", "none_comparison", "Vermeide != None, nutze is not None stattdessen"),
]

# In der RegexPatternEngine-Initialisierung
engine = RegexPatternEngine(SECURITY_PATTERNS)