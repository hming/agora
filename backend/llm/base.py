from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[LLMMessage], system: str = "") -> str:
        ...
