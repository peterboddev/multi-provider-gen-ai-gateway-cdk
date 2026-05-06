"""Data Models module.

Pydantic models for request/response validation.
Defines ChatMessage, ChatCompletionRequest, ChatCompletionResponse, and related models.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, field_validator


class Provider(str, Enum):
    """Supported LLM providers."""

    BEDROCK = "bedrock"
    OPENAI = "openai"


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None

    @field_validator("messages")
    @classmethod
    def messages_must_be_non_empty(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("messages must be a non-empty list")
        return v


class Usage(BaseModel):
    """Token usage statistics for a completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    """A single completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ErrorDetail(BaseModel):
    """Error detail within an error response."""

    message: str
    type: str


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: ErrorDetail
