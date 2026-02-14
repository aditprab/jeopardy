"""Load Jeopardy TSV data into Postgres."""

import csv
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = dict(
    host="localhost",
    port=5433,
    dbname="jeopardy",
    user="jeopardy",
    password="jeopardy",
)

DATA_DIR = Path(__file__).parent / "dataset" / "jeopardy_dataset_seasons_1-41"

# Map season files to season numbers for air_date -> season lookup
SEASON_DATE_RANGES = {}  # populated from scoring data


def parse_round(value):
    """Normalize round values to integers."""
    mapping = {"single": 1, "double": 2, "triple": 3, "final": 4}
    if value in mapping:
        return mapping[value]
    return int(value)


def build_season_lookup(conn):
    """Build air_date -> season mapping from scoring data."""
    lookup = {}
    scoring_file = DATA_DIR / "scoring_season1-41.tsv"
    with open(scoring_file, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            lookup[row["air_date"]] = int(row["season"])
    return lookup


def load_clues(conn, filepath, source, season_lookup):
    """Load clues from a TSV file, creating games and categories as needed."""
    cur = conn.cursor()

    # Caches to avoid repeated lookups
    category_cache = {}
    game_cache = {}

    # Pre-load existing categories and games
    cur.execute("SELECT name, id FROM categories")
    for name, cid in cur.fetchall():
        category_cache[name] = cid

    cur.execute("SELECT air_date, source, id FROM games")
    for air_date, src, gid in cur.fetchall():
        game_cache[(str(air_date), src)] = gid

    rows = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    # Collect new categories
    new_categories = set()
    for row in rows:
        cat = row["category"]
        if cat not in category_cache:
            new_categories.add(cat)

    if new_categories:
        execute_values(
            cur,
            "INSERT INTO categories (name) VALUES %s ON CONFLICT DO NOTHING",
            [(c,) for c in new_categories],
        )
        cur.execute("SELECT name, id FROM categories WHERE name = ANY(%s)",
                     (list(new_categories),))
        for name, cid in cur.fetchall():
            category_cache[name] = cid

    # Collect new games
    new_games = set()
    for row in rows:
        air_date = row["air_date"]
        game_key = (air_date, source)
        if game_key not in game_cache:
            new_games.add(game_key)

    if new_games:
        game_rows = []
        for air_date, src in new_games:
            season = season_lookup.get(air_date)
            game_rows.append((air_date, season, src))
        execute_values(
            cur,
            "INSERT INTO games (air_date, season, source) VALUES %s ON CONFLICT DO NOTHING",
            game_rows,
        )
        cur.execute("SELECT air_date, source, id FROM games")
        for air_date, src, gid in cur.fetchall():
            game_cache[(str(air_date), src)] = gid

    # Build clue rows
    clue_batch = []
    for row in rows:
        game_id = game_cache[(row["air_date"], source)]
        category_id = category_cache[row["category"]]
        rnd = parse_round(row["round"])
        clue_value = int(row["clue_value"])
        dd_val = int(row["daily_double_value"])
        daily_double_value = dd_val if dd_val != 0 else None
        answer = row["answer"]
        question = row["question"]
        comments = row["comments"] or None

        # Merge per-clue notes into game notes if present
        clue_batch.append((
            game_id, rnd, category_id, clue_value,
            daily_double_value, answer, question, comments,
        ))

    if clue_batch:
        execute_values(
            cur,
            """INSERT INTO clues
               (game_id, round, category_id, clue_value,
                daily_double_value, answer, question, comments)
               VALUES %s""",
            clue_batch,
            page_size=5000,
        )

    conn.commit()
    cur.close()
    return len(clue_batch)


def load_scoring(conn, season_lookup):
    """Load scoring/contestant data."""
    cur = conn.cursor()

    # Load game_id lookup
    cur.execute("SELECT air_date, source, id FROM games")
    game_cache = {}
    for air_date, src, gid in cur.fetchall():
        game_cache[(str(air_date), src)] = gid

    scoring_file = DATA_DIR / "scoring_season1-41.tsv"
    contestant_rows = []

    with open(scoring_file, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            game_key = (row["air_date"], "regular")
            game_id = game_cache.get(game_key)
            if game_id is None:
                continue

            for pos, label in [(1, "left"), (2, "middle"), (3, "right")]:
                name = row[f"name_{label}"]
                if not name:
                    continue
                contestant_rows.append((
                    game_id,
                    name,
                    pos,
                    int(row[f"single_{label}"]),
                    int(row[f"double_{label}"]),
                    int(row[f"final_{label}"]),
                    int(row[f"coryat_{label}"]),
                    int(row[f"correct_{label}"]),
                    int(row[f"wrong_{label}"]),
                ))

    if contestant_rows:
        execute_values(
            cur,
            """INSERT INTO game_contestants
               (game_id, contestant_name, podium_position,
                score_single, score_double, score_final,
                coryat_score, correct_count, wrong_count)
               VALUES %s""",
            contestant_rows,
            page_size=5000,
        )

    conn.commit()
    cur.close()
    return len(contestant_rows)


def main():
    conn = psycopg2.connect(**DB_CONFIG)

    print("Building season lookup from scoring data...")
    season_lookup = build_season_lookup(conn)

    print("Loading regular season clues...")
    n = load_clues(conn, DATA_DIR / "combined_season1-41.tsv", "regular", season_lookup)
    print(f"  {n:,} clues loaded.")

    print("Loading extra match clues...")
    n = load_clues(conn, DATA_DIR / "extra_matches.tsv", "extra", season_lookup)
    print(f"  {n:,} clues loaded.")

    print("Loading kids/teen match clues...")
    n = load_clues(conn, DATA_DIR / "kids_teen_matches.tsv", "kids_teen", season_lookup)
    print(f"  {n:,} clues loaded.")

    print("Loading scoring/contestant data...")
    n = load_scoring(conn, season_lookup)
    print(f"  {n:,} contestant records loaded.")

    # Print summary
    cur = conn.cursor()
    for table in ["categories", "games", "clues", "game_contestants"]:
        cur.execute(f"SELECT count(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]:,} rows")
    cur.close()

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
