from typing import Any

import httpx

from app.ai.base import AIProvider
from app.config import get_settings


class OpenAICompatibleProvider(AIProvider):
    """Provider for APIs compatible with OpenAI Chat Completions."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY is not configured.")

        if not self.model:
            raise RuntimeError("AI_MODEL is not configured.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "AI provider request timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"AI provider returned HTTP {exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                "AI provider request failed."
            ) from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "AI provider returned an unexpected response."
            ) from exc

        if not isinstance(content, str):
            raise RuntimeError(
                "AI provider returned invalid message content."
            )

        return content


def create_ai_provider() -> OpenAICompatibleProvider:
    """Create the configured AI provider."""

    settings = get_settings()

    return OpenAICompatibleProvider(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout=settings.ai_timeout_seconds,
    )
