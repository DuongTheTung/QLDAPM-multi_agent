from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from ..config import Settings


class RouterExhaustedError(RuntimeError):
    pass


class NineRouterClient:
    """OpenAI-compatible 9Router client with quota-only model fallback."""

    QUOTA_MARKERS = (
        "insufficient_quota", "quota", "rate limit", "rate_limit", "resource exhausted",
        "token limit", "tokens exhausted", "credit", "billing", "429",
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            base_url=settings.nine_router_base_url.rstrip("/"),
            api_key=settings.nine_router_api_key or "missing-key",
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    @classmethod
    def _quota_error(cls, error: Exception) -> bool:
        if isinstance(error, RateLimitError):
            return True
        if isinstance(error, APIStatusError) and error.status_code in {402, 429}:
            return True
        return any(marker in str(error).lower() for marker in cls.QUOTA_MARKERS)

    async def chat_json(
        self,
        *,
        system: str,
        prompt: str,
        schema_hint: str,
        temperature: float = 0.4,
        on_attempt: Any | None = None,
        image_paths: list[Path] | None = None,
        timeout_seconds: float | None = None,
        models: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.settings.nine_router_api_key:
            raise RouterExhaustedError("NINE_ROUTER_API_KEY chưa được cấu hình")

        errors: list[str] = []
        model_chain = [model for model in (models or self.settings.models) if model]
        for model_index, model in enumerate(model_chain):
            for attempt in range(1, 3):
                try:
                    if on_attempt:
                        on_attempt(model, attempt, model_index > 0)
                    user_content: str | list[dict[str, Any]] = (
                        f"{prompt}\n\nTrả về DUY NHẤT JSON hợp lệ. Schema:\n{schema_hint}"
                    )
                    if image_paths:
                        parts: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
                        for path in image_paths:
                            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
                            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                            parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "low"},
                            })
                        user_content = parts
                    response = await self.client.chat.completions.create(
                        model=model,
                        temperature=temperature,
                        timeout=timeout_seconds or self.settings.llm_timeout_seconds,
                        messages=[
                            {"role": "system", "content": system},
                            {
                                "role": "user",
                                "content": user_content,
                            },
                        ],
                    )
                    content = response.choices[0].message.content or ""
                    data = self._parse_json(content)
                    usage = getattr(response, "usage", None)
                    return data, {
                        "model": model,
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    }
                except (APIConnectionError, TimeoutError) as error:
                    errors.append(f"{model}: {error}")
                    if attempt == 1:
                        await asyncio.sleep(1.2)
                        continue
                    raise RouterExhaustedError(
                        f"Không kết nối được 9Router tại {self.settings.nine_router_base_url}: {error}"
                    ) from error
                except (json.JSONDecodeError, ValueError) as error:
                    errors.append(f"{model}: invalid JSON: {error}")
                    if attempt == 1:
                        prompt = (
                            f"Nội dung trước không parse được ({error}). Hãy tạo lại đầy đủ, JSON chuẩn.\n\n"
                            + prompt
                        )
                        continue
                    raise RouterExhaustedError(f"Model {model} trả JSON không hợp lệ hai lần") from error
                except Exception as error:  # SDK providers expose different error subclasses
                    errors.append(f"{model}: {error}")
                    if self._quota_error(error):
                        break
                    if isinstance(error, APIStatusError) and error.status_code >= 500 and attempt == 1:
                        await asyncio.sleep(1.2)
                        continue
                    raise
        raise RouterExhaustedError("Tất cả model đã hết quota/token: " + " | ".join(errors))

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL)
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            start, end = content.find("{"), content.rfind("}")
            if start < 0 or end <= start:
                raise
            result = json.loads(content[start : end + 1])
        if not isinstance(result, dict):
            raise TypeError("JSON root phải là object")
        return result

