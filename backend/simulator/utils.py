"""Small, dependency-free helpers used across the simulator."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from random import Random

_TRAILING_DIGITS = re.compile(r"(\d+)$")


class IdSequencer:
    """Generates sequential, zero-padded identifiers for an entity family.

    Initialised from the identifiers already present in the state so newly
    generated ids never collide with existing ones across days.

    Example
    -------
    >>> seq = IdSequencer("ORD-", ["ORD-0007", "ORD-0003"], width=4)
    >>> seq.next()
    'ORD-0008'
    """

    def __init__(self, prefix: str, existing_ids: Iterable[str], *, width: int = 4) -> None:
        self._prefix = prefix
        self._width = width
        highest = 0
        for identifier in existing_ids:
            match = _TRAILING_DIGITS.search(identifier)
            if match:
                highest = max(highest, int(match.group(1)))
        self._counter = highest

    def next(self) -> str:
        """Return the next identifier in the sequence."""
        self._counter += 1
        return f"{self._prefix}{self._counter:0{self._width}d}"


def poisson(rng: Random, mean: float) -> int:
    """Draw a non-negative integer from a Poisson distribution (Knuth).

    Used to generate a realistic, bursty count of daily events (e.g. new
    orders) from a configured mean, using only the injected RNG so results stay
    reproducible.
    """
    if mean <= 0:
        return 0
    threshold = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > threshold:
        count += 1
        product *= rng.random()
    return count
