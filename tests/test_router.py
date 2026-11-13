from typing import ClassVar

import pytest
from openai import RateLimitError

from backend.app.services.router import NineRouterClient


def test_json_parser_accepts_markdown_fence():
    assert NineRouterClient._parse_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_json_parser_extracts_object_from_text():
    assert NineRouterClient._parse_json('result: {"pages": [1, 2]} thanks')["pages"] == [1, 2]


class FakeResponse:
    class Choice:
        class Message:
            content = '{"ok": true}'
        message = Message()
    choices: ClassVar = [Choice()]
    usage = None


class FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs["model"])
        if kwargs["model"] == "first":
            request = __import__("httpx").Request("POST", "http://test")
            response = __import__("httpx").Response(429, request=request)
            raise RateLimitError("quota", response=response, body={})
        return FakeResponse()


@pytest.mark.asyncio
async def test_falls_back_only_after_quota():
    class Settings:
        nine_router_base_url = "http://localhost/v1"
        nine_router_api_key = "test"
        llm_timeout_seconds = 5
        models: ClassVar = ["first", "second"]

    router = NineRouterClient(Settings())
    fake = FakeCompletions()
    router.client.chat.completions = fake
    data, usage = await router.chat_json(system="s", prompt="p", schema_hint="{}")
    assert data == {"ok": True}
    assert usage["model"] == "second"
    assert fake.calls == ["first", "second"]

