"""When it is acceptable to make the call.

Calling a depot at 03:00 is legal and awful. It is also the failure mode an
autonomous agent falls into most easily, because nothing in the loop knows what
time it is where the phone is ringing — the planner has a frontier and a budget
and no reason to wait.

A window is per-outcome rather than per-organisation. Per-organisation would be
more correct, and is the right change the first time a run spans two continents;
one window keeps the model honest for everything short of that, and a single
wrong timezone is easier to spot than five.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class WindowError(ValueError):
    pass


def _parse_hhmm(value: str, label: str) -> tuple[int, int]:
    try:
        hours, minutes = str(value).split(":")
        hour, minute = int(hours), int(minutes)
    except (ValueError, AttributeError):
        raise WindowError(f"{label} must look like 09:00, got {value!r}.") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise WindowError(f"{label} is not a real time of day: {value!r}.")
    return hour, minute


@dataclass
class CallWindow:
    """The hours, in the recipients' own timezone, when this run may dial."""

    timezone: str = "UTC"
    start: str = "09:00"
    end: str = "17:30"
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])

    def __post_init__(self) -> None:
        try:
            self._tz = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise WindowError(
                f"Unknown timezone {self.timezone!r}. Use an IANA name such as "
                "'Europe/London' or 'Asia/Singapore'."
            ) from None
        self._start = _parse_hhmm(self.start, "start")
        self._end = _parse_hhmm(self.end, "end")
        if self._start >= self._end:
            raise WindowError(
                f"start {self.start} is not before end {self.end}. A window that wraps "
                "midnight is almost always a typo, so it is rejected rather than guessed at."
            )
        days = sorted({int(d) for d in self.weekdays})
        if not days or any(d < 0 or d > 6 for d in days):
            raise WindowError("weekdays must be numbers 0 (Monday) to 6 (Sunday).")
        self.weekdays = days

    # -- queries ---------------------------------------------------------

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def is_open(self, when: datetime | None = None) -> bool:
        local = (when or self.now()).astimezone(self._tz)
        if local.weekday() not in self.weekdays:
            return False
        minutes = local.hour * 60 + local.minute
        return self._start[0] * 60 + self._start[1] <= minutes < self._end[0] * 60 + self._end[1]

    def next_open(self, when: datetime | None = None) -> datetime:
        """The next moment this window is open.

        Walks forward a day at a time rather than solving it, because the answer
        has to survive a DST transition and a naive arithmetic version silently
        lands an hour out twice a year.
        """
        local = (when or self.now()).astimezone(self._tz)
        candidate = local.replace(
            hour=self._start[0], minute=self._start[1], second=0, microsecond=0
        )
        if candidate <= local:
            candidate += timedelta(days=1)
        for _ in range(8):
            if candidate.weekday() in self.weekdays:
                return candidate
            candidate += timedelta(days=1)
        raise WindowError("No open day found in the next week.")  # unreachable: weekdays is non-empty

    def describe(self) -> str:
        days = ", ".join(WEEKDAY_NAMES[d] for d in self.weekdays)
        return f"{self.start}-{self.end} {self.timezone}, {days}"

    def explain_closed(self, when: datetime | None = None) -> str:
        opens = self.next_open(when)
        return (
            f"Outside the calling window ({self.describe()}). "
            f"It opens {opens.strftime('%a %d %b %H:%M %Z')}."
        )

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "start": self.start,
            "end": self.end,
            "weekdays": list(self.weekdays),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CallWindow | None":
        if not d:
            return None
        return cls(
            timezone=str(d.get("timezone") or "UTC"),
            start=str(d.get("start") or "09:00"),
            end=str(d.get("end") or "17:30"),
            weekdays=list(d.get("weekdays") or [0, 1, 2, 3, 4]),
        )
