import os
import sqlite3
import requests
import sys
import time
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

REDDIT_HEADERS = {
    'User-Agent': 'AdScout/1.0 (lead research tool; contact via github)'
}

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

def is_excluded(url):
    return any(domain in url for domain in EXCLUDED_DOMAINS)

KEYWORDS = {
    "blinded by glare": 10, "can't see in sun": 10,
    "eye strain": 8, "ansi z87": 8, "headache sun": 8,
    "glare": 6, "polarized": 5,
    "distortion": 5, "blinded": 6, "sun glare": 7,
    "can't see": 6, "eye protection": 6, "shooting glasses": 7,
    "uv protection": 5, "lens quality": 4, "wrap around": 4,
    "eye injury": 8, "vision problems": 6, "bright light": 5,
}

SEED_QUERIES = [
    "sunglasses fog up reddit",
    "blinded by glare outdoor forum",
    "best anti-glare sunglasses review",
    "eye strain driving bright sun forum",
    # driving & glare
    "best sunglasses for driving glare reduction review",
    "driving into sun glare eye strain forum",
    "best driving sunglasses glare reduction review",
    # cycling & eye protection
    "best glasses for cycling outdoor forum",
    "cycling eye protection polarized",
    # fishing & polarized
    "polarized sunglasses fishing glare water review",
    "polarized fishing sunglasses water glare comparison",
    # hiking & sun protection
    "hiking sunglasses uv sun protection recommendation",
    # motorcycle
    "motorcycle riding sunglasses glare protection",
    "best sunglasses for motorcycle riding forum",
    "motorcycle riding sunglasses UV protection review",
]

REDDIT_SUBREDDITS = [
    "hunting", "fishing",
]

REDDIT_SEARCH_TERMS = [
    "sunglasses glare", "eye strain",
    "shooting glasses", "polarized sunglasses"
]

YOUTUBE_SEARCH_TERMS = [
    "shooting glasses review",
    "best polarized sunglasses outdoor",
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
            source     TEXT,
            date_found TEXT
        )
    """)
    # Migrate existing databases that pre-date the source column
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN source TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    return conn

def already_visited(conn, url):
    row = conn.execute("SELECT 1 FROM leads WHERE url=?", (url,)).fetchone()
    return row is not None

def save_lead(conn, url, title, score, keywords, strategy, source="web"):
    conn.execute("""INSERT OR IGNORE INTO leads
        (url, title, score, keywords, strategy, source, date_found)
        VALUES (?,?,?,?,?,?,?)""",
        (url, title, score, ",".join(keywords), strategy, source, str(date.today())))
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

# --- GOOGLE URL DISCOVERY ---
def discover_urls_google():
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
                link = r["link"]
                if not is_excluded(link):
                    urls.append(link)
        except Exception as e:
            print(f"❌ Google search failed for '{query}': {e}")
    return list(set(urls))

# --- REDDIT DISCOVERY ---
def discover_urls_reddit():
    urls = []
    print("🔴 Scouting Reddit...")

    # Search within specific subreddits
    for sub in REDDIT_SUBREDDITS:
        for term in REDDIT_SEARCH_TERMS[:2]:  # limit to 2 terms per sub
            try:
                api_url = f"https://www.reddit.com/r/{sub}/search.json?q={term}&sort=new&limit=5&restrict_sr=1"
                resp = requests.get(api_url, headers=REDDIT_HEADERS, timeout=10)
                if resp.status_code == 200:
                    posts = resp.json().get("data", {}).get("children", [])
                    for post in posts:
                        data = post.get("data", {})
                        permalink = data.get("permalink", "")
                        if permalink:
                            full_url = f"https://www.reddit.com{permalink}"
                            urls.append(full_url)
                time.sleep(1)  # be polite to Reddit
            except Exception as e:
                print(f"❌ Reddit search failed for r/{sub} '{term}': {e}")

    print(f"🔴 Reddit found {len(urls)} candidate URLs")
    return list(set(urls))

# --- REDDIT PAGE SCRAPER ---
def scrape_reddit_post(url):
    try:
        json_url = url.rstrip("/") + ".json?limit=50"
        resp = requests.get(json_url, headers=REDDIT_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        post_data = data[0]["data"]["children"][0]["data"]
        title = post_data.get("title", "Reddit Post")
        body = post_data.get("selftext", "")
        comments = []
        for comment in data[1]["data"]["children"]:
            c = comment.get("data", {})
            if "body" in c:
                comments.append(c["body"])
        full_text = f"{title} {body} " + " ".join(comments[:20])
        return title, full_text
    except Exception as e:
        print(f"❌ Reddit scrape failed: {e}")
        return None, None

# --- YOUTUBE DISCOVERY & SCRAPING ---
def discover_and_scrape_youtube():
    leads = []
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("⚠️ No YOUTUBE_API_KEY found, skipping YouTube")
        return leads

    print("📺 Scouting YouTube...")
    for term in YOUTUBE_SEARCH_TERMS:
        try:
            # Search for videos
            search_url = "https://www.googleapis.com/youtube/v3/search"
            resp = requests.get(search_url, params={
                "q": term,
                "key": api_key,
                "part": "snippet",
                "type": "video",
                "maxResults": 5,
                "order": "relevance"
            }, timeout=10)

            if resp.status_code != 200:
                print(f"❌ YouTube search failed for '{term}': {resp.status_code}")
                continue

            videos = resp.json().get("items", [])
            for video in videos:
                video_id = video["id"]["videoId"]
                title = video["snippet"]["title"]
                description = video["snippet"]["description"]
                url = f"https://www.youtube.com/watch?v={video_id}"

                # Get comments
                comments_url = "https://www.googleapis.com/youtube/v3/commentThreads"
                c_resp = requests.get(comments_url, params={
                    "videoId": video_id,
                    "key": api_key,
                    "part": "snippet",
                    "maxResults": 50,
                    "order": "relevance"
                }, timeout=10)

                comment_text = ""
                if c_resp.status_code == 200:
                    for item in c_resp.json().get("items", []):
                        comment_text += item["snippet"]["topLevelComment"]["snippet"]["textDisplay"] + " "

                full_text = f"{title} {description} {comment_text}"
                leads.append((url, title, full_text))

        except Exception as e:
            print(f"❌ YouTube failed for '{term}': {e}")

    print(f"📺 YouTube found {len(leads)} candidate videos")
    return leads

# --- AI ANALYSIS ---
def get_ai_recommendation(title, content_snippet, source="web"):
    print(f"🎯 AI analyzing [{source}]: {title[:50]}...")
    product_focus = "Tactical/Sport sunglasses with Zero-Glare polarization, Ballistic protection, and Anti-fog tech."
    prompt = f"""
    The following content is from a {source} page titled: {title}
    Content: {content_snippet[:1500]}

    TASK:
    1. Identify a specific problem (friction point) regarding vision, glare, eye protection, or gear failure.
    2. Create a High-Conversion ad strategy for our product: {product_focus}
    3. The ad headline must directly address the user's struggle.

    Format your response as:
    PROBLEM DETECTED: [Briefly describe]
    WHY OUR PRODUCT WINS: [Specific feature match]
    AD HEADLINE: [Catchy, solution-oriented text]
    AD PLACEMENT TIP: [Where/how to place this ad]
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# --- REPORT ---
def generate_report(results):
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{date.today()}.md"
    with open(filename, "w") as f:
        f.write(f"# AI Ad Scout Report — {date.today()}\n\n")
        if not results:
            f.write("**Status:** Scout ran successfully — no new leads found today.\n\n")
            f.write("All discovered URLs were either previously visited or scored below threshold.\n")
        else:
            f.write(f"**Total leads found:** {len(results)}\n\n---\n\n")
            for score, url, title, strategy, source in sorted(results, reverse=True):
                f.write(f"## [{title}]({url})\n")
                f.write(f"**Source:** {source.upper()}  |  **Score:** {score}/100\n\n")
                f.write(f"{strategy}\n\n---\n\n")
    print(f"📊 Report saved to {filename}")
    if not results:
        print("📭 No new leads found today.")

# --- DAILY RUNNER ---
def daily_run():
    print(f"\n🚀 Scout starting — {date.today()}")
    conn = init_db()
    results = []

    # --- GOOGLE ---
    google_urls = discover_urls_google()
    print(f"🔍 Google found {len(google_urls)} candidate URLs")
    for url in google_urls:
        if already_visited(conn, url):
            print(f"⏭️  Already visited: {url[:60]}")
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            text = " ".join(p.text for p in soup.find_all(["p", "div"]) if len(p.text) > 30)
            title = soup.title.string if soup.title else "Unknown"
            found_kws, score = score_page(text)
            print(f"📄 [Google] Score {score}: {title[:50]}")
            if score >= 20:
                strategy = get_ai_recommendation(title, text, "web")
                save_lead(conn, url, title, score, found_kws, strategy, "google")
                results.append((score, url, title, strategy, "google"))
                print(f"✅ Lead saved!")
        except Exception as e:
            print(f"❌ Failed on {url[:60]}: {e}")

    # --- REDDIT ---
    reddit_urls = discover_urls_reddit()
    for url in reddit_urls:
        if already_visited(conn, url):
            continue
        title, text = scrape_reddit_post(url)
        if not title or not text:
            continue
        found_kws, score = score_page(text)
        print(f"📄 [Reddit] Score {score}: {title[:50]}")
        if score >= 20:
            strategy = get_ai_recommendation(title, text, "reddit")
            save_lead(conn, url, title, score, found_kws, strategy, "reddit")
            results.append((score, url, title, strategy, "reddit"))
            print(f"✅ Reddit lead saved!")
        time.sleep(1)

    # --- YOUTUBE ---
    youtube_leads = discover_and_scrape_youtube()
    for url, title, text in youtube_leads:
        if already_visited(conn, url):
            continue
        found_kws, score = score_page(text)
        print(f"📄 [YouTube] Score {score}: {title[:50]}")
        if score >= 20:
            strategy = get_ai_recommendation(title, text, "youtube")
            save_lead(conn, url, title, score, found_kws, strategy, "youtube")
            results.append((score, url, title, strategy, "youtube"))
            print(f"✅ YouTube lead saved!")

    generate_report(results)
    print(f"✅ Scout run complete. {len(results)} leads found today.")

# --- MAIN ---
import sys
if __name__ == "__main__":
    if "--once" in sys.argv:
        daily_run()
        sys.exit(0)
    else:
        print("AI Ad Scout - runs daily at 9am")
        daily_run()
        scheduler = BlockingScheduler()
        scheduler.add_job(daily_run, "cron", hour=9, minute=0)
        scheduler.start()
