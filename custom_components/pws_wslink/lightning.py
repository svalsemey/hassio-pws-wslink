"""Stabilize the lightning values reported by a Type5 module.

The station reports whole minutes since the last strike, so the derived
timestamp moves by up to a minute between two payloads and cannot be trusted
alone. A strike is therefore accepted either when a counter grew, which no
quiet period can produce, or when the derived timestamp moved further than
that rounding allows.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from .const import (
    LIGHTNING_COUNT_KEYS,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_TIME,
)
from .helpers import minutes_since_to_timestamp, to_int

# Rounding to whole minutes moves the derived timestamp by up to a minute from
# one payload to the next, so only a larger move denotes a strike on its own.
_STRIKE_JITTER: Final = timedelta(minutes=2)

# Elapsed time the API reports when no strike time is available.
_UNKNOWN_MINUTES: Final = 9999

_MINUTES_PER_DAY: Final = 1440


@dataclass
class LightningTracker:
    """Hold the last coherent strike time and distance of one station."""

    last_strike: datetime | None = None
    distance: int | None = None
    _counters: dict[str, int] = field(default_factory=dict)

    def apply(self, data: dict[str, Any]) -> None:
        """Refresh the tracked values, then publish them back into the payload."""
        counters = {
            key: count
            for key in LIGHTNING_COUNT_KEYS
            if (count := to_int(data.get(key))) is not None
        }
        strike = self._reported_strike(data, counters)

        if strike is not None and self._is_new_strike(strike, counters):
            self.last_strike = strike
            self.distance = to_int(data.get(LIGHTNING_DISTANCE))

        # Counters are the reference of the next payload whether a strike was
        # accepted or not, so a sliding window rolling over is not a strike.
        self._counters = counters

        for key, value in (
            (LIGHTNING_STRIKE_TIME, self.last_strike),
            (LIGHTNING_DISTANCE, self.distance),
        ):
            if key in data:
                data[key] = value

    def _is_new_strike(self, strike: datetime, counters: Mapping[str, int]) -> bool:
        """Return True when the payload describes a strike not seen yet."""
        if self.last_strike is None:
            return True

        # A counter can only grow when the module detected another strike, which
        # catches strikes too close together for the minute resolution to show.
        if any(
            count > self._counters.get(key, count) for key, count in counters.items()
        ):
            return True

        return abs(strike - self.last_strike) > _STRIKE_JITTER

    def _reported_strike(
        self, data: Mapping[str, Any], counters: Mapping[str, int]
    ) -> datetime | None:
        """Return the strike time the payload describes, None when implausible."""
        minutes = to_int(data.get(LIGHTNING_STRIKE_TIME))
        if minutes is None or minutes >= _UNKNOWN_MINUTES:
            return None

        # A station that just rebooted reports a zeroed elapsed time while its
        # counters are still empty, which no real strike can produce.
        if minutes < _MINUTES_PER_DAY and counters and not any(counters.values()):
            return None

        return minutes_since_to_timestamp(minutes)
