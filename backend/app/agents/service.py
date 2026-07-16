"""Answer service: the single entry point used by the API. Ties together the semantic cache,
the deterministic router (structured data + human-in-the-loop action suggestions) and the MAF
orchestrator (prose message when Azure OpenAI is configured)."""
from __future__ import annotations

from app.agents.chat_client import azure_available
from app.agents.router import route
from app.cache.semantic_cache import get_cache


async def _compose_message(query: str, routed: dict) -> str:
    fallback = routed["headline"] + "\n" + "\n".join(f"- {d}" for d in routed["details"][:8])
    if not azure_available():
        return fallback
    try:
        from app.agents.orchestrator import run_orchestrator
        return await run_orchestrator(query)
    except Exception as exc:  # noqa: BLE001 - never fail the request on LLM issues
        return f"{fallback}\n(Note: LLM unavailable - {type(exc).__name__})"


async def answer(query: str, use_cache: bool = True) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": query, "error": "empty query"}

    # Cache LLM answers and router (no-key) answers separately, so enabling the LLM never
    # returns a stale router-mode answer.
    namespace = "answer_llm" if azure_available() else "answer_router"

    cache = get_cache()
    if use_cache:
        hit = cache.get(query, namespace=namespace)
        if hit is not None:
            hit["cached"] = True
            return hit

    routed = route(query)
    message = await _compose_message(query, routed)
    result = {
        "query": query,
        "intent": routed["intent"],
        "agent": routed["agent"],
        "message": message,
        "headline": routed["headline"],
        "details": routed["details"],
        "data": routed["data"],
        "suggested_actions": routed["suggested_actions"],
        "llm_used": azure_available(),
        "cached": False,
    }
    cache.set(query, result, namespace=namespace)
    return result
