"""Server Sent Events parsing and per-provider stream accumulation.

The proxy tees a streamed response: each raw chunk is forwarded to the client
untouched (to preserve time to first token) and at the same time fed here, where
it is parsed incrementally so the final usage, model, and assembled text can be
reconstructed once the stream closes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from replay.cost.calculator import Usage, usage_from_openai


class SSEParser:
    """Incremental SSE parser. Feed raw bytes, get back parsed data objects.

    Events are separated by a blank line. Within an event, ``data:`` lines carry
    the JSON payload. The OpenAI style terminal ``data: [DONE]`` is ignored.
    """

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, chunk: bytes) -> Iterator[dict[str, Any]]:
        self._buf += chunk
        while b"\n\n" in self._buf:
            event, self._buf = self._buf.split(b"\n\n", 1)
            data = self._data(event)
            if data is not None:
                yield data

    @staticmethod
    def _data(event: bytes) -> dict[str, Any] | None:
        datas = [
            line[5:].strip()
            for line in event.split(b"\n")
            if line.startswith(b"data:")
        ]
        if not datas:
            return None
        payload = b"\n".join(datas)
        if payload == b"[DONE]":
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


class StreamState:
    """Base accumulator. Subclasses implement consume() for their event shape."""

    def __init__(self) -> None:
        self.model: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.text_parts: list[str] = []
        self.done = False

    def consume(self, data: dict[str, Any]) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @property
    def usage(self) -> Usage:
        return Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
        )

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


class AnthropicStreamState(StreamState):
    """Anthropic Messages SSE: message_start carries input usage and model,
    content_block_delta carries text, message_delta carries output tokens,
    message_stop terminates.
    """

    def consume(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "message_start":
            message = data.get("message", {})
            if isinstance(message.get("model"), str):
                self.model = message["model"]
            usage = message.get("usage", {})
            if isinstance(usage, dict):
                self.input_tokens = int(usage.get("input_tokens", 0) or 0)
                self.cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
                self.cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
        elif kind == "content_block_delta":
            delta = data.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                self.text_parts.append(str(delta.get("text", "")))
        elif kind == "message_delta":
            usage = data.get("usage", {})
            if isinstance(usage, dict) and usage.get("output_tokens") is not None:
                self.output_tokens = int(usage.get("output_tokens", 0) or 0)
        elif kind == "message_stop":
            self.done = True


class OpenAIStreamState(StreamState):
    """OpenAI style chat completions SSE (also Gemini's compatible endpoint).

    Each chunk carries choices[].delta.content. Token usage appears only in the
    final chunk, and only when the caller sends stream_options.include_usage, so
    it may be absent.
    """

    def consume(self, data: dict[str, Any]) -> None:
        if isinstance(data.get("model"), str):
            self.model = data["model"]
        for choice in data.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                self.text_parts.append(str(delta["content"]))
            if choice.get("finish_reason"):
                self.done = True
        usage = data.get("usage")
        if isinstance(usage, dict):
            parsed = usage_from_openai(usage)
            self.input_tokens = parsed.input_tokens
            self.output_tokens = parsed.output_tokens
            self.cache_read_tokens = parsed.cache_read_tokens


_STATES: dict[str, type[StreamState]] = {
    "anthropic": AnthropicStreamState,
    "gemini": OpenAIStreamState,
    "openai": OpenAIStreamState,
}


def make_state(provider_name: str) -> StreamState:
    """Return a fresh accumulator for a provider, defaulting to the OpenAI shape."""
    return _STATES.get(provider_name, OpenAIStreamState)()
