"""Allowlist-only, non-persistent provider connectivity tests."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import Request


_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_MAX_RESPONSE_BYTES = 64 * 1024
_CONNECT_TIMEOUT_SECONDS = 10
_TOTAL_TIMEOUT_SECONDS = 20
_MAX_CONCURRENT_TESTS = 8


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    body: bytes


@dataclass(frozen=True)
class ProviderTestResult:
    ok: bool
    message: str


class ProviderTransport(Protocol):
    async def post(self, url: str, headers: dict[str, str], body: bytes) -> ProviderResponse: ...


class ProviderTestConfigurationError(ValueError):
    """A provider, model, credential, or endpoint violates the safe policy."""


class ResponseTooLargeError(RuntimeError):
    """The provider returned more data than a connectivity check needs."""


class HttpxProviderTransport:
    """Shared cancellation-aware HTTP transport for one FastAPI application."""

    def __init__(
        self,
        *,
        connect_timeout_seconds: float = _CONNECT_TIMEOUT_SECONDS,
        total_timeout_seconds: float = _TOTAL_TIMEOUT_SECONDS,
        max_concurrent_tests: int = _MAX_CONCURRENT_TESTS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._total_timeout_seconds = total_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent_tests)
        limits = httpx.Limits(
            max_connections=max_concurrent_tests,
            max_keepalive_connections=max_concurrent_tests,
        )
        timeout = httpx.Timeout(
            connect=connect_timeout_seconds, read=None, write=connect_timeout_seconds, pool=connect_timeout_seconds
        )
        self._client = client or httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0, verify=True, limits=limits),
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )
        self._owns_client = client is None

    async def post(self, url: str, headers: dict[str, str], body: bytes) -> ProviderResponse:
        """Send one bounded request; cancellation closes its socket in ``finally``."""

        self._validate_canonical_url(url)
        async with self._semaphore:
            async with asyncio.timeout(self._total_timeout_seconds):
                async with self._client.stream("POST", url, headers=headers, content=body) as response:
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > _MAX_RESPONSE_BYTES:
                            raise ResponseTooLargeError()
                    return ProviderResponse(response.status_code, bytes(payload))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _validate_canonical_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
            raise ValueError("Only canonical HTTPS endpoints are supported.")
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError("Only canonical HTTPS endpoints are supported.")


class ProviderTestService:
    """Build and execute one safe, minimal request for a supported provider."""

    def __init__(self, transport: ProviderTransport | None = None) -> None:
        self._transport = transport or HttpxProviderTransport()

    async def aclose(self) -> None:
        close = getattr(self._transport, "aclose", None)
        if close is not None:
            await close()

    async def test(
        self, *, provider: str, model: str, api_key: str, base_url: str | None = None
    ) -> ProviderTestResult:
        try:
            url, headers, payload = self._request_parts(provider, model, api_key, base_url)
        except ProviderTestConfigurationError:
            return ProviderTestResult(False, "Provider test configuration is not permitted.")

        try:
            response = await self._transport.post(url, headers, payload)
        except asyncio.TimeoutError:
            return ProviderTestResult(False, "Provider test timed out.")
        except ResponseTooLargeError:
            return ProviderTestResult(False, "Provider response exceeded the permitted size.")
        except (httpx.HTTPError, OSError, ValueError):
            return ProviderTestResult(False, "Provider connection failed.")
        except Exception:
            # Third-party/injected transport failures must never be reflected.
            return ProviderTestResult(False, "Provider connection failed.")

        if 200 <= response.status_code < 300:
            return ProviderTestResult(True, "Provider connection succeeded.")
        return ProviderTestResult(False, "Provider rejected the test request.")

    def _request_parts(
        self, provider: str, model: str, api_key: str, base_url: str | None
    ) -> tuple[str, dict[str, str], bytes]:
        normalized_provider = provider.strip().casefold() if isinstance(provider, str) else ""
        if (
            not isinstance(model, str)
            or not _MODEL_PATTERN.fullmatch(model)
            or not isinstance(api_key, str)
            or not api_key
        ):
            raise ProviderTestConfigurationError()

        if normalized_provider == "anthropic":
            self._validate_base(base_url, "api.anthropic.com", {"", "/"})
            return (
                "https://api.anthropic.com/v1/messages",
                {
                    "content-type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json.dumps(
                    {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
                ).encode("utf-8"),
            )
        if normalized_provider == "openrouter":
            self._validate_base(base_url, "openrouter.ai", {"", "/", "/api/v1", "/api/v1/"})
            return self._chat_request("https://openrouter.ai/api/v1/chat/completions", model, api_key)
        if normalized_provider == "openai":
            self._validate_base(base_url, "api.openai.com", {"", "/", "/v1", "/v1/"})
            return self._chat_request("https://api.openai.com/v1/chat/completions", model, api_key)
        raise ProviderTestConfigurationError()

    @staticmethod
    def _chat_request(url: str, model: str, api_key: str) -> tuple[str, dict[str, str], bytes]:
        return (
            url,
            {"content-type": "application/json", "authorization": f"Bearer {api_key}"},
            json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0,
                }
            ).encode("utf-8"),
        )

    @staticmethod
    def _validate_base(base_url: str | None, expected_host: str, allowed_paths: set[str]) -> None:
        if base_url is None or base_url == "":
            return
        if not isinstance(base_url, str):
            raise ProviderTestConfigurationError()
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError as exc:
            raise ProviderTestConfigurationError() from exc
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.hostname is None
            or parsed.hostname.casefold().rstrip(".") != expected_host
            or port not in (None, 443)
            or parsed.path not in allowed_paths
        ):
            raise ProviderTestConfigurationError()


def get_provider_test_service(request: Request) -> ProviderTestService:
    """FastAPI dependency; tests override it with an in-memory transport."""

    return request.app.state.provider_test_service
