import asyncio
import os
import anthropic
from .base import LLMProvider, LLMMessage

_RETRY_STATUSES = {429, 500, 502, 503, 529}


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        self.client = anthropic.AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = model

    async def complete(self, messages: list[LLMMessage], system: str = "") -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system

        last_err = None
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
            try:
                response = await self.client.messages.create(**kwargs)
                return response.content[0].text
            except anthropic.RateLimitError as e:
                last_err = e
            except anthropic.APIStatusError as e:
                if e.status_code in _RETRY_STATUSES:
                    last_err = e
                else:
                    raise
        raise last_err
