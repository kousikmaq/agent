"""Shared helpers for parsing the advisor's LLM output.

The model is asked for strict JSON, but real completions occasionally wrap it in
prose or a ```json code fence. :func:`extract_json_object` recovers the first
balanced JSON object so a stray sentence never breaks the feature.
"""

from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> dict | None:
    """Return the first JSON object found in ``text``, or ``None``.

    Tries a direct parse first, then strips a Markdown code fence, then falls
    back to scanning for the first balanced ``{...}`` block. Purely defensive --
    the caller still validates every field.
    """
    if not text:
        return None
    candidate = text.strip()

    # Strip a leading/trailing Markdown code fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        pass

    # Scan for the first balanced object.
    start = candidate.find("{")
    while start != -1:
        depth = 0
        for end in range(start, len(candidate)):
            char = candidate[end]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(candidate[start : end + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except (ValueError, TypeError):
                        break
        start = candidate.find("{", start + 1)
    return None
