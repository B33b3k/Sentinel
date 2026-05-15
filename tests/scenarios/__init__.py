"""Scenario registry — populated by importing each scenario module."""
from __future__ import annotations

from typing import Callable

_SCENARIOS: dict[str, Callable] = {}


def register(name: str):
    def _dec(fn: Callable) -> Callable:
        _SCENARIOS[name] = fn
        return fn
    return _dec


from tests.scenarios import sita, sim_swap, cold_start, mule_ring  # noqa: E402, F401
