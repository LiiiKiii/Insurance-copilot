"""
Provider registry for LLM provider metadata.

A1 currently enables OpenRouter through the OpenAI-compatible backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic.alias_generators import to_snake


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata describing one LLM provider."""

    # Identity
    name: str
    keywords: tuple[str, ...]
    env_key: str
    display_name: str = ""

    # Provider implementation
    backend: str = "openai_compat"

    # Additional environment variables
    env_extras: tuple[tuple[str, str], ...] = ()

    # Gateway / local detection
    is_gateway: bool = False
    is_local: bool = False
    detect_by_key_prefix: str = ""
    detect_by_base_keyword: str = ""
    default_api_base: str = ""

    # Gateway behavior
    strip_model_prefix: bool = False

    # Per-model parameter overrides
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    # Provider characteristics
    is_oauth: bool = False
    is_direct: bool = False
    supports_prompt_caching: bool = False

    @property
    def label(self) -> str:
        """Return the provider's display label."""
        return self.display_name or self.name.title()


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        backend="openai_compat",
        env_extras=(),
        is_gateway=True,
        is_local=False,
        detect_by_key_prefix="sk-or-",
        detect_by_base_keyword="openrouter",
        default_api_base="https://openrouter.ai/api/v1",
        strip_model_prefix=False,
        model_overrides=(),
        is_oauth=False,
        is_direct=False,
        supports_prompt_caching=True,
    ),
)


def find_by_name(name: str) -> ProviderSpec | None:
    """Find a provider specification by config field name."""
    normalized = to_snake(name.replace("-", "_"))

    for spec in PROVIDERS:
        if spec.name == normalized:
            return spec

    return None


def find_by_model(model: str) -> ProviderSpec | None:
    """Find a provider specification using model-name keywords."""
    model_lower = model.lower()

    for spec in PROVIDERS:
        for keyword in spec.keywords:
            if keyword in model_lower:
                return spec

    return None


def find_gateway(
    provider_name: str | None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> ProviderSpec | None:
    """Detect a gateway provider from its name, API key, or API base URL."""

    if provider_name:
        spec = find_by_name(provider_name)

        if spec and (spec.is_gateway or spec.is_local):
            return spec

    if api_key:
        for spec in PROVIDERS:
            if (
                spec.detect_by_key_prefix
                and api_key.startswith(spec.detect_by_key_prefix)
            ):
                return spec

    if api_base:
        base_lower = api_base.lower()

        for spec in PROVIDERS:
            if (
                spec.detect_by_base_keyword
                and spec.detect_by_base_keyword in base_lower
            ):
                return spec

    return None