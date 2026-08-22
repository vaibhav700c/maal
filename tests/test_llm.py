import time

import pytest

from pipeline.llm import (
    LLMClient,
    RateLimiter,
    StubBackend,
    parse_json_loose,
    retry_429,
)


async def test_rate_limiter_enforces_min_interval():
    limiter = RateLimiter(rpm=600)  # 0.1s min interval
    t0 = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    assert time.monotonic() - t0 >= 0.09


class QuotaThenOk:
    def __init__(self):
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
        return "ok"


async def test_retry_429_recovers_on_quota_error(monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr("pipeline.llm.asyncio.sleep", fast_sleep)
    fn = QuotaThenOk()
    assert await retry_429(fn, attempts=3) == "ok"
    assert fn.calls == 2


async def test_retry_429_reraises_other_errors():
    async def bad():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await retry_429(bad, attempts=2)


def test_parse_json_loose_handles_fences_and_trailing_comma():
    assert parse_json_loose('```json\n{"a": 1,}\n```') == {"a": 1}
    assert parse_json_loose('plain {"b": [1, 2]} here') == {"b": [1, 2]}


async def test_client_generate_json_with_stub_backend():
    backend = StubBackend(responses=['```json\n{"ok": true,}\n```'])
    client = LLMClient(backend=backend)
    result = await client.generate_json("prompt")
    assert result == {"ok": True}
    assert backend.calls == ["prompt"]
