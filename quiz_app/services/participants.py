"""Participant identity, appearance, presence, and lobby boost rules."""

import hashlib
import json
import random
import secrets
from datetime import datetime

from .room_runtime import now_iso


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def random_avatar_appearance(avatar_options, headwear_options):
    return {"avatar": random.choice(avatar_options), "headwear": random.choice(headwear_options)}


def participant_appearance(metadata_json, avatar_options, headwear_options):
    """Return only known cosmetic asset IDs, never a client-provided path."""
    try:
        metadata = json.loads(metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    appearance = metadata.get("appearance") if isinstance(metadata, dict) else {}
    appearance = appearance if isinstance(appearance, dict) else {}
    headwear = appearance.get("headwear")
    return {
        "avatar": appearance.get("avatar") if appearance.get("avatar") in avatar_options else avatar_options[0],
        "headwear": None if "headwear" in appearance and headwear is None else (
            headwear if headwear in headwear_options else headwear_options[0]
        ),
    }


def current_participant(conn, participant_id, room_id, reconnect_token):
    if not participant_id or not room_id or not reconnect_token:
        return None
    return conn.execute(
        """SELECT * FROM room_participants
           WHERE id = ? AND room_id = ? AND reconnect_token_hash = ? AND left_at IS NULL""",
        (participant_id, room_id, token_hash(reconnect_token)),
    ).fetchone()


def create_room_participant(conn, room_id, display_name, avatar_options, headwear_options):
    reconnect_token = secrets.token_urlsafe(32)
    metadata_json = json.dumps({"appearance": random_avatar_appearance(avatar_options, headwear_options)})
    participant_id = conn.insert_and_get_id(
        """INSERT INTO room_participants
           (room_id, display_name, reconnect_token_hash, joined_at, last_seen_at, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room_id, display_name.strip()[:80], token_hash(reconnect_token), now_iso(), now_iso(), metadata_json),
    )
    return participant_id, reconnect_token


def touch_participant(conn, participant_id):
    conn.execute(
        "UPDATE room_participants SET last_seen_at = ? WHERE id = ? AND left_at IS NULL",
        (now_iso(), participant_id),
    )


def lobby_boost_state(conn, room_id):
    now = datetime.now()
    rows = conn.execute(
        "SELECT participant_id, boosted_until, cooldown_until FROM room_lobby_boosts WHERE room_id = ?",
        (room_id,),
    ).fetchall()
    state = {}
    for row in rows:
        boosted_until = datetime.fromisoformat(row["boosted_until"])
        cooldown_until = datetime.fromisoformat(row["cooldown_until"])
        state[str(row["participant_id"])] = {
            "active": boosted_until > now,
            "boosted_until": row["boosted_until"],
            "cooldown_seconds": max(0, int((cooldown_until - now).total_seconds() + .999)),
        }
    return state
