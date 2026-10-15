from functools import lru_cache
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class MissingApiKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("OPENAI_API_KEY is not set. Add it to aria/backend/.env and restart the backend.")


@lru_cache
def get_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.has_api_key:
        raise MissingApiKeyError()
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def structured(
    *,
    model: str,
    instructions: str,
    input_text: str,
    schema: type[T],
    reasoning_effort: str | None = "low",
) -> tuple[T, dict[str, int]]:
    kwargs = {"reasoning": {"effort": reasoning_effort}} if reasoning_effort else {}
    response = await get_client().responses.parse(
        model=model,
        instructions=instructions,
        input=input_text,
        text_format=schema,
        **kwargs,
    )
    if response.output_parsed is None:
        raise ValueError(f"Model {model} returned no parsed output for {schema.__name__}")
    return response.output_parsed, usage_of(response)


async def embed(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 96):
        batch = [t[:8000] for t in texts[start : start + 96]]
        response = await get_client().embeddings.create(model=settings.embedding_model, input=batch)
        vectors.extend(item.embedding for item in response.data)
    return vectors


def usage_of(response: object) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
    }
