"""Persistence operations for a room's current activity and quiz attempts."""

import json
import random
from datetime import datetime


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def get_runtime(conn, room_id):
    runtime = conn.execute("SELECT * FROM room_runtime WHERE room_id = ?", (room_id,)).fetchone()
    if runtime:
        return runtime
    conn.execute(
        "INSERT INTO room_runtime (room_id, state, version, updated_at) VALUES (?, 'lobby', 0, ?) ON CONFLICT(room_id) DO NOTHING",
        (room_id, now_iso()),
    )
    return conn.execute("SELECT * FROM room_runtime WHERE room_id = ?", (room_id,)).fetchone()


def set_runtime(conn, room_id, activity_id, state):
    get_runtime(conn, room_id)
    conn.execute(
        """
        UPDATE room_runtime
        SET current_activity_id = ?, state = ?, version = version + 1, updated_at = ?
        WHERE room_id = ?
        """,
        (activity_id, state, now_iso(), room_id),
    )


def get_activity(conn, activity_id):
    if not activity_id:
        return None
    return conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()


def room_socket_state(conn, room_id):
    room = conn.execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()
    runtime = get_runtime(conn, room_id)
    activity = get_activity(conn, runtime["current_activity_id"])
    return {
        "room_id": room_id,
        "room_status": room["status"] if room else "finished",
        "runtime_state": runtime["state"],
        "runtime_version": runtime["version"],
        "activity_type": activity["type"] if activity else None,
        "activity_status": activity["status"] if activity else None,
    }


def get_active_attempt(conn, participant_id, room_id):
    return conn.execute(
        """
        SELECT qa.id, qa.activity_id, qa.participant_id, qa.question_order_json,
               qa.current_question, qa.score, qa.started_at, qa.finished_at,
               qa.abandoned_at, a.room_id, a.type AS activity_type,
               a.status AS activity_status, a.config_json,
               a.started_at AS activity_started_at, a.paused_at AS activity_paused_at,
               a.finished_at AS activity_finished_at
        FROM quiz_attempts qa JOIN activities a ON a.id = qa.activity_id
        WHERE qa.participant_id = ? AND a.room_id = ? AND qa.abandoned_at IS NULL
        ORDER BY qa.id DESC LIMIT 1
        """,
        (participant_id, room_id),
    ).fetchone()


def resumed_quiz_activity(conn, activity):
    """Find the quiz that a live extra activity will return to."""
    if not activity:
        return None
    if activity["type"] == "quiz":
        return activity
    try:
        resume_activity_id = json.loads(activity["config_json"] or "{}").get("resume_activity_id")
    except (TypeError, json.JSONDecodeError):
        return None
    quiz_activity = get_activity(conn, resume_activity_id)
    return quiz_activity if quiz_activity and quiz_activity["type"] == "quiz" else None


def create_late_quiz_attempt(conn, participant_id, quiz_activity, activity_questions):
    """Give a late joiner an independent attempt without changing the class activity."""
    existing = conn.execute(
        "SELECT id FROM quiz_attempts WHERE activity_id = ? AND participant_id = ? AND abandoned_at IS NULL",
        (quiz_activity["id"], participant_id),
    ).fetchone()
    if existing:
        return existing["id"]
    question_ids = [question["id"] for question in activity_questions(quiz_activity)]
    if not question_ids:
        return None
    config = json.loads(quiz_activity["config_json"] or "{}")
    if config.get("shuffle_questions"):
        random.shuffle(question_ids)
    return conn.insert_and_get_id(
        """INSERT INTO quiz_attempts (activity_id, participant_id, question_order_json, started_at)
           VALUES (?, ?, ?, ?)""",
        (quiz_activity["id"], participant_id, json.dumps(question_ids), now_iso()),
    )
