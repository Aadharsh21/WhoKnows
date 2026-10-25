"""Story time: minutes since midnight, shown the way a phone shows it."""

from __future__ import annotations

DAY = 24 * 60


def parse(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def fmt(t: int) -> str:
    hours, minutes = divmod(t % DAY, 60)
    suffix = "AM" if hours < 12 else "PM"
    return f"{hours % 12 or 12}:{minutes:02d} {suffix}"


def in_window(t: int, start: str, end: str) -> bool:
    """True when t falls in [start, end). The window may wrap past midnight."""
    s, e, x = parse(start), parse(end), t % DAY
    return s <= x < e if s <= e else (x >= s or x < e)
