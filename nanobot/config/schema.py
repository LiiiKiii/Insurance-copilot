
"""Runtime configuration schema for the A1 platform foundation."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Accept both camelCase and snake_case configuration keys."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class AgentDefaults(Base):
    """Default configuration for the agent runtime."""

    workspace: str = "~/.nanobot/workspace"
    model: str = "openai/gpt-4o-mini"
    provider: str = "openrouter"

    max_tokens: int = 8192
    context_window_tokens: int = 65536
    temperature: float = 0.1
    reasoning_effort: str | None = None


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """Configuration for one LLM provider."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(Base):
    """LLM providers supported in A1."""

    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)


class Config(BaseSettings):
    """Root runtime configuration."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    @property
    def workspace_path(self) -> Path:
        """Return the expanded agent workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self,
        model: str | None = None,
    ) -> tuple[ProviderConfig | None, str | None]:
        """Match a configured provider using the provider registry."""
        from nanobot.providers.registry import PROVIDERS, find_by_name

        forced = self.agents.defaults.provider

        if forced != "auto":
            spec = find_by_name(forced)

            if spec is None:
                return None, None

            provider = getattr(self.providers, spec.name, None)

            if provider is not None:
                return provider, spec.name

            return None, None

        model_name = (model or self.agents.defaults.model).lower()
        model_prefix = (
            model_name.split("/", 1)[0]
            if "/" in model_name
            else ""
        )

        for spec in PROVIDERS:
            provider = getattr(self.providers, spec.name, None)

            if provider is None or not provider.api_key:
                continue

            if model_prefix == spec.name:
                return provider, spec.name

            if any(keyword in model_name for keyword in spec.keywords):
                return provider, spec.name

        # Fall back to the first configured provider.
        for spec in PROVIDERS:
            provider = getattr(self.providers, spec.name, None)

            if provider is not None and provider.api_key:
                return provider, spec.name

        return None, None

    def get_provider(
        self,
        model: str | None = None,
    ) -> ProviderConfig | None:
        """Return the matched provider configuration."""
        provider, _ = self._match_provider(model)
        return provider

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Return the matched provider's registry name."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Return the configured API key."""
        provider = self.get_provider(model)
        return provider.api_key if provider else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Return the configured or default API base URL."""
        from nanobot.providers.registry import find_by_name

        provider, name = self._match_provider(model)

        if provider is not None and provider.api_base:
            return provider.api_base

        if name:
            spec = find_by_name(name)

            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base

        return None

    model_config = ConfigDict(
        env_prefix="NANOBOT_",
        env_nested_delimiter="__",
    )