import calendar
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS identify_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    foods_json TEXT NOT NULL,
    total_calories_kcal REAL,
    summary TEXT NOT NULL DEFAULT '',
    tips TEXT NOT NULL DEFAULT '',
    raw_response TEXT NOT NULL DEFAULT '',
    debug_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    user_id INTEGER
);
CREATE TABLE IF NOT EXISTS user_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_session (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn


def init_db(db_path):
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(identify_record)")]
        if "user_id" not in columns:
            conn.execute("ALTER TABLE identify_record ADD COLUMN user_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_identify_user ON identify_record(user_id)")
        conn.commit()
    finally:
        conn.close()


def insert_record(db_path, record):
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO identify_record (
                image_path, foods_json, total_calories_kcal, summary, tips,
                raw_response, debug_url, created_at, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["image_path"],
                json.dumps(record["foods"], ensure_ascii=False),
                record["total_calories_kcal"],
                record["summary"],
                record["tips"],
                record["raw_response"],
                record["debug_url"],
                record["created_at"],
                record["user_id"],
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _public_row(row):
    foods = json.loads(row["foods_json"] or "[]")
    total = row["total_calories_kcal"]
    return {
        "id": row["id"],
        "image_url": row["image_path"],
        "foods": foods,
        "total_calories_kcal": total,
        "summary": row["summary"],
        "tips": row["tips"],
        "debug_url": row["debug_url"],
        "created_at": row["created_at"],
    }


def list_records(db_path, user_id, limit, offset):
    conn = connect(db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM identify_record WHERE user_id = ?",
            (user_id,),
        ).fetchone()["c"]
        rows = conn.execute(
            """
            SELECT * FROM identify_record
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()
        return {"items": [_public_row(row) for row in rows], "total": total}
    finally:
        conn.close()


def list_records_on_day(db_path, user_id, day):
    start, end = _day_bounds(day)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM identify_record
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, start, end),
        ).fetchall()
        items = [_public_row(row) for row in rows]
        total_kcal = 0.0
        for item in items:
            total_kcal += float(item["total_calories_kcal"] or 0)
        return {
            "items": items,
            "total": len(items),
            "total_calories_kcal": round(total_kcal, 2),
        }
    finally:
        conn.close()


def calendar_month(db_path, user_id, month):
    year_text, month_text = month.split("-")
    year = int(year_text)
    mon = int(month_text)
    last_day = calendar.monthrange(year, mon)[1]
    start = "%04d-%02d-01 00:00:00" % (year, mon)
    if mon == 12:
        end = "%04d-01-01 00:00:00" % (year + 1,)
    else:
        end = "%04d-%02d-01 00:00:00" % (year, mon + 1)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day,
                   SUM(COALESCE(total_calories_kcal, 0)) AS kcal,
                   COUNT(*) AS c
            FROM identify_record
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            GROUP BY day
            """,
            (user_id, start, end),
        ).fetchall()
        by_day = {}
        for row in rows:
            by_day[row["day"]] = row
        days = []
        for day_number in range(1, last_day + 1):
            key = "%04d-%02d-%02d" % (year, mon, day_number)
            row = by_day.get(key)
            days.append({
                "date": key,
                "total_calories_kcal": round(float(row["kcal"]), 2) if row else 0,
                "count": int(row["c"]) if row else 0,
            })
        return {"month": "%04d-%02d" % (year, mon), "days": days}
    finally:
        conn.close()


def _day_bounds(day):
    year, mon, day_number = [int(part) for part in day.split("-")]
    start = "%04d-%02d-%02d 00:00:00" % (year, mon, day_number)
    if day_number == calendar.monthrange(year, mon)[1]:
        if mon == 12:
            end = "%04d-01-01 00:00:00" % (year + 1,)
        else:
            end = "%04d-%02d-01 00:00:00" % (year, mon + 1)
    else:
        end = "%04d-%02d-%02d 00:00:00" % (year, mon, day_number + 1)
    return start, end


def get_record(db_path, record_id, user_id):
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM identify_record WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return _public_row(row)
    finally:
        conn.close()


def replace_record(db_path, record_id, user_id, record):
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT image_path, created_at FROM identify_record WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE identify_record
            SET image_path = ?, foods_json = ?, total_calories_kcal = ?, summary = ?,
                tips = ?, raw_response = ?, debug_url = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                record["image_path"],
                json.dumps(record["foods"], ensure_ascii=False),
                record["total_calories_kcal"],
                record["summary"],
                record["tips"],
                record["raw_response"],
                record["debug_url"],
                record_id,
                user_id,
            ),
        )
        conn.commit()
        return {"old_image_path": row["image_path"], "created_at": row["created_at"]}
    finally:
        conn.close()


def delete_record(db_path, record_id, user_id):
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT image_path FROM identify_record WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "DELETE FROM identify_record WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        )
        conn.commit()
        return row["image_path"]
    finally:
        conn.close()


def create_user(db_path, username, password_hash, created_at):
    conn = connect(db_path)
    try:
        exists = conn.execute(
            "SELECT id FROM user_account WHERE username = ?",
            (username,),
        ).fetchone()
        if exists is not None:
            return None
        cursor = conn.execute(
            """
            INSERT INTO user_account (username, password_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (username, password_hash, created_at),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def find_user_by_username(db_path, username):
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM user_account WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
        }
    finally:
        conn.close()


def create_session(db_path, token, user_id, created_at):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO auth_session (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def find_user_by_token(db_path, token):
    if not token:
        return None
    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT u.id AS id, u.username AS username
            FROM auth_session s
            JOIN user_account u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "username": row["username"]}
    finally:
        conn.close()


def delete_session(db_path, token):
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM auth_session WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()
