"""Provider-agnostic LLM client with rate limiting and 429 backoff."""
import asyncio
import json
import re
import time


class LLMError(Exception):
    pass


class DailyQuotaError(Exception):
    """Raised when the provider's per-day request budget is exhausted."""


def classify_llm_error(exc: Exception) -> str:
    text = str(exc).lower()
    compact = text.replace("_", "")
    if "perday" in compact or "requestsperday" in compact or "per-day" in text:
        return "daily"
    if "retry in" in text and ("day" in text or "hour" in text):
        return "daily"
    if "429" in str(exc) or "resource_exhausted" in text or "quota" in text:
        return "rate"
    return "other"


class RateLimiter:
    def __init__(self, rpm: int):
        self.min_interval = 60.0 / max(rpm, 1)
        self._last = 0.0

    async def acquire(self) -> None:
        now = time.monotonic()
        wait = self._last + self.min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()


async def retry_429(fn, attempts: int = 6):
    delay = 2.0
    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            kind = classify_llm_error(exc)
            if kind == "daily":
                raise DailyQuotaError(str(exc)) from exc
            if kind == "rate":
                last_exc = exc
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            raise
    raise LLMError(f"rate limited after {attempts} retries: {last_exc}")


class GeminiBackend:
    def __init__(self, api_key: str, model: str):
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, system: str | None = None) -> str:
        config = (
            self._types.GenerateContentConfig(system_instruction=system)
            if system
            else None
        )
        resp = await self._client.aio.models.generate_content(
            model=self.model, contents=prompt, config=config
        )
        return resp.text or ""


class StubBackend:
    """Test double: returns canned responses (str or callable(prompt)->str)."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[str] = []

    async def complete(self, prompt: str, system: str | None = None) -> str:
        self.calls.append(prompt)
        if not self.responses:
            return "{}"
        item = self.responses.pop(0)
        return item(prompt) if callable(item) else item


def parse_json_loose(text: str):
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = fence.group(1) if fence else text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    embedded = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
    if not embedded:
        raise json.JSONDecodeError("no JSON object found", raw, 0)
    body = re.sub(r",\s*([}\]])", r"\1", embedded.group(1))
    return json.loads(body)


class LLMClient:
    def __init__(self, settings=None, backend=None):
        if settings is None:
            from pipeline.config import Settings

            settings = Settings.from_env()
        self._settings = settings
        self.backend = backend or GeminiBackend(settings.api_key, settings.model)
        self.limiter = RateLimiter(settings.rpm)
        self._injected_backend = backend is not None

    def _backend_for(self, model: str):
        if self._injected_backend:
            return self.backend
        return GeminiBackend(self._settings.api_key, model)

    async def generate(self, prompt: str, system: str | None = None) -> str:
        if self._injected_backend:
            await self.limiter.acquire()
            return await retry_429(
                lambda: self._backend_for(self._settings.model).complete(prompt, system)
            )
        models = [self._settings.model] + list(self._settings.model_fallbacks)
        last_daily: DailyQuotaError | None = None
        for model in models:
            backend = self._backend_for(model)
            try:
                await self.limiter.acquire()
                return await retry_429(lambda: backend.complete(prompt, system))
            except DailyQuotaError as exc:
                last_daily = exc
                continue
        raise LLMError(f"daily quota exhausted on all models: {last_daily}")

    async def generate_json(self, prompt: str, system: str | None = None):
        text = await self.generate(prompt, system)
        if isinstance(text, (dict, list)):  # stub backends may return parsed JSON
            return text
        try:
            return parse_json_loose(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned invalid JSON: {exc}\n{text[:500]}") from exc
