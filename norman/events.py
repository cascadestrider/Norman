"""Tournament event calendar and active-window detection.

Phase 1.7 scope: the calendar covers full-season 2026 schedules for three
tours — PGA Tour, LPGA, DP World Tour — stored as three per-tour lists
(EVENTS_2026_PGA, EVENTS_2026_LPGA, EVENTS_2026_DP_WORLD) and concatenated
as EVENTS_2026 for backward compatibility. active_event_window returns the
event whose [start - pre_days, end + post_days] window contains a given
date; event_query_combos generates 6-10 search queries that cross event
identifiers with Torque Optics pain-point anchors.

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
    "EVENTS_2026_PGA",
    "EVENTS_2026_LPGA",
    "EVENTS_2026_DP_WORLD",
    "active_event_window",
    "event_query_combos",
    "event_verification_keywords",
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
    prestige: str = "Regular"   # "Major" | "Signature" | "Regular" — used as tiebreak when multiple events overlap
    tour: str = "PGA"           # "PGA" | "LPGA" | "DP_WORLD" — tour-of-origin used for cross-tour priority


# 2026 PGA Tour events (men's), regular season through Tour Championship in August.
# Dates per ESPN's 2026 PGA Tour schedule; venues per current published
# schedule. The fall FedExCup series is intentionally excluded for Phase 1.7.
EVENTS_2026_PGA: list[TournamentEvent] = [
    TournamentEvent(
        name="Sony Open in Hawaii",
        short_name="sony_open",
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 18),
        venue="Waialae Country Club",
        location="Honolulu, HI",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="The American Express",
        short_name="am_express",
        start_date=date(2026, 1, 22),
        end_date=date(2026, 1, 25),
        venue="PGA West",
        location="La Quinta, CA",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Farmers Insurance Open",
        short_name="farmers",
        start_date=date(2026, 1, 29),
        end_date=date(2026, 2, 1),
        venue="Torrey Pines",
        location="La Jolla, CA",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="WM Phoenix Open",
        short_name="wm_phoenix",
        start_date=date(2026, 2, 5),
        end_date=date(2026, 2, 8),
        venue="TPC Scottsdale",
        location="Scottsdale, AZ",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="AT&T Pebble Beach Pro-Am",
        short_name="pebble_beach",
        start_date=date(2026, 2, 12),
        end_date=date(2026, 2, 15),
        venue="Pebble Beach Golf Links",
        location="Pebble Beach, CA",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="The Genesis Invitational",
        short_name="genesis",
        start_date=date(2026, 2, 19),
        end_date=date(2026, 2, 22),
        venue="Riviera Country Club",
        location="Pacific Palisades, CA",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="Cognizant Classic in The Palm Beaches",
        short_name="cognizant",
        start_date=date(2026, 2, 26),
        end_date=date(2026, 3, 1),
        venue="PGA National Resort",
        location="Palm Beach Gardens, FL",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Arnold Palmer Invitational",
        short_name="api",
        start_date=date(2026, 3, 5),
        end_date=date(2026, 3, 8),
        venue="Bay Hill Club & Lodge",
        location="Orlando, FL",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="The Players Championship",
        short_name="players",
        start_date=date(2026, 3, 12),
        end_date=date(2026, 3, 15),
        venue="TPC Sawgrass",
        location="Ponte Vedra Beach, FL",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="Valspar Championship",
        short_name="valspar",
        start_date=date(2026, 3, 19),
        end_date=date(2026, 3, 22),
        venue="Innisbrook Resort",
        location="Palm Harbor, FL",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Texas Children's Houston Open",
        short_name="houston_open",
        start_date=date(2026, 3, 26),
        end_date=date(2026, 3, 29),
        venue="Memorial Park Golf Course",
        location="Houston, TX",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Valero Texas Open",
        short_name="valero",
        start_date=date(2026, 4, 2),
        end_date=date(2026, 4, 5),
        venue="TPC San Antonio",
        location="San Antonio, TX",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="The Masters",
        short_name="masters",
        start_date=date(2026, 4, 9),
        end_date=date(2026, 4, 12),
        venue="Augusta National",
        location="Augusta, GA",
        hashtags=["#TheMasters", "#Masters", "#Masters2026"],
        prestige="Major",
        tour="PGA",
    ),
    TournamentEvent(
        name="RBC Heritage",
        short_name="rbc_heritage",
        start_date=date(2026, 4, 16),
        end_date=date(2026, 4, 19),
        venue="Harbour Town Golf Links",
        location="Hilton Head Island, SC",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="Zurich Classic of New Orleans",
        short_name="zurich",
        start_date=date(2026, 4, 23),
        end_date=date(2026, 4, 26),
        venue="TPC Louisiana",
        location="Avondale, LA",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Cadillac Championship",
        short_name="cadillac",
        start_date=date(2026, 4, 30),
        end_date=date(2026, 5, 3),
        venue="Trump National Doral",
        location="Miami, FL",
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="Truist Championship",
        short_name="truist",
        start_date=date(2026, 5, 7),
        end_date=date(2026, 5, 10),
        venue="Quail Hollow Club",
        location="Charlotte, NC",
        hashtags=["#TruistChampionship", "#Truist2026"],
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="PGA Championship",
        short_name="pga_championship",
        start_date=date(2026, 5, 14),
        end_date=date(2026, 5, 17),
        venue="Aronimink Golf Club",
        location="Newtown Square, PA",
        hashtags=["#PGAChampionship", "#PGAChamp", "#PGAChamp2026"],
        prestige="Major",
        tour="PGA",
    ),
    TournamentEvent(
        name="The CJ Cup Byron Nelson",
        short_name="cj_byron_nelson",
        start_date=date(2026, 5, 21),
        end_date=date(2026, 5, 24),
        venue="TPC Craig Ranch",
        location="McKinney, TX",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Charles Schwab Challenge",
        short_name="charles_schwab",
        start_date=date(2026, 5, 28),
        end_date=date(2026, 5, 31),
        venue="Colonial Country Club",
        location="Fort Worth, TX",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="The Memorial Tournament",
        short_name="memorial",
        start_date=date(2026, 6, 4),
        end_date=date(2026, 6, 7),
        venue="Muirfield Village Golf Club",
        location="Dublin, OH",
        hashtags=["#TheMemorial", "#MemorialTournament"],
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="RBC Canadian Open",
        short_name="rbc_canadian",
        start_date=date(2026, 6, 11),
        end_date=date(2026, 6, 14),
        venue="TPC Toronto at Osprey Valley",
        location="Caledon, ON",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="US Open",
        short_name="us_open",
        start_date=date(2026, 6, 18),
        end_date=date(2026, 6, 21),
        venue="Shinnecock Hills",
        location="Southampton, NY",
        hashtags=["#USOpen", "#USOpen2026", "#USOpenGolf"],
        prestige="Major",
        tour="PGA",
    ),
    TournamentEvent(
        name="Travelers Championship",
        short_name="travelers",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 28),
        venue="TPC River Highlands",
        location="Cromwell, CT",
        hashtags=["#TravelersChamp", "#TravelersChampionship"],
        prestige="Signature",
        tour="PGA",
    ),
    TournamentEvent(
        name="John Deere Classic",
        short_name="john_deere",
        start_date=date(2026, 7, 2),
        end_date=date(2026, 7, 5),
        venue="TPC Deere Run",
        location="Silvis, IL",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Genesis Scottish Open",
        short_name="scottish_open",
        start_date=date(2026, 7, 9),
        end_date=date(2026, 7, 12),
        venue="The Renaissance Club",
        location="North Berwick, Scotland",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="The Open Championship",
        short_name="the_open",
        start_date=date(2026, 7, 16),
        end_date=date(2026, 7, 19),
        venue="Royal Birkdale",
        location="Southport, UK",
        hashtags=["#TheOpen", "#TheOpen2026", "#OpenChampionship"],
        prestige="Major",
        tour="PGA",
    ),
    TournamentEvent(
        name="3M Open",
        short_name="three_m_open",
        start_date=date(2026, 7, 23),
        end_date=date(2026, 7, 26),
        venue="TPC Twin Cities",
        location="Blaine, MN",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Rocket Classic",
        short_name="rocket_classic",
        start_date=date(2026, 7, 30),
        end_date=date(2026, 8, 2),
        venue="Detroit Golf Club",
        location="Detroit, MI",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Wyndham Championship",
        short_name="wyndham",
        start_date=date(2026, 8, 6),
        end_date=date(2026, 8, 9),
        venue="Sedgefield Country Club",
        location="Greensboro, NC",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="FedEx St. Jude Championship",
        short_name="fedex_st_jude",
        start_date=date(2026, 8, 13),
        end_date=date(2026, 8, 16),
        venue="TPC Southwind",
        location="Memphis, TN",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="BMW Championship",
        short_name="bmw",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 23),
        venue="Bellerive Country Club",
        location="St. Louis, MO",
        prestige="Regular",
        tour="PGA",
    ),
    TournamentEvent(
        name="Tour Championship",
        short_name="tour_championship",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 30),
        venue="East Lake Golf Club",
        location="Atlanta, GA",
        prestige="Regular",
        tour="PGA",
    ),
]


# 2026 LPGA Tour events, May 25 forward through end of season.
# Dates per ESPN's 2026 LPGA Tour schedule. 4 women's majors fall in this
# window: U.S. Women's Open, KPMG Women's PGA Championship, Amundi Evian
# Championship, AIG Women's Open. Solheim Cup (team event) included as
# "Signature" prestige; everything else is Regular.
EVENTS_2026_LPGA: list[TournamentEvent] = [
    TournamentEvent(
        name="ShopRite LPGA Classic",
        short_name="lpga_shoprite",
        start_date=date(2026, 5, 29),
        end_date=date(2026, 5, 31),
        venue="Seaview Hotel and Golf Club",
        location="Galloway, NJ",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="U.S. Women's Open",
        short_name="us_womens_open",
        start_date=date(2026, 6, 4),
        end_date=date(2026, 6, 7),
        venue="Riviera Country Club",
        location="Pacific Palisades, CA",
        prestige="Major",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Dow Championship",
        short_name="lpga_dow",
        start_date=date(2026, 6, 11),
        end_date=date(2026, 6, 14),
        venue="Midland Country Club",
        location="Midland, MI",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Meijer LPGA Classic for Simply Give",
        short_name="lpga_meijer",
        start_date=date(2026, 6, 18),
        end_date=date(2026, 6, 21),
        venue="Blythefield Country Club",
        location="Belmont, MI",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="KPMG Women's PGA Championship",
        short_name="kpmg_womens",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 28),
        venue="Hazeltine National Golf Club",
        location="Chaska, MN",
        prestige="Major",
        tour="LPGA",
    ),
    TournamentEvent(
        name="The Amundi Evian Championship",
        short_name="evian",
        start_date=date(2026, 7, 9),
        end_date=date(2026, 7, 12),
        venue="Evian Resort Golf Club",
        location="Évian-les-Bains, France",
        prestige="Major",
        tour="LPGA",
    ),
    TournamentEvent(
        name="ISPS HANDA Women's Scottish Open",
        short_name="lpga_scottish",
        start_date=date(2026, 7, 23),
        end_date=date(2026, 7, 26),
        venue="Dundonald Links",
        location="Ayrshire, Scotland",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="AIG Women's Open",
        short_name="aig_womens_open",
        start_date=date(2026, 7, 30),
        end_date=date(2026, 8, 2),
        venue="Royal Lytham & St. Annes Golf Club",
        location="Lancashire, England",
        prestige="Major",
        tour="LPGA",
    ),
    TournamentEvent(
        name="The Standard Portland Classic",
        short_name="portland_classic",
        start_date=date(2026, 8, 13),
        end_date=date(2026, 8, 16),
        venue="Columbia Edgewater Country Club",
        location="Portland, OR",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="CPKC Women's Open",
        short_name="cpkc_womens",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 23),
        venue="Royal Mayfair Golf & Country Club",
        location="Edmonton, AB",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="FM Championship",
        short_name="fm_championship",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 30),
        venue="TPC Boston",
        location="Norton, MA",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Solheim Cup",
        short_name="solheim_cup",
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 13),
        venue="Bernardus Golf",
        location="Cromvoirt, Netherlands",
        prestige="Signature",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Walmart NW Arkansas Championship",
        short_name="nw_arkansas",
        start_date=date(2026, 9, 25),
        end_date=date(2026, 9, 27),
        venue="Pinnacle Country Club",
        location="Rogers, AR",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="LOTTE Championship",
        short_name="lotte",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        venue="Hoakalei Country Club",
        location="Ewa Beach, HI",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Buick LPGA Shanghai",
        short_name="buick_shanghai",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 18),
        venue="Sheshan Golf Club",
        location="Shanghai, China",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="BMW Ladies Championship",
        short_name="bmw_ladies",
        start_date=date(2026, 10, 22),
        end_date=date(2026, 10, 25),
        venue="Pine Beach Golf Links",
        location="Haenam-gun, South Korea",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Maybank Championship",
        short_name="maybank",
        start_date=date(2026, 10, 29),
        end_date=date(2026, 11, 1),
        venue="Kuala Lumpur Golf and Country Club",
        location="Kuala Lumpur, Malaysia",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="TOTO Japan Classic",
        short_name="toto_japan",
        start_date=date(2026, 11, 5),
        end_date=date(2026, 11, 8),
        venue="Taiheiyo Club Minori Course",
        location="Omitama, Japan",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="The ANNIKA driven by Gainbridge at Pelican",
        short_name="annika_pelican",
        start_date=date(2026, 11, 12),
        end_date=date(2026, 11, 15),
        venue="Pelican Golf Club",
        location="Belleair, FL",
        prestige="Regular",
        tour="LPGA",
    ),
    TournamentEvent(
        name="CME Group Tour Championship",
        short_name="cme_tour_championship",
        start_date=date(2026, 11, 19),
        end_date=date(2026, 11, 22),
        venue="Tiburón Golf Club",
        location="Naples, FL",
        prestige="Signature",
        tour="LPGA",
    ),
    TournamentEvent(
        name="Grant Thornton Invitational",
        short_name="grant_thornton",
        start_date=date(2026, 12, 11),
        end_date=date(2026, 12, 13),
        venue="Tiburón Golf Club",
        location="Naples, FL",
        prestige="Regular",
        tour="LPGA",
    ),
]

# 2026 DP World Tour events, May 25 forward through the DP World Tour
# Championship in November. Dates per Sky Sports' 2026 DP World Tour
# schedule. Three Rolex Series events fall in this window (BMW PGA
# Championship, Abu Dhabi Championship, DP World Tour Championship);
# marked "Signature" prestige.
#
# Co-sanctioning note: the U.S. Open, Genesis Scottish Open, and The
# Open Championship are all co-sanctioned by the DP World Tour but
# appear in EVENTS_2026_PGA only — duplicating them here would cause
# events_in_range to double-count the same tournament and would surface
# as redundant secondary entries in the run summary. The events remain
# on the DP World Tour schedule in reality; their absence from this
# list is a deliberate de-duplication choice.
EVENTS_2026_DP_WORLD: list[TournamentEvent] = [
    TournamentEvent(
        name="Soudal Open",
        short_name="soudal_open",
        start_date=date(2026, 5, 21),
        end_date=date(2026, 5, 24),
        venue="Rinkven International Golf Club",
        location="Antwerp, Belgium",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Austrian Alpine Open",
        short_name="austrian_alpine",
        start_date=date(2026, 5, 28),
        end_date=date(2026, 5, 31),
        venue="Golfclub Kitzbühel-Schwarzsee-Reith",
        location="Kitzbühel, Austria",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="KLM Open",
        short_name="klm_open",
        start_date=date(2026, 6, 4),
        end_date=date(2026, 6, 7),
        venue="The International",
        location="Amsterdam, Netherlands",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Open d'Italia",
        short_name="italian_open",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 28),
        venue="Circolo Golf Torino",
        location="Turin, Italy",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="BMW International Open",
        short_name="bmw_international",
        start_date=date(2026, 7, 2),
        end_date=date(2026, 7, 5),
        venue="Golfclub München Eichenried",
        location="Munich, Germany",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="ISCO Championship",
        short_name="isco",
        start_date=date(2026, 7, 9),
        end_date=date(2026, 7, 12),
        venue="Hurstbourne Country Club",
        location="Louisville, KY",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Corales Puntacana Championship",
        short_name="puntacana",
        start_date=date(2026, 7, 16),
        end_date=date(2026, 7, 19),
        venue="Puntacana Resort & Club",
        location="Punta Cana, Dominican Republic",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Danish Golf Championship",
        short_name="danish_open",
        start_date=date(2026, 8, 13),
        end_date=date(2026, 8, 16),
        venue="Great Northern",
        location="Kerteminde, Denmark",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Betfred British Masters",
        short_name="british_masters",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 30),
        venue="The Belfry Hotel and Resort",
        location="Sutton Coldfield, England",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Omega European Masters",
        short_name="european_masters",
        start_date=date(2026, 9, 3),
        end_date=date(2026, 9, 6),
        venue="Crans-sur-Sierre Golf Club",
        location="Crans-Montana, Switzerland",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Amgen Irish Open",
        short_name="irish_open",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 13),
        venue="Trump International Golf Links",
        location="Doonbeg, Ireland",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="BMW PGA Championship",
        short_name="bmw_pga",
        start_date=date(2026, 9, 17),
        end_date=date(2026, 9, 20),
        venue="Wentworth Club",
        location="Virginia Water, England",
        prestige="Signature",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="FedEx Open de France",
        short_name="open_de_france",
        start_date=date(2026, 9, 24),
        end_date=date(2026, 9, 27),
        venue="Le Golf National",
        location="Saint-Quentin-en-Yvelines, France",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Alfred Dunhill Links Championship",
        short_name="dunhill_links",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        venue="Old Course St Andrews",
        location="St Andrews, Scotland",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Open de España",
        short_name="spanish_open",
        start_date=date(2026, 10, 8),
        end_date=date(2026, 10, 11),
        venue="Club de Campo Villa de Madrid",
        location="Madrid, Spain",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="DP World India Championship",
        short_name="india_championship",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 18),
        venue="Delhi Golf Club",
        location="New Delhi, India",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Genesis Championship",
        short_name="genesis_korea",
        start_date=date(2026, 10, 22),
        end_date=date(2026, 10, 25),
        venue="Woo Jeong Hills Country Club",
        location="Cheonan, South Korea",
        prestige="Regular",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="Abu Dhabi Championship",
        short_name="abu_dhabi",
        start_date=date(2026, 11, 5),
        end_date=date(2026, 11, 8),
        venue="Yas Links",
        location="Abu Dhabi, UAE",
        prestige="Signature",
        tour="DP_WORLD",
    ),
    TournamentEvent(
        name="DP World Tour Championship",
        short_name="dp_world_championship",
        start_date=date(2026, 11, 12),
        end_date=date(2026, 11, 15),
        venue="Jumeirah Golf Estates",
        location="Dubai, UAE",
        prestige="Signature",
        tour="DP_WORLD",
    ),
]

# Concatenated view — preserves the public name used by callers.
EVENTS_2026: list[TournamentEvent] = (
    EVENTS_2026_PGA + EVENTS_2026_LPGA + EVENTS_2026_DP_WORLD
)


_PRESTIGE_PRIORITY = {"Major": 0, "Signature": 1, "Regular": 2}

# Tour-of-origin priority for cross-tour tiebreak: PGA > LPGA > DP World.
# Lower number wins. Used as the primary sort key in active_event_window.
_TOUR_PRIORITY = {"PGA": 0, "LPGA": 1, "DP_WORLD": 2}


def active_event_window(
    today: date,
    pre_days: int = 3,
    post_days: int = 2,
) -> tuple[Optional[TournamentEvent], list[TournamentEvent]]:
    """Return (primary, secondaries) for events whose [start - pre_days,
    end + post_days] window contains today.

    Sort key (lower wins): tour priority (PGA > LPGA > DP World), then
    prestige (Major > Signature > Regular) as same-tour tiebreak, then
    proximity to today. The first event in sorted order is the primary;
    all remaining concurrent events are returned as secondaries (in the
    same priority order) for human-visibility surfacing in the run
    summary.

    Returns (None, []) when no event is active.
    """
    candidates: list[TournamentEvent] = []
    for event in EVENTS_2026:
        window_start = event.start_date - timedelta(days=pre_days)
        window_end = event.end_date + timedelta(days=post_days)
        if window_start <= today <= window_end:
            candidates.append(event)

    if not candidates:
        return (None, [])

    def _rank(e: TournamentEvent) -> tuple[int, int, int]:
        tour_p = _TOUR_PRIORITY.get(e.tour, 99)
        prestige_p = _PRESTIGE_PRIORITY.get(e.prestige, 99)
        proximity = abs((e.start_date - today).days)
        return (tour_p, prestige_p, proximity)

    candidates.sort(key=_rank)
    return (candidates[0], candidates[1:])


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


# Hashtag-based queries (#EventName + pain) were removed for Phase 1.5
# because hashtags rarely appear in Reddit thread titles. When X scout
# activates in Phase 2, restore hashtag queries via a parallel
# event_query_combos_x() function or conditional logic.
def event_query_combos(event: TournamentEvent) -> list[str]:
    """Generate 6-10 search queries that cross event identifiers with pain anchors.

    Skips sponsorship/marketing-skewed combos in favor of phrasings most likely
    to surface customer-voice content (forum posts, Reddit threads, complaints).
    """
    return [
        "tournament weekend golf sunglasses",
        "golf weekend polarized lenses",
        "watching golf TV eye strain",
        f"{event.venue} polarized",
        f"{event.name} sunglasses recommendation",
        f"{event.name} golf vision",
        f"watching {event.name} polarized",
        f"{event.name} eye strain",
    ]


def event_verification_keywords(event: TournamentEvent) -> list[str]:
    """Return strict verification keywords for an event. A lead title must
    contain at least one of these as a substring (case-insensitive) to
    qualify as tournament-relevant.

    Keywords derived from event metadata plus a small set of strict
    tournament-context phrases.
    """
    kws: list[str] = []

    # Full event name only — bare short forms like "pga" or "truist" match
    # unrelated content (PGA Tour broadly, Truist Bank, etc.).
    kws.append(event.name.lower())

    # Venue full name and short form
    kws.append(event.venue.lower())
    # If venue is multi-word, also accept the first 2 words
    # e.g., "Quail Hollow Club" → also accept "quail hollow"
    venue_words = event.venue.split()
    if len(venue_words) > 2:
        kws.append(" ".join(venue_words[:2]).lower())

    # Hashtags as plain text (without #) — for the rare case someone writes
    # the hashtag-formatted text in Reddit
    for h in event.hashtags:
        kws.append(h.lstrip("#").lower())

    # Strict tournament-context phrases (event-agnostic). Catch threads that
    # are clearly about a tournament without naming a specific one.
    kws.extend([
        "the tournament this week",
        "watching the tournament",
        "this weekend's tournament",
        "tournament sunday",
        "the final round",
    ])

    # Dedupe preserving order
    return list(dict.fromkeys(kws))
