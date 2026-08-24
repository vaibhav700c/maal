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
    if (
        "429" in str(exc)
        or "resource_exhausted" in text
        or "quota" in text
        or "503" in str(exc)
        or "unavailable" in text
        or "high demand" in text
        or "500" in str(exc)
        or "internal error" in text
        or "deadline" in text
    ):
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

    async def complete_grounded(self, prompt: str, system: str | None = None) -> tuple[str, list[str]]:
        """Gemini with Google Search grounding. Returns (text, source_urls)."""
        config_kwargs = {"tools": [{"google_search": {}}]}
        if system:
            config_kwargs["system_instruction"] = system
        config = self._types.GenerateContentConfig(**config_kwargs)

        resp = await self._client.aio.models.generate_content(
            model=self.model, contents=prompt, config=config
        )

        text = resp.text or ""
        urls = []
        # Extract grounding metadata (source URLs Gemini used)
        if hasattr(resp, "candidates") and resp.candidates:
            cand = resp.candidates[0]
            if hasattr(cand, "grounding_metadata") and cand.grounding_metadata:
                gm = cand.grounding_metadata
                if hasattr(gm, "grounding_chunks") and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, "web") and chunk.web and hasattr(chunk.web, "uri"):
                            if chunk.web.uri not in urls:
                                urls.append(chunk.web.uri)
        return text, urls


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


import hashlib
import json as _json
from pathlib import Path


class ResponseCache:
    """Disk-backed prompt->response cache. Same prompt (+model) never pays
    tokens twice, across runs. Enabled by default; LLM_CACHE=0 disables."""

    def __init__(self, path: Path | None = None, enabled: bool | None = None):
        import os

        if enabled is None:
            enabled = os.environ.get("LLM_CACHE", "1") != "0"
        self.enabled = enabled
        self.path = path or Path("output/cache/llm-responses.json")
        self._data: dict[str, str] = {}
        if self.enabled and self.path.exists():
            try:
                self._data = _json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    @staticmethod
    def key(model: str, prompt: str, system: str | None) -> str:
        blob = f"{model}\x00{system or ''}\x00{prompt}"
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(_json.dumps(self._data))


class LLMClient:
    def __init__(self, settings=None, backend=None):
        if settings is None:
            from pipeline.config import Settings

            settings = Settings.from_env()
        self._settings = settings
        if not settings.model_fallbacks and not backend:
            # proven working chain when no explicit config is provided
            settings.model_fallbacks = [
                "gemini-flash-latest",
                "gemini-flash-lite-latest",
            ]
            if settings.model == "gemini-2.5-flash":
                settings.model = "gemini-3.1-flash-lite"
        self.backend = backend or GeminiBackend(settings.api_key, settings.model)
        self.limiter = RateLimiter(settings.rpm)
        self._injected_backend = backend is not None
        # stub backends stay uncached so tests keep sequencing control
        self.cache = None if backend is not None else ResponseCache()

    def _backend_for(self, model: str):
        if self._injected_backend:
            return self.backend
        return GeminiBackend(self._settings.api_key, model)

    async def generate(self, prompt: str, system: str | None = None) -> str:
        cache_key = None
        if self.cache is not None:
            model_id = getattr(self.backend, "model", "") or self._settings.model
            cache_key = ResponseCache.key(model_id, prompt, system)
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit
        result = await self._generate_uncached(prompt, system, cache_key)
        if self.cache is not None and cache_key:
            self.cache.put(cache_key, result)
        return result

    async def _generate_uncached(
        self, prompt: str, system: str | None, cache_key: str | None = None
    ) -> str:
        if self._injected_backend:
            await self.limiter.acquire()
            return await retry_429(
                lambda: self._backend_for(self._settings.model).complete(prompt, system)
            )
        models = [self._settings.model] + list(self._settings.model_fallbacks)
        errors: list[str] = []
        for model in models:
            backend = self._backend_for(model)
            try:
                await self.limiter.acquire()
                return await retry_429(lambda: backend.complete(prompt, system))
            except DailyQuotaError as exc:
                errors.append(f"{model}: daily quota")
                continue
            except LLMError as exc:
                errors.append(f"{model}: {exc}")
                continue
        raise LLMError("all models failed -> " + " | ".join(errors))

    async def generate_json(self, prompt: str, system: str | None = None):
        text = await self.generate(prompt, system)
        if isinstance(text, (dict, list)):  # stub backends may return parsed JSON
            return text
        try:
            return parse_json_loose(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned invalid JSON: {exc}\n{text[:500]}") from exc
