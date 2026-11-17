"""Asks any OpenAI-compatible /chat/completions endpoint (AI_BASE_URL, AI_API_KEY, AI_MODEL) to translate
Creator's strings. Your provider and your key: nothing goes to SurveyJS. Swap this file for your provider's
SDK if you like; the route only needs a list back. When you copy ai-translation, copy this file too."""

import json
import logging
import re
from typing import Annotated, Any

import httpx2
from fastapi import Depends, HTTPException
from starlette.requests import HTTPConnection

from app.settings import Settings

log = logging.getLogger("app.ai")
_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class AiTranslation:
    def __init__(self, http: httpx2.AsyncClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    async def translate(self, strings: list[str], source: str, target: str) -> Any:
        """The translated strings as the model returned them (a list if all went well), or None. An unreachable
        provider or an HTTP error ends the request here with 502."""
        try:
            reply = await self.http.post(
                f"{self.settings.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.ai_api_key}"},
                json={
                    "model": self.settings.ai_model,
                    "messages": [
                        {"role": "system", "content": f"Translate each string from {source} to {target}. "
                                                      "Return a JSON array in the same order."},
                        {"role": "user", "content": json.dumps(strings, ensure_ascii=False)},
                    ],
                },
                timeout=60,
            )
            reply.raise_for_status()
        except httpx2.HTTPError as error:
            log.error("Translation provider failed: %s", error)
            raise HTTPException(502, "The translation provider is unavailable. Please try again.") from None
        try:
            content = reply.json()["choices"][0]["message"]["content"]
        except (ValueError, LookupError, TypeError):
            return None

        # Models sometimes wrap the array in prose or a code fence: take the array itself
        match = _ARRAY.search(content) if isinstance(content, str) else None
        try:
            return json.loads(match.group(0)) if match else None
        except ValueError:
            return None


def get_ai_translation(conn: HTTPConnection) -> AiTranslation:
    return AiTranslation(conn.app.state.http, conn.app.state.settings)


Translator = Annotated[AiTranslation, Depends(get_ai_translation)]
