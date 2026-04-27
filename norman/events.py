"""Tournament event calendar and active-window detection.

Phase 1 scope (Reddit-only): the calendar covers the four men's majors
plus a small set of PGA Tour signature events for 2026. active_event_window
returns the event whose [start - pre_days, end + post_days] window
contains a given date; event_query_combos generates 6-10 search queries
that cross event identifiers with Torque Optics pain-point anchors.

No score logic lives here — events are surfaced via the event_window
boolean on Lead, not via score modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


__all__ = [
    "TournamentEvent",
    "EVENTS_2026",
    "active_event_window",
    "event_query_combos",
    "events_in_range",
]


@dataclass
class TournamentEvent:
    name: str
    short_name: str
    start_date: date
    end_date: date
    venue: str
    location: str
    hashtags: list[str] = field(default_factory=list)
    tour: str = "Regular"   # "Major" | "Signature" | "Regular"


# 2026 men's majors and signature events, dates per the published
# PGA Tour 2026 schedule.
EVENTS_2026: list[TournamentEvent] = [
    TournamentEvent(
        name="The Masters",
        short_name="masters",
        start_date=date(2026, 4, 9),
        end_date=date(2026, 4, 12),
        venue="Augusta National",
        location="Augusta, GA",
        hashtags=["#TheMasters", "#Masters", "#Masters2026"],
        tour="Major",
    ),
    TournamentEvent(
        name="Truist Championship",
        short_name="truist",
        start_date=date(2026, 5, 7),
        end_date=date(2026, 5, 10),
        venue="Quail Hollow Club",
        location="Charlotte, NC",
        hashtags=["#TruistChampionship", "#Truist2026"],
        tour="Signature",
    ),
    TournamentEvent(
        name="PGA Championship",
        short_name="pga_championship",
        start_date=date(2026, 5, 14),
        end_date=date(2026, 5, 17),
        venue="Quail Hollow Club",
        location="Charlotte, NC",
        hashtags=["#PGAChampionship", "#PGAChamp", "#PGAChamp2026"],
        tour="Major",
    ),
    TournamentEvent(
        name="The Memorial Tournament",
        short_name="memorial",
        start_date=date(2026, 6, 4),
        end_date=date(2026, 6, 7),
        venue="Muirfield Village Golf Club",
        location="Dublin, OH",
        hashtags=["#TheMemorial", "#MemorialTournament"],
        tour="Signature",
    ),
    TournamentEvent(
        name="US Open",
        short_name="us_open",
        start_date=date(2026, 6, 18),
        end_date=date(2026, 6, 21),
        venue="Shinnecock Hills",
        location="Southampton, NY",
        hashtags=["#USOpen", "#USOpen2026", "#USOpenGolf"],
        tour="Major",
    ),
    TournamentEvent(
        name="Travelers Championship",
        short_name="travelers",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 28),
        venue="TPC River Highlands",
        location="Cromwell, CT",
        hashtags=["#TravelersChamp", "#TravelersChampionship"],
        tour="Signature",
    ),
    TournamentEvent(
        name="The Open Championship",
        short_name="the_open",
        start_date=date(2026, 7, 16),
        end_date=date(2026, 7, 19),
        venue="Royal Birkdale",
        location="Southport, UK",
        hashtags=["#TheOpen", "#TheOpen2026", "#OpenChampionship"],
        tour="Major",
    ),
]


_TOUR_PRIORITY = {"Major": 0, "Signature": 1, "Regular": 2}


def active_event_window(
    today: date,
    pre_days: int = 3,
    post_days: int = 2,
) -> Optional[TournamentEvent]:
    """Return the event whose [start - pre_days, end + post_days] window contains today.

    When multiple events overlap, prefer Major > Signature > Regular, then the
    closer start_date.
    """
    candidates: list[TournamentEvent] = []
    for event in EVENTS_2026:
        window_start = event.start_date - timedelta(days=pre_days)
        window_end = event.end_date + timedelta(days=post_days)
        if window_start <= today <= window_end:
            candidates.append(event)

    if not candidates:
        return None

    def _rank(e: TournamentEvent) -> tuple[int, int]:
        priority = _TOUR_PRIORITY.get(e.tour, 99)
        proximity = abs((e.start_date - today).days)
        return (priority, proximity)

    candidates.sort(key=_rank)
    return candidates[0]


def events_in_range(
    window_start: date,
    window_end: date,
    pre_days: int = 3,
    post_days: int = 2,
) -> list[TournamentEvent]:
    """Return events whose [start - pre_days, end + post_days] window
    intersects the inclusive date range [window_start, window_end].

    Used by the weekly synthesis to detect which tournaments overlapped the
    past N days of customer-voice data.
    """
    out: list[TournamentEvent] = []
    for event in EVENTS_2026:
        ev_start = event.start_date - timedelta(days=pre_days)
        ev_end = event.end_date + timedelta(days=post_days)
        if ev_start <= window_end and window_start <= ev_end:
            out.append(event)
    out.sort(key=lambda e: e.start_date)
    return out


def event_query_combos(event: TournamentEvent) -> list[str]:
    """Generate 6-10 search queries that cross event identifiers with pain anchors.

    Skips sponsorship/marketing-skewed combos in favor of phrasings most likely
    to surface customer-voice content (forum posts, Reddit threads, complaints).
    """
    primary_tag = event.hashtags[0] if event.hashtags else f"#{event.short_name}"
    return [
        f"{primary_tag} sunglasses glare",
        f"{primary_tag} polarized",
        f"{primary_tag} eye strain",
        f"{event.venue} polarized",
        f"{event.name} sunglasses recommendation",
        f"{event.name} golf vision",
        f"watching {event.name} polarized",
        f"{event.name} eye strain",
    ]
