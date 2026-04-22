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
    errors: list[str] = field(default_factory=list)
