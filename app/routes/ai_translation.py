"""Translate with AI: POST /api/translate, Creator's strings translated by your OpenAI-compatible provider.

The request isn't stored, so a Pydantic model reads it; app/integration/ai_translation.py calls the provider.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.integration.ai_translation import Translator
from app.settings import SettingsDep

router = APIRouter()


class TranslateRequest(BaseModel):
    strings: list[str] = []
    source: str = Field("", alias="from")
    to: str = ""


# region sjs:ai-translation.server
# POST /api/translate — strings in, translated strings out (same order); nothing goes to SurveyJS
@router.post("/api/translate")
async def translate(body: TranslateRequest, settings: SettingsDep, translator: Translator) -> list[str]:
    if not settings.ai_api_key:
        raise HTTPException(501, "Set AI_API_KEY to enable translation")

    translated = await translator.translate(body.strings, body.source, body.to)   # any OpenAI-compatible provider
    if not isinstance(translated, list) or len(translated) != len(body.strings) \
            or not all(isinstance(text, str) for text in translated):
        raise HTTPException(502, "The AI provider returned an unexpected answer")

    return translated   # what options.callback() takes
# endregion
