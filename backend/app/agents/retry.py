"""Retry policy for recoverable agent failures.

A small, deterministic policy the base agent consults when an agent raises a
recoverable error. The ``sleep`` callable is injectable so tests can run with
no real delay.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RetryPolicy:
    """Exponential-backoff retry configuration.

    Parameters
    ----------
    max_attempts:
        Total attempts (1 = no retry).
    base_delay_seconds:
        Delay before the first retry.
    backoff_factor:
        Multiplier applied to the delay on each subsequent retry.
    sleep:
        Delay function (injected for testability; defaults to ``time.sleep``).
    """

    max_attempts: int = 2
    base_delay_seconds: float = 0.1
    backoff_factor: float = 2.0
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    def next_delay(self, attempt: int) -> float:
        """Return the delay (seconds) before the given 1-based attempt number."""
        exponent = max(0, attempt - 1)
        return self.base_delay_seconds * (self.backoff_factor**exponent)


# A no-retry policy is occasionally useful for tests / fast paths.
NO_RETRY = RetryPolicy(max_attempts=1, sleep=lambda _delay: None)
