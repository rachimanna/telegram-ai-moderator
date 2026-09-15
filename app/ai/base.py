from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Common interface for all AI providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Generate a text response from the AI provider."""
        raise NotImplementedError
