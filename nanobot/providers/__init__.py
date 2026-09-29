"""LLM provider interfaces and implementations."""

from importlib import import_module

from nanobot.providers.base import LLMProvider, LLMResponse


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAICompatProvider",
]


_LAZY_IMPORTS = {
    "OpenAICompatProvider": ".openai_compat_provider",
}


def __getattr__(name: str):
    """Lazily import provider implementations."""
    module_name = _LAZY_IMPORTS.get(name)

    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value