import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
SERP_API_KEY = os.getenv("SERP_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("NORMAN_ANTHROPIC_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Semantic scoring toggle (A/B vs keyword scoring) ---
USE_SEMANTIC_SCORING = os.getenv("USE_SEMANTIC_SCORING", "0") == "1"

# --- Per-lead ad generation toggle ---
# When off (default, "0"), the orchestrator skips the Analyst stage entirely:
# customer_voice leads are saved with strategy='' and Discord/markdown fall
# back to a condensed daily summary. Weekly synthesis (synthesizer.py) is the
# primary creative output. Set to "1" to restore the per-lead ad-copy path
# as an A/B fallback.
USE_PER_LEAD_ADS = os.getenv("USE_PER_LEAD_ADS", "0") == "1"

# --- Event monitoring (Phase 1: Reddit-only) ---
# Surfaces tournament-window leads via the event_window flag without
# modifying score. Disable by setting EVENT_MONITORING_ENABLED=0.
EVENT_MONITORING_ENABLED = os.getenv("EVENT_MONITORING_ENABLED", "1") == "1"
EVENT_PRE_DAYS = int(os.getenv("EVENT_PRE_DAYS", "3"))
EVENT_POST_DAYS = int(os.getenv("EVENT_POST_DAYS", "2"))

# --- Scoring ---
SCORE_THRESHOLD = 30

# Legacy keyword scorer — only used when USE_SEMANTIC_SCORING=0.
# Refreshed 2026-04-21 against client pain-point input (golf vision,
# screen visibility, headaches/sensitivity). Weights tuned to favor
# language that signals real customer distress over generic product vocab.
KEYWORDS = {
    # Golf vision (file 1)
    "can't see golf ball": 10,
    "ball tracking sunglasses": 9,
    "reading greens": 9,
    "depth perception sunglasses": 9,
    "water hazard glare": 8,
    "polarization percentage": 7,
    "pink purple golf lenses": 7,
    "golf lens color": 6,
    "golf sunglasses": 5,

    # Screen visibility (file 2)
    "can't see phone": 10,
    "can't read watch": 9,
    "heads up display sunglasses": 9,
    "phone screen pixelated": 9,
    "phone screen dark sunglasses": 8,
    "GPS screen visibility": 8,
    "HUD compatible sunglasses": 7,
    "screen goes dark": 7,

    # Headaches / sensitivity (file 3)
    "sunglasses cause headache": 10,
    "sunglasses headache": 9,
    "post concussion sunglasses": 10,
    "concussion light sensitivity": 10,
    "photophobia sunglasses": 9,
    "eyes hurt sunglasses": 9,
    "light sensitivity sunglasses": 9,
    "sunglasses eye strain": 8,
    "sunglasses too dark": 7,
    "color distortion sunglasses": 7,
    "LED glare sunglasses": 7,
    "99 percent polarized problems": 7,
    "alternatives to polarized": 6,
    "do I need polarized": 5,

    # Cross-cutting safety net (applies across files 1-3)
    "polarized sunglasses review": 4,
    "activity specific sunglasses": 5,
    "color accuracy sunglasses": 6,

    # Fishing — preserved from prior config (client input did not cover fishing)
    "polarized fishing sunglasses": 5,
    "fishing water glare": 6,
    "sight fishing sunglasses": 5,
}

# --- Segments ---
# Added "sensitivity" as a fifth segment (2026-04-21) based on client
# pain-point input. This captures post-concussion, migraine-prone, and
# photophobia-driven shoppers — an underserved, high-conversion audience.
SEGMENTS = ["golf", "fishing", "motorcycle", "commuter", "sensitivity"]

# --- Excluded Domains (Google scout) ---
EXCLUDED_DOMAINS = [
    "merriam-webster.com",
    "dictionary.com",
    "definitions.net",
    "wiktionary.org",
    "wikipedia.org",
    "thefreedictionary.com",
    "oed.com",
    "dictionary.cambridge.org",
    "britannica.com",
]

# --- Reddit ---
REDDIT_HEADERS = {
    "User-Agent": "AdScout/1.0 (lead research tool; contact via github)"
}

REDDIT_SUBREDDITS = {
    # Golf — refreshed per client input (file 1)
    "golf": ["golf", "golfequipment", "golfing", "discgolf"],

    # Fishing — preserved (client input did not cover fishing)
    "fishing": ["fishing", "flyfishing", "bassfishing", "kayakfishing"],

    # Motorcycle — preserved; overlaps with screen-visibility pain (file 2)
    "motorcycle": ["motorcycles", "motocamping", "rideIt", "advriding"],

    # Commuter — preserved; overlaps with screen-visibility pain (file 2)
    "commuter": ["cycling", "bikecommuting", "running", "hiking", "hunting"],

    # Sensitivity — new per client input (file 3)
    # Post-concussion, migraine, and photophobia communities
    "sensitivity": ["Concussion", "TBI", "migraine", "optometry", "sunglasses", "health"],
}

# Reddit search terms: refreshed per client input with fishing preserved.
# Used by the Reddit scout's search mode across subreddits.
REDDIT_SEARCH_TERMS = [
    # Golf (file 1)
    "can't see golf ball sunglasses",
    "polarized sunglasses golf",
    "golf sunglasses depth perception",
    "reading greens sunglasses",
    "best lens color for golf",
    "polarization percentage for golf",

    # Screen visibility (file 2)
    "can't see phone with sunglasses",
    "polarized sunglasses phone screen",
    "can't read watch sunglasses",
    "sunglasses GPS HUD",

    # Headaches / sensitivity (file 3)
    "sunglasses give me a headache",
    "polarized sunglasses headache",
    "post concussion sunglasses",
    "concussion light sensitivity sunglasses",
    "photophobia sunglasses",
    "sunglasses eyes hurt",
    "sunglasses too dark",
    "do I need polarized sunglasses",
    "sunglasses color distortion",
    "LED glare sunglasses",
    "alternatives to polarized sunglasses",

    # Fishing — preserved
    "polarized sunglasses fishing",
    "fishing sunglasses glare water",

    # Cross-cutting safety net
    "sunglasses recommendation",
    "best polarized sunglasses",
]

# --- Google (SerpAPI) ---
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://www.google.com/",
}

# GOOGLE_QUERIES: refreshed 2026-04-21 from client pain-point files.
# Golf, motorcycle, commuter, sensitivity updated; fishing preserved.
GOOGLE_QUERIES = {
    # Golf — file 1
    "golf": [
        "can't see golf ball sunglasses",
        "best sunglasses for golf ball tracking",
        "polarized sunglasses golf yes or no",
        "golf sunglasses depth perception",
        "reading greens sunglasses",
        "golf sunglasses glare water hazard",
        "best lens color for golf sunglasses",
        "golf sunglasses not pink purple alternatives",
        "polarization percentage for golf",
        "color contrast golf sunglasses",
        "sunglasses improve golf game",
        "golf sunglasses visual handicap",
        "best golf sunglasses 2025",
        "sunglasses for golf Reddit",
        "golf tournament sunglasses",
    ],

    # Motorcycle — file 2 (screen visibility overlaps heavily with riders)
    "motorcycle": [
        "motorcycle sunglasses HUD compatible",
        "polarized sunglasses heads up display motorcycle",
        "can't see GPS with sunglasses motorcycle",
        "best motorcycle sunglasses phone screen",
        "polarized sunglasses motorcycle dashboard",
    ],

    # Commuter — file 2 + file 3
    "commuter": [
        "can't see phone sunglasses",
        "polarized sunglasses phone screen dark",
        "sunglasses phone screen pixelation",
        "can't read watch with sunglasses",
        "see through polarized lenses phone",
        "best sunglasses for phone screen visibility",
        "sunglasses too dark phone screen",
        "polarized sunglasses GPS screen visibility",
    ],

    # Sensitivity — file 3 (new segment)
    "sensitivity": [
        "sunglasses causing headaches",
        "why do my sunglasses give me a headache",
        "polarized sunglasses headache",
        "sunglasses eye strain",
        "post concussion sunglasses",
        "concussion light sensitivity sunglasses",
        "sunglasses too dark solution",
        "do I need polarized sunglasses",
        "sunglasses color distortion",
        "LED glare sunglasses",
        "sunglasses not accurate color",
        "alternatives to polarized sunglasses",
        "best sunglasses for light sensitivity",
        "photophobia sunglasses",
        "sunglasses eyes hurt",
        "99 percent polarized sunglasses problems",
    ],

    # Fishing — preserved from prior config (client input did not cover fishing)
    "fishing": [
        "polarized sunglasses fishing glare water review",
        "polarized fishing sunglasses water glare comparison",
        "fishing sunglasses eye strain forum",
    ],

    # Cross-cutting safety-net queries that apply across multiple segments
    "general": [
        "polarized sunglasses review",
        "sunglasses that work with phones",
        "sunglasses color distortion",
        "activity specific sunglasses",
        "best sunglasses 2025",
        "sunglasses recommendation reddit",
        "polarization percentage explained",
    ],
}

# --- YouTube ---
# YouTube pools favor queries that match review/discussion video formats.
YOUTUBE_QUERIES = {
    "golf": [
        "best sunglasses for golf review",
        "golf sunglasses ball tracking",
        "polarized sunglasses golf test",
        "reading greens with sunglasses",
        "best golf sunglasses 2025",
    ],
    "motorcycle": [
        "motorcycle sunglasses HUD review",
        "best riding sunglasses phone screen",
    ],
    "commuter": [
        "polarized sunglasses phone screen test",
        "best driving sunglasses review",
        "sunglasses color distortion review",
    ],
    "sensitivity": [
        "sunglasses headache review",
        "post concussion sunglasses review",
        "sunglasses for light sensitivity review",
        "polarized vs non polarized headache",
        "alternatives to polarized sunglasses review",
    ],
    # Fishing — preserved
    "fishing": [
        "polarized sunglasses fishing review",
        "fishing sunglasses glare water",
    ],
}

# --- LLM Token Pricing ($ per million tokens) ---
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input": 0.25, "output": 1.25},
}

# --- Product context for Analyst ---
# Updated 2026-04-21 to reflect client positioning input across all three
# pain-point files: activity-tuned polarization (not 99%), color accuracy
# over darkness, screen/HUD compatibility, sensitivity-friendly tuning.
PRODUCT_FOCUS = (
    "Torque Optics — Sunglasses with proprietary activity-tuned polarization "
    "technology. Not 99% polarized (which causes headaches, phone screen "
    "blackout, and color distortion) and not zero polarized (which doesn't "
    "cut glare). The right polarization percentage for each activity: "
    "golf (preserves ball tracking + depth perception), fishing (max water "
    "glare cut), commuter/riding (phone + GPS + HUD compatible), sensitivity "
    "(minimal darkness, color-accurate, designed for post-concussion and "
    "photophobia). Color accuracy over aggressive tinting. Alternatives to "
    "the pink/purple 'golf lens' and the 99% 'pro fishing' assumptions that "
    "dominate the market."
)
