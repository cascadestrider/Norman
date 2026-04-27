from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Lead:
    url: str
    title: str
    score: int
    keywords: list[str]
    source: str          # reddit | google | youtube | x | meta | tiktok
    platform: str        # reddit | web | youtube | x | facebook | instagram | tiktok
    geo: Optional[str] = None
    snippet: str = ""
    source_type: str = "unknown"  # customer_voice | retailer | editorial_roundup | unknown
    event_name: str = ""          # set when surfaced by event-specific querying
    event_window: bool = False    # True when this lead came from an event-search pass


@dataclass
class AnalystLead(Lead):
    segment: str = "general"
    problem_detected: str = ""
    why_we_win: str = ""
    ad_headline: str = ""
    ad_body: str = ""
    placement_tip: str = ""
    geo_note: Optional[str] = None


@dataclass
class ScoutResult:
    source: str
    leads: list[Lead] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalystOutput:
    date: str
    total_leads: int
    segments: dict[str, list[AnalystLead]] = field(default_factory=dict)
    top_3: list[AnalystLead] = field(default_factory=list)


@dataclass
class DeliveryStatus:
    markdown: str = ""
    discord: str = ""
    klaviyo: str = ""
    dashboard: str = ""
    synthesis_markdown: str = ""
    synthesis_discord: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class RepresentativeQuote:
    quote: str       # verbatim excerpt; may be empty when no quotable text exists in the lead
    summary: str     # synthesizer's observation about the lead in third-person clinical voice
    source_url: str
    segment: str


@dataclass
class CreativeAngle:
    angle: str
    hook: str
    proof_point: str


@dataclass
class ThemeOutput:
    name: str
    pain_point: str
    segment_breakdown: dict[str, int] = field(default_factory=dict)
    urgency_score: int = 0
    representative_quotes: list[RepresentativeQuote] = field(default_factory=list)
    creative_angles: list[CreativeAngle] = field(default_factory=list)


@dataclass
class SynthesisOutput:
    week_of: str
    leads_analyzed: int
    summary: str
    themes: list[ThemeOutput] = field(default_factory=list)
    # Set when the synthesizer sampled a subset of the weekly corpus because
    # the total exceeded the budget cap. None when the full corpus was used.
    sampled_note: Optional[str] = None
    # Pre-formatted event labels (e.g. "PGA Championship (May 14-17)") for
    # tournaments whose windows overlapped the synthesis period. Empty when
    # no events overlapped.
    events_in_window: list[str] = field(default_factory=list)
