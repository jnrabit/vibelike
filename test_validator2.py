from vibelike.validator2 import StaticValidatorV2


def _check_line(code: str) -> bool:
    v = StaticValidatorV2()
    report = v.validate_code([{"path": "x.py", "content": code}], "")
    return any(f.check == "security:none_comparison" for f in report.findings)


def test_none_comparison_flags():
    assert _check_line("if x == None:\n    pass\n")


def test_none_comparison_flags_negative():
    assert not _check_line("if x is None:\n    pass\n")


def test_not_none_comparison_flags():
    assert _check_line("if x != None:\n    pass\n")


def test_not_none_comparison_flags_negative():
    assert not _check_line("if x is not None:\n    pass\n")
