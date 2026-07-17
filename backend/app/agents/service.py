"""Answer service: the single entry point used by the API. Ties together the semantic cache,
the deterministic router (structured data + human-in-the-loop action suggestions) and the MAF
orchestrator (prose message when Azure OpenAI is configured)."""
from __future__ import annotations

import time

from app.agents.chat_client import azure_available
from app.agents.guardrails import screen
from app.agents.router import route
from app.cache.semantic_cache import get_cache
from app.logging_config import log


async def _compose_message(query: str, routed: dict) -> str:
    fallback = routed["headline"] + "\n" + "\n".join(f"- {d}" for d in routed["details"][:8])
    if not azure_available():
        log.info("LLM    skipped (no Azure key) -> using router-composed answer")
        return fallback
    try:
        from app.agents.orchestrator import run_orchestrator
        log.info("LLM    composing answer via MAF orchestrator (gpt-4o)...")
        return await run_orchestrator(query)
    except Exception as exc:  # noqa: BLE001 - never fail the request on LLM issues
        log.warning("LLM    unavailable (%s) -> falling back to router answer", type(exc).__name__)
        return f"{fallback}\n(Note: LLM unavailable - {type(exc).__name__})"


async def answer(query: str, use_cache: bool = True) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": query, "error": "empty query"}
    t0 = time.perf_counter()
    log.info("CHAT   query=%r", query)

    # Guardrail: intercept greetings, vague, off-topic and unsafe input before any analysis
    # or LLM call, and return a safe on-brand reply that steers back to the assistant's job.
    guard = screen(query)
    if guard is not None:
        log.info("GUARD  intercepted (%s) -> canned response in %.2fs",
                 guard["guardrail"], time.perf_counter() - t0)
        return {
            "query": query,
            "intent": guard["intent"],
            "agent": guard["agent"],
            "message": guard["message"],
            "headline": guard["headline"],
            "details": guard["details"],
            "data": guard["data"],
            "suggested_actions": guard["suggested_actions"],
            "llm_used": False,
            "cached": False,
        }

    # Cache LLM answers and router (no-key) answers separately, so enabling the LLM never
    # returns a stale router-mode answer.
    namespace = "answer_llm" if azure_available() else "answer_router"

    cache = get_cache()
    if use_cache:
        hit = cache.get(query, namespace=namespace)
        if hit is not None:
            log.info("CACHE  hit -> returning saved answer in %.2fs", time.perf_counter() - t0)
            hit["cached"] = True
            return hit
    log.info("CACHE  miss")

    routed = route(query)
    log.info("ROUTE  intent=%s -> agent='%s'", routed["intent"], routed["agent"])
    log.info("ENGINE ran %s analysis (%d detail rows)", routed["intent"], len(routed["details"]))

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
    log.info("DONE   answered in %.2fs (llm=%s, actions=%d)",
             time.perf_counter() - t0, azure_available(), len(routed["suggested_actions"]))
    return result
