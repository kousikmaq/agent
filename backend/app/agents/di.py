"""Lightweight dependency-injection container.

A minimal service registry used to wire the orchestration layer without hard
imports between wiring points. In later phases it will also register the
existing engine instances that agents delegate to, keeping the agents free of
direct construction concerns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ServiceContainer:
    """A tiny container supporting eager instances and lazy factories."""

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}

    def register_instance(self, key: str, instance: Any) -> None:
        """Register an already-constructed singleton instance."""
        self._instances[key] = instance

    def register_factory(self, key: str, factory: Callable[[], Any]) -> None:
        """Register a lazy factory; its result is cached on first resolve."""
        self._factories[key] = factory

    def resolve(self, key: str) -> Any:
        """Resolve a registered service by key.

        Raises
        ------
        KeyError
            If no instance or factory is registered under ``key``.
        """
        if key in self._instances:
            return self._instances[key]
        if key in self._factories:
            instance = self._factories[key]()
            self._instances[key] = instance
            return instance
        raise KeyError(f"No service registered under '{key}'.")

    def has(self, key: str) -> bool:
        """Return whether a service is registered under ``key``."""
        return key in self._instances or key in self._factories
