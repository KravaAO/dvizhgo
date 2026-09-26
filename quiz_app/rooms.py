"""Room lifecycle and room-scoped access helpers.

The current `students` table is a legacy persistence name. New application
code refers to its records as participants while a future migration can rename
the physical table without changing the room API.
"""

import json
import random
import secrets
from datetime import datetime
from pathlib import Path

from quiz_app.config import settings


ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_WORDS_PATH = Path(__file__).resolve().parent.parent / "room_name_words.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def generate_room_code() -> str:
    return "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))


def generate_room_title(locale: str | None = None) -> str:
    with open(ROOM_WORDS_PATH, "r", encoding="utf-8") as file:
        words = json.load(file)
    locale_words = words.get(locale or settings.default_locale) or words["uk"]
    adjective = random.choice(locale_words["adjectives"])
    noun = random.choice(locale_words["nouns"])
    return f"{adjective} {noun}"


def create_room(conn) -> tuple[dict, str]:
    clean_title = generate_room_title()
    for _ in range(10):
        code = generate_room_code()
        existing = conn.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone()
        if not existing:
            break
    else:
        raise RuntimeError("Could not generate a unique room code")

    room_id = conn.insert_and_get_id(
        """
        INSERT INTO rooms (code, title, status, created_at, settings_json)
        VALUES (?, ?, 'lobby', ?, ?)
        """,
        (code, clean_title, now_iso(), "{}"),
    )
    access_token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO room_hosts (room_id, access_token, created_at)
        VALUES (?, ?, ?)
        """,
        (room_id, access_token, now_iso()),
    )
    conn.commit()
    return {"id": room_id, "code": code, "title": clean_title, "status": "lobby"}, access_token


def get_room_by_code(conn, code: str):
    return conn.execute(
        "SELECT * FROM rooms WHERE code = ?",
        (code.strip().upper(),),
    ).fetchone()


def get_host_room(conn, room_id: int | None, access_token: str | None):
    if not room_id or not access_token:
        return None
    return conn.execute(
        """
        SELECT r.* FROM rooms r
        JOIN room_hosts h ON h.room_id = r.id
        WHERE r.id = ? AND h.access_token = ?
        """,
        (room_id, access_token),
    ).fetchone()


def add_participant(conn, room_id: int, name: str, question_ids: list[int]) -> int:
    order = list(question_ids)
    random.shuffle(order)
    participant_id = conn.insert_and_get_id(
        """
        INSERT INTO students (room_id, name, started_at, total_questions, question_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        (room_id, name.strip()[:80], now_iso(), len(order), json.dumps(order)),
    )
    conn.commit()
    return participant_id


def get_participant(conn, participant_id: int | None, room_id: int | None):
    if not participant_id or not room_id:
        return None
    return conn.execute(
        "SELECT * FROM students WHERE id = ? AND room_id = ?",
        (participant_id, room_id),
    ).fetchone()
