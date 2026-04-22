import sqlite3
from datetime import date, timedelta
from norman.models import Lead

REVISIT_WINDOW_DAYS = 14
SCORE_BUMP_THRESHOLD = 5


def init_db(path: str = "scout_log.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT UNIQUE,
            title       TEXT,
            score       INTEGER,
            keywords    TEXT,
            strategy    TEXT,
            source      TEXT,
            source_type TEXT,
            date_found  TEXT,
            last_seen   TEXT
        )
    """)
    for sql in (
        "ALTER TABLE leads ADD COLUMN source TEXT",
        "ALTER TABLE leads ADD COLUMN source_type TEXT",
        "ALTER TABLE leads ADD COLUMN last_seen TEXT",
    ):
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    # Backfill last_seen for rows that predate the column so the 14-day
    # filter works correctly on the first post-migration run.
    conn.execute(
        "UPDATE leads SET last_seen = date_found WHERE last_seen IS NULL"
    )
    conn.commit()
    return conn


def get_seen_urls(conn: sqlite3.Connection) -> set[str]:
    """Return URLs seen within the past REVISIT_WINDOW_DAYS. URLs older than
    the window fall out of the set so scouts will re-fetch and re-score them.
    """
    cutoff = (date.today() - timedelta(days=REVISIT_WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT url FROM leads WHERE last_seen >= ?", (cutoff,)
    ).fetchall()
    return {row[0] for row in rows}


def save_lead(conn: sqlite3.Connection, lead: Lead, strategy: str = "") -> str:
    """Insert a new lead or update an existing one. Returns the save status:
    "new"       — first time this URL was saved
    "updated"   — URL existed; new score > old score + SCORE_BUMP_THRESHOLD
    "revisited" — URL existed; score did not meaningfully change
    """
    today = str(date.today())
    existing = conn.execute(
        "SELECT score FROM leads WHERE url = ?", (lead.url,)
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO leads
               (url, title, score, keywords, strategy, source, source_type,
                date_found, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                lead.url,
                lead.title,
                lead.score,
                ",".join(lead.keywords),
                strategy,
                lead.source,
                lead.source_type,
                today,
                today,
            ),
        )
        conn.commit()
        return "new"

    old_score = existing[0] or 0
    if lead.score > old_score + SCORE_BUMP_THRESHOLD:
        conn.execute(
            """UPDATE leads
               SET last_seen = ?, score = ?, title = ?, source_type = ?
               WHERE url = ?""",
            (today, lead.score, lead.title, lead.source_type, lead.url),
        )
        conn.commit()
        return "updated"

    conn.execute(
        "UPDATE leads SET last_seen = ? WHERE url = ?",
        (today, lead.url),
    )
    conn.commit()
    return "revisited"
