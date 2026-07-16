"""Semantic cache: stores answered queries (ML + LLM results) in SQLite so a repeat question
returns instantly without re-running models. Keyed by the normalised question + a data
version so it self-invalidates when the dataset changes. All SQL is parameterised."""
