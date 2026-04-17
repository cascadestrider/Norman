import sqlite3
from datetime import date
from norman.models import Lead


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
            date_found  TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN source TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN source_type TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def get_seen_urls(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT url FROM leads").fetchall()
    return {row[0] for row in rows}


def save_lead(conn: sqlite3.Connection, lead: Lead, strategy: str = ""):
    conn.execute(
        """INSERT OR IGNORE INTO leads
           (url, title, score, keywords, strategy, source, source_type, date_found)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            lead.url,
            lead.title,
            lead.score,
            ",".join(lead.keywords),
            strategy,
            lead.source,
            lead.source_type,
            str(date.today()),
        ),
    )
    conn.commit()
