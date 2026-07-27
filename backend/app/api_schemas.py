"""Pydantic request models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    use_cache: bool = True


class ActionRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    params: dict = Field(default_factory=dict)
