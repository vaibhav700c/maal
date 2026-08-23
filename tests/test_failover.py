from pipeline.llm import (
    DailyQuotaError,
    LLMClient,
    RateLimiter,
    StubBackend,
    classify_llm_error,
)
from pipeline.config import Settings


def test_classify_llm_error_kinds():
    daily = RuntimeError(
        "429 ... Quota exceeded for metric: generate_content_free_tier_requests, "
        "limit: 20 ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    )
    assert classify_llm_error(daily) == "daily"
    rate = RuntimeError("429 RESOURCE_EXHAUSTED please retry in 2s")
    assert classify_llm_error(rate) == "rate"
    other = ValueError("bad request")
    assert classify_llm_error(other) == "other"


class _QuotaBackend:
    def __init__(self):
        self.models_used = []

    def __call__(self, model: str):
        me = self

        class B:
            async def complete(self, prompt, system=None):
                me.models_used.append(model)
                if model == "model-a":
                    raise DailyQuotaError("per-day quota exhausted")
                return '{"ok": "' + model + '"}'

        return B()


async def test_client_fails_over_on_daily_quota(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate the on-disk response cache from other runs
    settings = Settings(
        api_key="k", model="model-a", model_fallbacks=["model-b"],
        rpm=6000,
        input_csv=None or "", expected_headers_csv="", output_dir="",
    )
    client = LLMClient(settings, backend=None)
    quota_backend = _QuotaBackend()
    monkeypatch.setattr(client, "_backend_for", quota_backend)

    async def no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.llm.asyncio.sleep", no_sleep)
    out = await client.generate_json('say {"a": 1}')
    # backend returns plain string; generate_json parses it
    assert out == {"ok": "model-b"}
    assert quota_backend.models_used == ["model-a", "model-b"]


async def test_stub_backend_path_unchanged():
    client = LLMClient(backend=StubBackend(responses=['{"x": 2}']))
    assert (await client.generate_json("p")) == {"x": 2}


async def test_extract_many_reraises_quota_errors():
    from pipeline.extract import extract_many
    from pipeline.models import CleanRow

    from pipeline.llm import LLMError

    class DeadLLM:
        async def generate_json(self, prompt, system=None):
            raise LLMError("all models failed -> daily quota")

    rows = [CleanRow(mfg_part_num="X1", part_desc="disc")]
    try:
        await extract_many(DeadLLM(), [(rows[0], None, None)], batch=8)
        raise SystemExit("should have raised")
    except Exception as exc:
        assert "all models failed" in str(exc)
