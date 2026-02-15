import random
try:
    from .db import get_conn, put_conn
except ImportError:
    from db import get_conn, put_conn

# Value sets by era for each round
ROUND_1_VALUE_SETS = [
    [200, 400, 600, 800, 1000],   # modern
    [100, 200, 300, 400, 500],    # classic
]
ROUND_2_VALUE_SETS = [
    [400, 800, 1200, 1600, 2000], # modern
    [200, 400, 600, 800, 1000],   # classic
]

# Display values (always modern)
DISPLAY_VALUES = {
    1: [200, 400, 600, 800, 1000],
    2: [400, 800, 1200, 1600, 2000],
}


def generate_board(round_num: int) -> dict:
    value_sets = ROUND_1_VALUE_SETS if round_num == 1 else ROUND_2_VALUE_SETS
    display = DISPLAY_VALUES[round_num]

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Find category groups that have exactly 5 clues with one of the valid value sets
            # We build a query that finds complete groups
            conditions = []
            for vs in value_sets:
                conditions.append(
                    f"array_agg(c.clue_value ORDER BY c.clue_value) = ARRAY{vs}"
                )
            where = " OR ".join(conditions)

            cur.execute(f"""
                SELECT c.game_id, c.category_id, cat.name
                FROM clues c
                JOIN categories cat ON cat.id = c.category_id
                WHERE c.round = %s
                GROUP BY c.game_id, c.category_id, cat.name
                HAVING count(*) = 5 AND ({where})
                ORDER BY random()
                LIMIT 6
            """, (round_num,))

            groups = cur.fetchall()
            if len(groups) < 6:
                raise ValueError(f"Not enough category groups for round {round_num}")

            categories = []
            for game_id, category_id, cat_name in groups:
                cur.execute("""
                    SELECT id, clue_value, daily_double_value
                    FROM clues
                    WHERE game_id = %s AND category_id = %s AND round = %s
                    ORDER BY clue_value ASC
                """, (game_id, category_id, round_num))

                clues = cur.fetchall()
                mapped_clues = []
                for i, (clue_id, original_value, dd_value) in enumerate(clues):
                    mapped_clues.append({
                        "id": clue_id,
                        "value": display[i],
                        "is_daily_double": False,
                    })

                categories.append({
                    "name": cat_name,
                    "clues": mapped_clues,
                })

            # Assign daily doubles
            dd_count = 1 if round_num == 1 else 2
            all_clue_refs = [
                (cat_idx, clue_idx)
                for cat_idx, cat in enumerate(categories)
                for clue_idx in range(len(cat["clues"]))
            ]
            dd_picks = random.sample(all_clue_refs, dd_count)
            for cat_idx, clue_idx in dd_picks:
                categories[cat_idx]["clues"][clue_idx]["is_daily_double"] = True

        return {"round": round_num, "categories": categories}
    finally:
        put_conn(conn)


def get_clue(clue_id: int) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, cat.name, c.clue_value, c.answer, c.question, g.air_date
                FROM clues c
                JOIN categories cat ON cat.id = c.category_id
                JOIN games g ON g.id = c.game_id
                WHERE c.id = %s
            """, (clue_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "category": row[1],
                "value": row[2],
                "clue_text": row[3],
                "expected_response": row[4],
                "air_date": row[5],
            }
    finally:
        put_conn(conn)
