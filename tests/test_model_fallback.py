"""Tests für die Local-First-Fallback-Kette (model_fallback.py)."""

import pytest

from errors import (
    ModelError,
    ModelNotAvailableError,
    ModelQuotaExceededError,
    ModelTimeoutError,
)
from model_fallback import FallbackCoder, classify_model_exception


# ───────────────────────── classify_model_exception ─────────────────────────

class FakeRateLimitError(Exception):
    pass


class FakeResourceExhausted(Exception):
    pass


def test_classify_by_classname_quota():
    err = classify_model_exception(FakeRateLimitError("boom"))
    assert isinstance(err, ModelQuotaExceededError)


def test_classify_resource_exhausted_classname():
    err = classify_model_exception(FakeResourceExhausted("gemini limit"))
    assert isinstance(err, ModelQuotaExceededError)


def test_classify_by_message_credit_balance():
    err = classify_model_exception(Exception("Your credit balance is too low"))
    assert isinstance(err, ModelQuotaExceededError)


def test_classify_by_message_429():
    err = classify_model_exception(Exception("[ERR] Error code: 429 too many requests"))
    assert isinstance(err, ModelQuotaExceededError)


def test_classify_timeout():
    err = classify_model_exception(Exception("Request timed out after 60s"))
    assert isinstance(err, ModelTimeoutError)


def test_classify_unavailable():
    err = classify_model_exception(Exception("503 service unavailable"))
    assert isinstance(err, ModelNotAvailableError)


def test_classify_unknown_returns_none():
    assert classify_model_exception(Exception("some unrelated parse error")) is None


# ───────────────────────────── FallbackCoder ────────────────────────────────

class RaisingPrimary:
    """Cloud-Coder der bei raise_on_quota Quota wirft (wie ClaudeCoder mit Flag)."""

    usable = True

    def __init__(self, exc):
        self._exc = exc
        self.calls = 0

    def generate(self, prompt, raise_on_quota=False, **kwargs):
        self.calls += 1
        if raise_on_quota:
            raise self._exc
        return "[ERR] swallowed"


class StringErrPrimary:
    """Älterer Coder der raise_on_quota NICHT kennt und [ERR]-String zurückgibt."""

    usable = True

    def __init__(self, msg):
        self._msg = msg
        self.calls = 0

    def generate(self, prompt, **kwargs):  # kein raise_on_quota → TypeError-Pfad
        self.calls += 1
        return self._msg


class LocalFallback:
    usable = True

    def __init__(self):
        self.calls = 0
        self.last_kwargs = None

    def generate(self, prompt, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return f"LOCAL:{prompt}"


class GoodPrimary:
    usable = True

    def generate(self, prompt, raise_on_quota=False, **kwargs):
        return f"CLOUD:{prompt}"


def test_fallback_on_quota_exception():
    primary = RaisingPrimary(ModelQuotaExceededError("credit balance too low"))
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    out = fc.generate("write code")
    assert out == "LOCAL:write code"
    assert local.calls == 1
    # raise_on_quota darf NICHT ans lokale Modell durchgereicht werden
    assert "raise_on_quota" not in local.last_kwargs


def test_quota_is_sticky():
    primary = RaisingPrimary(ModelQuotaExceededError("429"))
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    fc.generate("first")
    fc.generate("second")
    # Nach erstem Quota-Hit: Cloud wird nicht erneut versucht (sticky)
    assert primary.calls == 1
    assert local.calls == 2


def test_timeout_not_sticky():
    primary = RaisingPrimary(ModelTimeoutError("timed out"))
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    fc.generate("a")
    fc.generate("b")
    # Timeout ist transient → Cloud bei jedem Call erneut versucht
    assert primary.calls == 2
    assert local.calls == 2


def test_string_err_primary_triggers_fallback():
    primary = StringErrPrimary("[ERR] Error code: 429 rate limit exceeded")
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    out = fc.generate("x")
    assert out == "LOCAL:x"


def test_string_err_unrelated_does_not_fallback():
    primary = StringErrPrimary("[ERR] some parse glitch")
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    out = fc.generate("x")
    # Nicht-Quota-[ERR] → KEIN Fallback, String durchgereicht
    assert out.startswith("[ERR]")
    assert local.calls == 0


def test_happy_path_no_fallback():
    primary = GoodPrimary()
    local = LocalFallback()
    fc = FallbackCoder(primary, local)

    out = fc.generate("hello")
    assert out == "CLOUD:hello"
    assert local.calls == 0
