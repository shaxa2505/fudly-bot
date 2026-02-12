"""Shared helpers for location-based search strategies."""
from __future__ import annotations

from collections.abc import Sequence

# Default distance ladder for "nearest first" expansion.
DEFAULT_NEARBY_RADIUS_STEPS_KM: tuple[float, ...] = (3.0, 7.0, 15.0, 25.0)


def build_nearby_radius_steps(
    requested_max_distance_km: float | None,
    *,
    default_steps: Sequence[float] = DEFAULT_NEARBY_RADIUS_STEPS_KM,
) -> tuple[float, ...]:
    """Return radius steps for nearby lookups.

    Rules:
    - Explicit `requested_max_distance_km` means "single fixed radius".
    - Otherwise use a sanitized default radius ladder.
    """
    if requested_max_distance_km is not None:
        try:
            explicit = float(requested_max_distance_km)
        except (TypeError, ValueError):
            explicit = 0.0
        return (max(explicit, 0.1),)

    steps: list[float] = []
    seen: set[float] = set()
    for item in default_steps:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        rounded = round(value, 2)
        if rounded in seen:
            continue
        seen.add(rounded)
        steps.append(rounded)

    if not steps:
        return (DEFAULT_NEARBY_RADIUS_STEPS_KM[0],)
    return tuple(sorted(steps))
