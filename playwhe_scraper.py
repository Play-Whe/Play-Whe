"""
Play Whe Results Scraper — Prototype
--------------------------------------
Polls a public Play Whe results page, detects new draws, stores them
in a local SQLite database, and exports a results.json file that the
live site (play-whe.com) fetches directly. Designed to run on a
schedule (cron / GitHub Actions) shortly after each draw time.

Draw times (Mon-Sat): 10:30 AM, 1:00 PM, 4:00 PM, 6:30 PM (AST, UTC-4)

IMPORTANT NOTES BEFORE YOU RUN THIS:
1. Source: nlcbplaywhelotto.com — confirmed reachable (not blocked by
   robots.txt) and its content was checked live against today's date
   (22-Aug-2026) before this was written, so the parser below is
   built from real page text, not a guess.
2. Run this politely: don't poll more than once every 1-2 minutes,
   and only during a short window after each scheduled draw time.
3. This environment (Claude's sandbox) has no live network access,
   so this script has NOT been executed against the real site.
   Test it yourself in an environment with internet access, and
   inspect the actual page HTML (right-click > Inspect) to confirm
   the selectors match before relying on it.
4. Respect the target site's terms of use. This is a bootstrap
   solution for prototyping — see the plan to seek official NLCB
   data access once the app has traction.

Requirements:
    pip install requests beautifulsoup4 --break-system-packages
"""

import sqlite3
import logging
import re
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SOURCE_URL = "https://www.nlcbplaywhelotto.com/nlcb-play-whe-results/"
DB_PATH = "playwhe.db"
JSON_PATH = "results.json"          # committed to the repo, fetched by the site
JSON_MAX_DRAWS = 500                # keep the fetched file small and fast
USER_AGENT = "PlayWheCompanionApp/0.1 (prototype; contact: you@example.com)"
REQUEST_TIMEOUT = 15  # seconds

# The 36 marks, used to validate/normalize whatever text we scrape.
MARKS = {
    1: "Centipede", 2: "Old Lady", 3: "Carriage", 4: "Dead Man",
    5: "Parson Man", 6: "Belly", 7: "Hog", 8: "Tiger", 9: "Cattle",
    10: "Monkey", 11: "Corbeau", 12: "King", 13: "Crapaud", 14: "Money",
    15: "Sick Woman", 16: "Jamette", 17: "Pigeon", 18: "Water Boat",
    19: "Horse", 20: "Dog", 21: "Mouth", 22: "Rat", 23: "House",
    24: "Queen", 25: "Morocoy", 26: "Fowl", 27: "Little Snake",
    28: "Red Fish", 29: "Opium Man", 30: "House Cat", 31: "Parson Wife",
    32: "Shrimps", 33: "Spider", 34: "Blind Man", 35: "Big Snake",
    36: "Donkey",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("playwhe_scraper")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DrawResult:
    draw_number: int          # NLCB's sequential draw id, e.g. 27334
    draw_date: str             # ISO format YYYY-MM-DD
    period: str                 # MORNING / MIDDAY / AFTERNOON / EVENING
    number: int                 # 1-36
    mark: str


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            draw_number INTEGER PRIMARY KEY,
            draw_date   TEXT NOT NULL,
            period      TEXT NOT NULL,
            number      INTEGER NOT NULL,
            mark        TEXT NOT NULL,
            scraped_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def store_result(conn: sqlite3.Connection, result: DrawResult) -> bool:
    """Returns True if this was a NEW result (not already stored)."""
    try:
        conn.execute(
            """
            INSERT INTO results (draw_number, draw_date, period, number, mark, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.draw_number,
                result.draw_date,
                result.period,
                result.number,
                result.mark,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # draw_number already exists — not new, nothing to do
        return False


def get_latest_draw_number(conn: sqlite3.Connection) -> Optional[int]:
    row = conn.execute(
        "SELECT MAX(draw_number) FROM results"
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def export_json(conn: sqlite3.Connection, path: str = JSON_PATH, limit: int = JSON_MAX_DRAWS) -> int:
    """
    Writes the most recent `limit` draws to a JSON file the live site
    fetches directly, in the same shape the front-end expects:
        {"generated_at": "...", "history": [{"id":..., "date":..., "period":..., "n":...}, ...]}
    Oldest first, matching the order the page's HISTORY array uses.
    Returns the number of draws written.
    """
    rows = conn.execute(
        """
        SELECT draw_number, draw_date, period, number
        FROM results
        ORDER BY draw_number DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    rows.reverse()  # oldest first

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "history": [
            {"id": r[0], "date": r[1], "period": r[2], "n": r[3]}
            for r in rows
        ],
    }

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

    return len(payload["history"])


# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------

def fetch_page(url: str = SOURCE_URL) -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_results(html: str) -> list[DrawResult]:
    """
    Parses today's Play Whe results from nlcbplaywhelotto.com's results
    page. Confirmed against the real live page on 22-Aug-2026, where
    the text reads (each draw block, in order):

        Play Whe Results for today: 22-Aug-26
        ...
        Morning
        Draw #27334
        33 Spider
        ...

    Only draws that have already happened today appear on the page —
    later slots (Midday/Afternoon/Evening) simply aren't there yet
    until their draw time passes, so this naturally returns 1-4
    results depending on what time of day it runs.

    NOTE: this was built from the page's rendered text, not raw HTML
    (this environment has no live browser access to inspect real tag
    structure). It should work as-is, but if a run finds nothing,
    inspect the live page's HTML (right-click > Inspect near a period
    label like "Morning") and adjust the regex/soup logic below.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    results: list[DrawResult] = []

    # "Play Whe Results for today: 22-Aug-26"
    date_match = re.search(
        r"Play Whe Results for today:\s*(\d{1,2}-[A-Za-z]{3}-\d{2})",
        text,
    )
    if not date_match:
        return results
    try:
        today = datetime.strptime(date_match.group(1), "%d-%b-%y")
    except ValueError:
        return results
    draw_date = today.strftime("%Y-%m-%d")

    # Each draw block: period name, then "Draw #NNNNN", then "NN MarkName"
    block_pattern = re.compile(
        r"(?P<period>Morning|Midday|Afternoon|Evening)\s*\n+"
        r"Draw #(?P<draw>\d+)\s*\n+"
        r"(?P<number>\d{1,2})\s+(?P<mark>[A-Za-z ]+?)\s*\n",
        re.IGNORECASE,
    )

    for match in block_pattern.finditer(text):
        number = int(match.group("number"))
        if number not in MARKS:
            continue
        results.append(
            DrawResult(
                draw_number=int(match.group("draw")),
                draw_date=draw_date,
                period=match.group("period").upper(),
                number=number,
                mark=MARKS[number],
            )
        )

    return results


# ---------------------------------------------------------------------------
# Main polling routine
# ---------------------------------------------------------------------------

def run_once() -> None:
    conn = init_db()
    last_known = get_latest_draw_number(conn)
    log.info("Last known draw number in DB: %s", last_known)

    try:
        html = fetch_page()
    except requests.RequestException as e:
        log.error("Failed to fetch results page: %s", e)
        return

    parsed = parse_results(html)
    if not parsed:
        log.warning(
            "No results parsed — the page structure may have changed. "
            "Inspect the live HTML and update parse_results()."
        )
        return

    new_count = 0
    for result in sorted(parsed, key=lambda r: r.draw_number):
        if store_result(conn, result):
            new_count += 1
            log.info(
                "NEW draw stored: #%s %s %s -> %s (%s)",
                result.draw_number,
                result.draw_date,
                result.period,
                result.number,
                result.mark,
            )

    if new_count == 0:
        log.info("No new draws found this run.")
    else:
        log.info("%d new draw(s) added.", new_count)

    written = export_json(conn)
    log.info("Exported %d draws to %s.", written, JSON_PATH)

    conn.close()


if __name__ == "__main__":
    run_once()

# ---------------------------------------------------------------------------
# Scheduling
#
# Trinidad is AST (UTC-4) year-round — no daylight saving, so these
# UTC times are fixed and don't need seasonal adjustment.
#
#   Draw (AST)      UTC       Cron (run a few min after, with retries)
#   10:30 AM     -> 14:30 UTC
#   1:00 PM      -> 17:00 UTC
#   4:00 PM      -> 20:00 UTC
#   6:30 PM      -> 22:30 UTC
#
# See .github/workflows/update-results.yml for the actual GitHub
# Actions schedule — it runs this script a few times after each
# draw (results can post a little late), and a run that finds
# nothing new just logs and exits cheaply.
# ---------------------------------------------------------------------------
