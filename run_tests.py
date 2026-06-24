#!/usr/bin/env python3.12
"""Simple test runner (without pytest dependency)."""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add paths
ROOT = Path(__file__).parent

# Import test modules
from vibelike.tests import test_queue, test_tools, test_sandbox, test_adapters, test_requests


def run_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("VIBELIKE TEST SUITE")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    test_modules = [
        ("Queue Tests", test_queue),
        ("Tools Tests", test_tools),
        ("Sandbox Tests", test_sandbox),
        ("Adapters Tests", test_adapters),
        ("Requests Tests", test_requests),
    ]

    total_tests = 0
    total_passed = 0
    total_failed = 0
    results = []

    for module_name, module in test_modules:
        print(f"\n[{module_name}]")
        print("-" * 70)

        # Get all test functions
        test_funcs = [
            (name, getattr(module, name))
            for name in dir(module)
            if name.startswith("test_") and callable(getattr(module, name))
        ]

        module_passed = 0
        module_failed = 0

        for test_name, test_func in test_funcs:
            try:
                # Check if it needs fixtures
                import inspect
                sig = inspect.signature(test_func)
                params = list(sig.parameters.keys())

                # For now, skip tests that need fixtures
                if len(params) > 0:
                    # Try to create fixtures
                    if "tmp_path" in params:
                        import tempfile
                        with tempfile.TemporaryDirectory() as tmp:
                            test_func(Path(tmp))
                    else:
                        # Skip tests with fixtures we can't provide
                        print(f"  ⊘ {test_name:50} SKIPPED (needs fixtures)")
                        continue
                else:
                    test_func()

                print(f"  ✓ {test_name:50} PASSED")
                module_passed += 1
                total_passed += 1
            except Exception as e:
                print(f"  ✗ {test_name:50} FAILED")
                print(f"      Error: {str(e)[:60]}")
                module_failed += 1
                total_failed += 1

            total_tests += 1

        # Module summary
        if module_failed == 0:
            print(f"\n  ✓ {module_name}: {module_passed} passed")
        else:
            print(f"\n  ✗ {module_name}: {module_passed} passed, {module_failed} failed")

        results.append((module_name, module_passed, module_failed))

    # Final summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for module_name, passed, failed in results:
        status = "✓" if failed == 0 else "✗"
        print(f"{status} {module_name:40} {passed} passed, {failed} failed")

    print("\n" + "-" * 70)
    if total_failed == 0:
        print(f"✓ ALL TESTS PASSED: {total_passed}/{total_tests}")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED: {total_passed}/{total_tests} passed, {total_failed} failed")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
