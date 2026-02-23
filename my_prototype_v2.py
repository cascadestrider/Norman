import os
import sqlite3
import requests
from datetime import date
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from serpapi import GoogleSearch

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/'
}

KEYWORDS = {
    "blinded by glare": 10, "can't see in sun": 10,
    "fog up": 9, "glasses fog": 9, "fogging up": 9,
    "eye strain": 8, "ansi z87": 8, "headache sun": 8,
    "ballistic": 7, "anti-fog": 7, "tactical eyewear": 7,
    "glare": 6, "polarized": 5, "scratch": 5,
    "distortion": 5, "blinded": 6, "sun glare": 7,
    "can't see": 6, "eye protection": 6, "shooting glasses": 7,
    "uv protection": 5, "lens quality": 4, "wrap around": 4,
    "eye injury": 8, "vision problems": 6, "bright light": 5,
}

SEED_QUERIES = [
    "sunglasses fog up site:reddit.com",
    "blinded by glare outdoor forum",
    "ballistic eyewear recommendation",
    "best anti-glare tactical sunglasses review",
    "eye strain driving bright sun forum",
    "shooting glasses fogging up problem",
]

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("scout_log.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            url        TEXT UNIQUE,
            title      TEXT,
            score      INTEGER,
            keywords   TEXT,
            strategy   TEXT,
            date_found TEXT
        )
    """)
    conn.commit()
    return conn

def already_visited(conn, url):
    row = conn.execute("SELECT 1 FROM leads WHERE url=?", (url,)).fetchone()
    return row is not None

def save_lead(conn, url, title, score, keywords, strategy):
    conn.execute("""INSERT OR IGNORE INTO leads
        (url, title, score, keywords, strategy, date_found)
        VALUES (?,?,?,?,?,?)""",
        (url, title, score, ",".join(keywords), strategy, str(date.today())))
    conn.commit()

# --- SCORING ---
def score_page(text):
    text_l = text.lower()
    found, total = [], 0
    for kw, weight in KEYWORDS.items():
        count = text_l.count(kw)
        if count:
            found.append(kw)
            total += weight * min(count, 3)
    return found, min(total, 100)

# --- URL DISCOVERY ---
def discover_urls():
    urls = []
    for query in SEED_QUERIES:
        try:
            search = GoogleSearch({
                "q": query,
                "api_key": os.getenv("SERP_API_KEY"),
                "num": 5
            })
            results = search.get_dict()
            for r in results.get("organic_results", []):
                urls.append(r["link"])
        except Exception as e:
            print(f"❌ Search failed for '{query}': {e}")
    return list(set(urls))

# --- AI ANALYSIS ---
def get_ai_recommendation(title, content_snippet):
    print("🎯 AI analyzing page for friction points...")
    product_focus = "Tactical/Sport sunglasses with Zero-Glare polarization, Ballistic protection, and Anti-fog tech."
    prompt = f"""
    The following content is from a webpage titled: {title}
    Content: {content_snippet[:1500]}

    TASK:
    1. Identify a specific problem (friction point) regarding vision, glare, eye protection, or gear failure.
    2. Create a High-Conversion ad strategy for our product: {product_focus}
    3. The ad headline must directly address the user's struggle.

    Format your response as:
    PROBLEM DETECTED: [Briefly describe]
    WHY OUR PRODUCT WINS: [Specific feature match]
    AD HEADLINE: [Catchy, solution-oriented text]
    AD PLACEMENT TIP: [Where/how to place this ad on the page]
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# --- REPORT ---
def generate_report(results):
    if not results:
        print("📭 No leads found today.")
        return
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{date.today()}.md"
    with open(filename, "w") as f:
        f.write(f"# AI Ad Scout Report — {date.today()}\n\n")
        f.write(f"**Total leads found:** {len(results)}\n\n---\n\n")
        for score, url, title, strategy in sorted(results, reverse=True):
            f.write(f"## [{title}]({url})\n")
            f.write(f"**Score:** {score}/100\n\n")
            f.write(f"{strategy}\n\n---\n\n")
    print(f"📊 Report saved to {filename}")

# --- DAILY RUNNER ---
def daily_run():
    print(f"\n🚀 Scout starting — {date.today()}")
    conn = init_db()
    urls = discover_urls()
    print(f"🔍 Found {len(urls)} candidate URLs")
    results = []

    for url in urls:
        if already_visited(conn, url):
            print(f"⏭️  Already visited: {url}")
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            text = " ".join(p.text for p in soup.find_all(["p", "div"]) if len(p.text) > 30)
            title = soup.title.string if soup.title else "Unknown"
            found_kws, score = score_page(text)

            print(f"📄 Score {score}: {title[:60]}")

            if score >= 20:
                strategy = get_ai_recommendation(title, text)
                save_lead(conn, url, title, score, found_kws, strategy)
                results.append((score, url, title, strategy))
                print(f"✅ Lead saved!")
            else:
                print(f"⚖️  Score too low, skipping AI.")
        except Exception as e:
            print(f"❌ Failed on {url}: {e}")

    generate_report(results)
    print("✅ Scout run complete.")

# --- MAIN ---
import sys
if __name__ == "__main__":
    if "--once" in sys.argv:
        daily_run()
        sys.exit(0)
    else:
        print("AI Ad Scout - runs daily at 6am")
        daily_run()
        scheduler = BlockingScheduler()
        scheduler.add_job(daily_run, "cron", hour=6, minute=0)
        scheduler.start()
