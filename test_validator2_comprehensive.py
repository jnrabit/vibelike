"""
Comprehensive Test Suite for validator2.py
============================================

Demonstrates validator2's capabilities by validating intentional code anti-patterns
across all check categories. Each test case includes problematic code and expected findings.
"""

from validator2 import StaticValidatorV2
from pathlib import Path
import json


def print_header(title):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_findings(findings, category_name=""):
    """Print findings in a formatted table."""
    if not findings:
        print(f"  ✅ No findings (clean)")
        return

    print(f"  Found {len(findings)} issues:")
    for f in findings:
        severity_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(f.severity, "⚪")
        print(f"    {severity_symbol} [{f.severity:6s}] {f.check:30s} @ {f.location}")
        print(f"      └─ {f.message}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Security Vulnerabilities
# ─────────────────────────────────────────────────────────────────────────────

def test_security_vulnerabilities():
    """Test detection of security anti-patterns."""
    print_header("TEST 1: SECURITY VULNERABILITIES")

    test_cases = [
        {
            "name": "RCE via eval()",
            "path": "security/rce_eval.py",
            "content": """
user_input = input("Enter expression: ")
result = eval(user_input)  # HIGH: RCE via eval
print(result)
"""
        },
        {
            "name": "Command Injection via subprocess shell=True",
            "path": "security/subprocess_shell.py",
            "content": """
import subprocess
user_cmd = input("Command: ")
subprocess.run(user_cmd, shell=True)  # MEDIUM: shell=True is dangerous
"""
        },
        {
            "name": "Unsafe YAML loading",
            "path": "security/yaml_unsafe.py",
            "content": """
import yaml
with open('config.yml') as f:
    config = yaml.load(f)  # MEDIUM: should use yaml.safe_load
"""
        },
        {
            "name": "Hardcoded credentials",
            "path": "security/hardcoded_creds.py",
            "content": """
API_KEY = "sk-1234567890abcdefghij"  # HIGH: hardcoded secret
SECRET_TOKEN = "token_abc123def456"
DATABASE_PASSWORD = "P@ssw0rd123"
"""
        },
        {
            "name": "Disabled SSL/TLS verification",
            "path": "security/ssl_disabled.py",
            "content": """
import requests
response = requests.get("https://api.example.com", verify=False)  # MEDIUM: SSL disabled
"""
        },
        {
            "name": "SQL Injection via f-string",
            "path": "security/sql_injection.py",
            "content": """
user_id = request.args.get('id')
query = f"SELECT * FROM users WHERE id={user_id}"  # HIGH: SQL injection risk
cursor.execute(query)
"""
        },
        {
            "name": "Insecure file permissions",
            "path": "security/file_perms.py",
            "content": """
import os
os.chmod("/var/secrets/key.txt", 0o777)  # MEDIUM: 777 is too permissive
os.chmod("/home/user/.ssh/id_rsa", 0o777)  # MEDIUM: private key exposed
"""
        },
        {
            "name": "Pickle deserialization",
            "path": "security/pickle_unsafe.py",
            "content": """
import pickle
untrusted_data = request.data
obj = pickle.loads(untrusted_data)  # MEDIUM: RCE risk with untrusted data
"""
        },
    ]

    validator = StaticValidatorV2()

    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        changes = [{"path": test["path"], "content": test["content"]}]
        report = validator.validate_code(changes, "")

        print_findings(report.findings)
        assert len(report.findings) > 0, f"Test {i}: Expected findings but got none"
        assert any(f.severity in ["high", "medium"] for f in report.findings), f"Test {i}: Expected security issue"

    print(f"\n✅ All {len(test_cases)} security tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Performance Anti-patterns
# ─────────────────────────────────────────────────────────────────────────────

def test_performance_antipatterns():
    """Test detection of performance anti-patterns."""
    print_header("TEST 2: PERFORMANCE ANTI-PATTERNS")

    test_cases = [
        {
            "name": "range(len()) instead of enumerate()",
            "path": "perf/range_len.py",
            "content": """
items = [1, 2, 3, 4, 5]
for i in range(len(items)):  # MEDIUM: use enumerate() instead
    print(f"{i}: {items[i]}")
"""
        },
        {
            "name": "list(map()) instead of comprehension",
            "path": "perf/list_map.py",
            "content": """
numbers = [1, 2, 3, 4, 5]
squared = list(map(lambda x: x**2, numbers))  # MEDIUM: use list comprehension
"""
        },
        {
            "name": "list(filter()) instead of comprehension",
            "path": "perf/list_filter.py",
            "content": """
numbers = [1, 2, 3, 4, 5]
evens = list(filter(lambda x: x % 2 == 0, numbers))  # MEDIUM: use comprehension
"""
        },
        {
            "name": "N+1 Database Query Problem",
            "path": "perf/n_plus_one.py",
            "content": """
for user in users:
    posts = db.query(Post).filter(Post.user_id == user.id).all()  # HIGH: N+1 problem
    print(f"{user.name}: {len(posts)} posts")
"""
        },
        {
            "name": "Save in loop (should use bulk_create)",
            "path": "perf/loop_save.py",
            "content": """
for i in range(1000):
    obj = MyModel(data=i)
    obj.save()  # MEDIUM: should use bulk_create
"""
        },
        {
            "name": "Loading entire file into memory",
            "path": "perf/json_mem.py",
            "content": """
import json
data = json.loads(open('large_file.json').read())  # MEDIUM: loads entire file to memory
"""
        },
    ]

    validator = StaticValidatorV2()

    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        changes = [{"path": test["path"], "content": test["content"]}]
        report = validator.validate_code(changes, "")

        print_findings(report.findings)
        assert len(report.findings) > 0, f"Test {i}: Expected findings but got none"
        assert any("performance" in f.check for f in report.findings), f"Test {i}: Expected performance issue"

    print(f"\n✅ All {len(test_cases)} performance tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Code Quality & Best Practices
# ─────────────────────────────────────────────────────────────────────────────

def test_code_quality():
    """Test detection of code quality issues."""
    print_header("TEST 3: CODE QUALITY & BEST PRACTICES")

    test_cases = [
        {
            "name": "Bare except (catches everything)",
            "path": "quality/bare_except.py",
            "content": """
try:
    dangerous_operation()
except:  # HIGH: bare except masks all errors
    pass
"""
        },
        {
            "name": "Generic Exception catch",
            "path": "quality/generic_except.py",
            "content": """
try:
    process_data()
except Exception:  # MEDIUM: too broad, catch specific exceptions
    print("Something went wrong")
"""
        },
        {
            "name": "print() instead of logging",
            "path": "quality/print_logging.py",
            "content": """
print("User logged in")  # LOW: use logger instead of print
print(f"Processing {item_count} items")  # LOW
print("Debug info:", debug_data)  # LOW
"""
        },
        {
            "name": "Wildcard import",
            "path": "quality/wildcard_import.py",
            "content": """
from my_module import *  # MEDIUM: unclear what symbols are imported
from utils import *  # MEDIUM
"""
        },
        {
            "name": "Magic numbers without constants",
            "path": "quality/magic_numbers.py",
            "content": """
if user_age > 18:  # LOW: magic number
    show_adult_content()

timeout = 300  # LOW: magic number
request_timeout(timeout)

MAX_RETRIES = 500  # LOW: magic number for retries
"""
        },
        {
            "name": "Global state mutation",
            "path": "quality/global_state.py",
            "content": """
counter = 0

def increment():
    global counter  # MEDIUM: avoid global state
    counter += 1
"""
        },
        {
            "name": "TODO/FIXME debt markers",
            "path": "quality/technical_debt.py",
            "content": """
def calculate_total():
    # TODO: optimize this loop
    for item in items:
        total += item.price

    # FIXME: handle edge case
    if total > 1000:
        apply_discount()
"""
        },
    ]

    validator = StaticValidatorV2()

    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        changes = [{"path": test["path"], "content": test["content"]}]
        report = validator.validate_code(changes, "")

        print_findings(report.findings)
        assert len(report.findings) > 0, f"Test {i}: Expected findings but got none"
        assert any("quality" in f.check or "except" in f.check for f in report.findings), \
            f"Test {i}: Expected quality issue"

    print(f"\n✅ All {len(test_cases)} quality tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Missing Documentation
# ─────────────────────────────────────────────────────────────────────────────

def test_documentation():
    """Test detection of missing documentation."""
    print_header("TEST 4: MISSING DOCUMENTATION")

    test_cases = [
        {
            "name": "Module without docstring",
            "path": "docs/no_module_doc.py",
            "content": """
import os
import sys

def main():
    pass
"""
        },
        {
            "name": "Public function without docstring",
            "path": "docs/no_func_doc.py",
            "content": """
def process_data(input_data):
    result = []
    for item in input_data:
        result.append(item * 2)
    return result

def _helper():  # Private function, OK
    pass
"""
        },
        {
            "name": "Class without docstring",
            "path": "docs/no_class_doc.py",
            "content": """
class UserManager:
    def __init__(self, db):
        self.db = db

    def _helper(self):  # Private method, OK
        pass
"""
        },
        {
            "name": "Function without type hints",
            "path": "docs/no_type_hints.py",
            "content": """
def add(a, b):  # MEDIUM: missing type hints
    return a + b

def _private_func():  # OK - private
    pass

def get_user_data(user_id):  # MEDIUM: missing type hints
    return db.query(user_id)
"""
        },
    ]

    validator = StaticValidatorV2()

    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        changes = [{"path": test["path"], "content": test["content"]}]
        report = validator.validate_code(changes, "")

        print_findings(report.findings)
        assert len(report.findings) > 0, f"Test {i}: Expected findings but got none"
        assert any("docstring" in f.check or "type_hints" in f.check for f in report.findings), \
            f"Test {i}: Expected documentation issue"

    print(f"\n✅ All {len(test_cases)} documentation tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Ecosystem & Configuration Issues
# ─────────────────────────────────────────────────────────────────────────────

def test_ecosystem_issues():
    """Test detection of ecosystem and configuration problems."""
    print_header("TEST 5: ECOSYSTEM & CONFIGURATION ISSUES")

    test_cases = [
        {
            "name": "Sensitive .env file exposed",
            "path": ".env",
            "content": """API_KEY=sk-1234567890
DB_PASSWORD=super_secret
AWS_SECRET_ACCESS_KEY=abc123def456
"""
        },
        {
            "name": "Docker :latest tag (version pinning)",
            "path": "Dockerfile",
            "content": """FROM ubuntu:latest
RUN apt-get update
RUN apt-get install -y python3
EXPOSE 8000
CMD ["python3", "app.py"]
"""
        },
        {
            "name": "Docker container running as root",
            "path": "Dockerfile.prod",
            "content": """FROM python:3.11
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
USER root
EXPOSE 5000
CMD ["python", "app.py"]
"""
        },
        {
            "name": "Unpinned dependencies in requirements.txt",
            "path": "requirements.txt",
            "content": """numpy>=1.20
pandas
requests>=2.25.0
flask~=2.0
django
"""
        },
        {
            "name": "Hardcoded credentials in config",
            "path": "config.yaml",
            "content": """database:
  host: localhost
  user: admin
  password: hardcoded_password_123

api:
  key: "sk-1234567890abcdef"
  secret: "my_secret_key"
"""
        },
    ]

    validator = StaticValidatorV2()

    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        changes = [{"path": test["path"], "content": test["content"]}]
        report = validator.validate_code(changes, "")

        print_findings(report.findings)
        assert len(report.findings) > 0, f"Test {i}: Expected findings but got none"

    print(f"\n✅ All {len(test_cases)} ecosystem tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Cross-File Issues
# ─────────────────────────────────────────────────────────────────────────────

def test_crossfile_issues():
    """Test detection of issues spanning multiple files."""
    print_header("TEST 6: CROSS-FILE ISSUES")

    print("\n  Test 1: Circular imports detection")
    circular_changes = [
        {"path": "module_a.py", "content": "from module_b import b_func"},
        {"path": "module_b.py", "content": "from module_a import a_func"},
    ]
    validator = StaticValidatorV2()
    report = validator.validate_code(circular_changes, "")
    print_findings(report.findings)
    assert any("circular" in f.check for f in report.findings), "Expected circular import detection"
    print("  ✅ Circular import test passed")

    print("\n  Test 2: Test coverage detection")
    coverage_changes = [
        {"path": "app.py", "content": """
def get_user(user_id):
    return db.query(user_id)

def create_user(name):
    return db.create(name)

def delete_user(user_id):
    return db.delete(user_id)
"""},
        {"path": "test_app.py", "content": "def test_get_user(): pass"},
    ]
    report2 = validator.validate_code(coverage_changes, "")
    print_findings(report2.findings)
    assert any("coverage" in f.check for f in report2.findings), "Expected test coverage warning"
    print("  ✅ Test coverage test passed")

    print("\n✅ All cross-file tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Configuration Features
# ─────────────────────────────────────────────────────────────────────────────

def test_configuration_features():
    """Test validator configuration features."""
    print_header("TEST 7: VALIDATOR CONFIGURATION FEATURES")

    code_with_issues = [{"path": "test.py", "content": "eval('1+1')\nprint('hi')\nfor i in range(len([1,2])): pass"}]

    print("\n  Test 1: Disabling specific checks")
    v_disabled = StaticValidatorV2(disabled_checks={"security:eval_rce"})
    report = v_disabled.validate_code(code_with_issues, "")
    eval_findings = [f for f in report.findings if "eval" in f.check]
    assert len(eval_findings) == 0, "eval_rce should be disabled"
    print(f"    Found {len(report.findings)} findings (eval_rce disabled)")
    print("  ✅ Disabling checks works")

    print("\n  Test 2: Severity override (upgrade)")
    v_upgrade = StaticValidatorV2(severity_overrides={"range_len": "critical"})
    report2 = v_upgrade.validate_code(code_with_issues, "")
    critical_findings = [f for f in report2.findings if f.severity == "critical"]
    assert len(critical_findings) > 0, "range_len should be critical"
    print(f"    Found {len(critical_findings)} critical findings (range_len upgraded)")
    print("  ✅ Severity upgrade works")

    print("\n  Test 3: Severity override (ignore with None)")
    v_ignore = StaticValidatorV2(severity_overrides={"print_stmt": None})
    report3 = v_ignore.validate_code(code_with_issues, "")
    print_findings = [f for f in report3.findings if "print" in f.check]
    assert len(print_findings) == 0, "print_stmt should be ignored"
    print(f"    Found {len(report3.findings)} findings (print_stmt ignored)")
    print("  ✅ Severity ignore (None) works")

    print("\n✅ All configuration tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: Run all tests
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  COMPREHENSIVE VALIDATOR2.PY TEST SUITE")
    print("  Testing all check categories with intentional anti-patterns")
    print("="*70)

    try:
        test_security_vulnerabilities()
        test_performance_antipatterns()
        test_code_quality()
        test_documentation()
        test_ecosystem_issues()
        test_crossfile_issues()
        test_configuration_features()

        print("\n" + "="*70)
        print("  ✅ ALL TESTS PASSED")
        print("  validator2.py is working correctly across all categories")
        print("="*70 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)
