import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
SERP_API_KEY = os.getenv("SERP_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("NORMAN_ANTHROPIC_KEY", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Scoring ---
SCORE_THRESHOLD = 30

KEYWORDS = {
    "blinded by glare": 10,
    "can't see in sun": 10,
    "eye strain": 8,
    "ansi z87": 8,
    "headache sun": 8,
    "eye injury": 8,
    "shooting glasses": 7,
    "sun glare": 7,
    "glare": 6,
    "blinded": 6,
    "can't see": 6,
    "eye protection": 6,
    "vision problems": 6,
    "polarized": 5,
    "distortion": 5,
    "uv protection": 5,
    "bright light": 5,
    "lens quality": 4,
    "wrap around": 4,
}

# --- Segments ---
SEGMENTS = ["golf", "fishing", "motorcycle", "commuter"]

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
    "fishing": ["fishing", "flyfishing", "bassfishing", "kayakfishing"],
    "golf": ["golf", "golfequipment", "discgolf"],
    "motorcycle": ["motorcycles", "motocamping", "rideIt", "advriding"],
    "commuter": ["cycling", "bikecommuting", "running", "hiking", "hunting"],
}

REDDIT_SEARCH_TERMS = [
    "sunglasses glare",
    "eye strain",
    "polarized sunglasses",
    "can't see in sun",
    "blinded glare",
    "shooting glasses",
    "uv protection",
    "lens distortion",
]

# --- Google (SerpAPI) ---
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://www.google.com/",
}

GOOGLE_QUERIES = {
    "fishing": [
        "polarized sunglasses fishing glare water review",
        "polarized fishing sunglasses water glare comparison",
        "fishing sunglasses eye strain forum",
    ],
    "golf": [
        "best sunglasses for golf glare reduction review",
        "golf sunglasses eye strain bright sun forum",
        "anti-glare sunglasses for golfers recommendation",
    ],
    "motorcycle": [
        "motorcycle riding sunglasses glare protection",
        "best sunglasses for motorcycle riding forum",
        "motorcycle riding sunglasses UV protection review",
    ],
    "commuter": [
        "best sunglasses for driving glare reduction review",
        "driving into sun glare eye strain forum",
        "best driving sunglasses glare reduction review",
        "best anti-glare sunglasses review",
        "eye strain driving bright sun forum",
        "sunglasses fog up reddit",
        "blinded by glare outdoor forum",
    ],
}

# --- YouTube ---
YOUTUBE_QUERIES = {
    "fishing": [
        "polarized sunglasses fishing review",
        "fishing sunglasses glare water",
    ],
    "golf": [
        "best sunglasses for golf review",
        "golf sunglasses glare bright sun",
    ],
    "motorcycle": [
        "motorcycle sunglasses review",
        "best riding sunglasses UV protection",
    ],
    "commuter": [
        "best driving sunglasses glare review",
        "shooting glasses review",
        "best polarized sunglasses outdoor",
        "anti-glare sunglasses review",
    ],
}

# --- LLM Token Pricing ($ per million tokens) ---
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input": 0.25, "output": 1.25},
}

# --- Product context for Analyst ---
PRODUCT_FOCUS = (
    "Torque Optics — Sunglasses with proprietary polarization lens technology. "
    "Zero-glare polarization for specific activities (golf, fishing, riding, driving). "
    "Superior lens clarity vs mainstream brands. Activity-specific lens tuning — "
    "not generic polarization. UV protection + anti-fog options."
)
