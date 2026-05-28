import re

class Finding:
    """Represents a finding with severity, check ID, and message."""
    
    def __init__(self, severity, check, message):
        self.severity = severity
        self.check = check
        self.message = message

class ExtendedReport:
    """Stores findings for reporting purposes."""
    
    def __init__(self):
        self.findings = []

    def add_finding(self, finding: Finding):
        """Adds a finding to the report."""
        self.findings.append(finding)

class RegexPatternEngine:
    """Engine to scan lines of code for security patterns."""
    
    SECURITY_PATTERNS = [
        (r"\b(os\.environ\.get\s*\(\s*['\"]SECRET_KEY['\"]\s*\))", "security:env_var_cred"),
        # Add other patterns here
    ]

    def __init__(self, patterns, category):
        self.patterns = patterns
        self.category = category

    def scan_line(self, line: str, line_number: int, file_name: str, report: ExtendedReport, disabled: set, overrides: dict):
        """Scans a single line for security patterns and adds findings to the report."""
        for pattern, check_id in self.patterns:
            if check_id not in disabled:
                matches = re.findall(pattern, line)
                for match in matches:
                    severity = "high"  # Adjust severity as needed
                    message = f"Environment variable '{match}' contains hardcoded credential"
                    finding = Finding(severity, check_id, message)
                    report.add_finding(finding)

# Example usage
if __name__ == "__main__":
    line = "os.environ.get('SECRET_KEY')"
    report = ExtendedReport()
    engine = RegexPatternEngine(RegexPatternEngine.SECURITY_PATTERNS, "security")
    engine.scan_line(line, 42, "example.py", report, disabled=set(), overrides={})
    for finding in report.findings:
        print(f"Severity: {finding.severity}, Check ID: {finding.check}, Message: {finding.message}")