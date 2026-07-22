"""HTTP API layer.

Exposes the FastAPI routers. Routing is organised by version (``v1``, ``v2``,
...) so the public contract can evolve without breaking existing clients.
"""
