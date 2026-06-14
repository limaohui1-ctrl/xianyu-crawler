"""Provider Registry — register and lookup discovery providers by name."""
from typing import Dict, Optional, List
from .candidate_url import CandidateUrl


class ProviderRegistry:
    """Central registry for search/discovery providers.

    Each provider is a callable supported by a name key.
    """

    def __init__(self):
        self._providers: Dict[str, callable] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, provider: callable, description: str = ""):
        """Register a provider function.

        Args:
            name: Provider key (e.g. 'mock', 'import-file', 'sitemap')
            provider: Callable that takes relevant args and returns list[CandidateUrl]
            description: Human-readable description
        """
        self._providers[name] = provider
        self._descriptions[name] = description

    def get(self, name: str) -> Optional[callable]:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> List[dict]:
        """List all registered providers."""
        return [{"name": k, "description": self._descriptions.get(k, "")}
                for k in sorted(self._providers.keys())]

    def has(self, name: str) -> bool:
        return name in self._providers

    def search(self, name: str, **kwargs) -> List[CandidateUrl]:
        """Execute a search via the named provider."""
        provider = self.get(name)
        if not provider:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self._providers.keys())}")
        return provider(**kwargs)


# Global singleton
_registry = ProviderRegistry()


def register(name: str, provider: callable, description: str = ""):
    _registry.register(name, provider, description)


def get_registry() -> ProviderRegistry:
    return _registry


def search(name: str, **kwargs) -> List[CandidateUrl]:
    return _registry.search(name, **kwargs)
