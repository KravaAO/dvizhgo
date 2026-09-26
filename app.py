import json
import random
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import (
    jsonify, redirect, render_template,
    request, session, url_for
)
from flask_socketio import SocketIO, join_room as join_socket_room
from quiz_app import create_app
from quiz_app.config import settings
from quiz_app.database import connect_database, initialize_database
from quiz_app.rooms import (
    create_room,
    get_host_room as find_host_room,
    get_room_by_code,
)

BASE_DIR = settings.base_dir
DB_PATH = settings.sqlite_path
DATABASE_URL = settings.database_url
QUESTIONS_PATH = BASE_DIR / "questions.json"

app = create_app()
socketio = SocketIO(app, async_mode="threading", message_queue=settings.socketio_message_queue)

ADMIN_PASSWORD = settings.admin_password
SHUFFLE_ANSWERS = settings.shuffle_answers
SHUFFLE_QUESTIONS = settings.shuffle_questions
AVATAR_OPTIONS = ("avatar-1", "avatar-2", "avatar-3", "avatar-4")
HEADWEAR_OPTIONS = (
    "headwear-1", "headwear-2", "headwear-3", "headwear-4", "headwear-5",
    "headwear-6", "headwear-7", "headwear-8", "headwear-9",
)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def get_db():
    return connect_database(DATABASE_URL, DB_PATH)


def init_db():
    initialize_database(DATABASE_URL, DB_PATH)


def load_questions():
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_room_questions(conn, room_id):
    room = conn.execute("SELECT active_quiz_id FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room and room["active_quiz_id"]:
        quiz = conn.execute(
            "SELECT questions_json FROM quizzes WHERE id = ? AND room_id = ?",
            (room["active_quiz_id"], room_id),
        ).fetchone()
        if quiz:
            return json.loads(quiz["questions_json"])
    return load_questions()


def get_room_quiz_title(conn, room):
    """Return the selected quiz name without coupling a room to a running attempt."""
    if room["active_quiz_id"]:
        quiz = conn.execute(
            "SELECT title FROM quizzes WHERE id = ? AND room_id = ?",
            (room["active_quiz_id"], room["id"]),
        ).fetchone()
        if quiz:
            return quiz["title"]
    return "Django та Git — готовий квіз"


def get_question_map(room_id=None):
    if not room_id:
        return {q["id"]: q for q in load_questions()}
    conn = get_db()
    questions = load_room_questions(conn, room_id)
    conn.close()
    return {q["id"]: q for q in questions}


def validate_quiz_payload(payload):
    data = payload if isinstance(payload, dict) else {"questions": payload}
    title = str(data.get("title") or "Мій квіз").strip()[:120]
    questions = data.get("questions")
    if not title or not isinstance(questions, list) or not 1 <= len(questions) <= 67:
        raise ValueError("Потрібно від 1 до 67 питань і назва квіза.")

    valid_types = {"single", "multiple", "true_false"}
    normalized = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Питання {index} має бути об'єктом.")
        kind = item.get("type", "single")
        question = str(item.get("question") or "").strip()
        answers = item.get("answers")
        correct = item.get("correct")
        if kind not in valid_types or not question or not isinstance(answers, list) or not 2 <= len(answers) <= 8:
            raise ValueError(f"Перевірте тип, текст і варіанти питання {index}.")
        answers = [str(answer).strip() for answer in answers]
        if any(not answer for answer in answers) or not isinstance(correct, list) or not correct:
            raise ValueError(f"Питання {index} має містити непорожні варіанти та правильну відповідь.")
        try:
            correct = sorted({int(answer) for answer in correct})
        except (ValueError, TypeError):
            raise ValueError(f"Некоректні правильні відповіді в питанні {index}.")
        if any(answer < 0 or answer >= len(answers) for answer in correct):
            raise ValueError(f"Правильна відповідь поза межами варіантів у питанні {index}.")
        if kind in {"single", "true_false"} and len(correct) != 1:
            raise ValueError(f"У питанні {index} типу {kind} має бути одна правильна відповідь.")
        if kind == "true_false" and len(answers) != 2:
            raise ValueError(f"True/false питання {index} має містити рівно два варіанти.")
        normalized.append({
            "id": index,
            "type": kind,
            "question": question,
            "text": str(item.get("text") or "").strip()[:1800],
            "code": str(item.get("code") or "").strip()[:4000],
            "answers": answers,
            "correct": correct,
            "explanation": str(item.get("explanation") or "").strip()[:500],
            "difficulty": str(item.get("difficulty") or "").strip()[:20],
        })
    return title, normalized


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def random_avatar_appearance():
    return {
        "avatar": random.choice(AVATAR_OPTIONS),
        "headwear": random.choice(HEADWEAR_OPTIONS),
    }


def participant_appearance(metadata_json):
    """Return only known cosmetic asset IDs, never a client-provided path."""
    try:
        metadata = json.loads(metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    appearance = metadata.get("appearance") if isinstance(metadata, dict) else {}
    appearance = appearance if isinstance(appearance, dict) else {}
    headwear = appearance.get("headwear")
    return {
        "avatar": appearance.get("avatar") if appearance.get("avatar") in AVATAR_OPTIONS else AVATAR_OPTIONS[0],
        # An explicit null is a valid choice: the participant removed headwear.
        "headwear": None if "headwear" in appearance and headwear is None else (
            headwear if headwear in HEADWEAR_OPTIONS else HEADWEAR_OPTIONS[0]
        ),
    }


def current_participant(conn=None):
    participant_id = session.get("participant_id")
    room_id = session.get("room_id")
    reconnect_token = session.get("participant_reconnect_token")
    if not participant_id or not room_id or not reconnect_token:
        return None
    own_connection = conn is None
    if own_connection:
        conn = get_db()
    row = conn.execute(
        """
        SELECT * FROM room_participants
        WHERE id = ? AND room_id = ? AND reconnect_token_hash = ? AND left_at IS NULL
        """,
        (participant_id, room_id, token_hash(reconnect_token)),
    ).fetchone()
    if own_connection:
        conn.close()
    return row


def create_room_participant(conn, room_id, display_name):
    reconnect_token = secrets.token_urlsafe(32)
    metadata_json = json.dumps({"appearance": random_avatar_appearance()})
    participant_id = conn.insert_and_get_id(
        """
        INSERT INTO room_participants
        (room_id, display_name, reconnect_token_hash, joined_at, last_seen_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (room_id, display_name.strip()[:80], token_hash(reconnect_token), now_iso(), now_iso(), metadata_json),
    )
    return participant_id, reconnect_token


def touch_participant(conn, participant_id):
    conn.execute(
        "UPDATE room_participants SET last_seen_at = ? WHERE id = ? AND left_at IS NULL",
        (now_iso(), participant_id),
    )


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
    runtime = get_runtime(conn, room_id)
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


def socket_room_name(room_id):
    return f"room:{room_id}"


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


def emit_room_event(room_id, event, payload=None):
    socketio.emit(event, payload or {}, to=socket_room_name(room_id))


def emit_room_state(room_id):
    conn = get_db()
    payload = room_socket_state(conn, room_id)
    conn.commit()
    conn.close()
    emit_room_event(room_id, "room:state", payload)


def get_active_attempt(conn, participant_id, room_id):
    return conn.execute(
        """
        SELECT
            qa.id,
            qa.activity_id,
            qa.participant_id,
            qa.question_order_json,
            qa.current_question,
            qa.score,
            qa.started_at,
            qa.finished_at,
            qa.abandoned_at,
            a.room_id,
            a.type AS activity_type,
            a.status AS activity_status,
            a.config_json,
            a.started_at AS activity_started_at,
            a.paused_at AS activity_paused_at,
            a.finished_at AS activity_finished_at
        FROM quiz_attempts qa
        JOIN activities a ON a.id = qa.activity_id
        WHERE qa.participant_id = ? AND a.room_id = ?
          AND qa.abandoned_at IS NULL
        ORDER BY qa.id DESC
        LIMIT 1
        """,
        (participant_id, room_id),
    ).fetchone()


def activity_questions(activity):
    return json.loads(activity["config_json"]).get("questions", [])


def activity_question_map(activity):
    return {question["id"]: question for question in activity_questions(activity)}


def get_current_host_room():
    conn = get_db()
    room = find_host_room(conn, session.get("host_room_id"), session.get("host_access_token"))
    conn.close()
    return room


@socketio.on("connect")
def connect_room_socket(_auth=None):
    """Authorize the browser from its existing room session and join one room channel."""
    conn = get_db()
    participant = current_participant(conn)
    room_id = None
    if participant:
        room_id = participant["room_id"]
        touch_participant(conn, participant["id"])
    else:
        host_room = find_host_room(conn, session.get("host_room_id"), session.get("host_access_token"))
        if host_room:
            room_id = host_room["id"]
    if not room_id:
        conn.close()
        return False

    join_socket_room(socket_room_name(room_id))
    payload = room_socket_state(conn, room_id)
    conn.commit()
    conn.close()
    socketio.emit("room:state", payload, to=request.sid)
    if participant:
        emit_room_event(room_id, "room:presence", {"participant_id": participant["id"]})


@socketio.on("presence:heartbeat")
def socket_presence_heartbeat():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return {"ok": False}
    touch_participant(conn, participant["id"])
    conn.commit()
    conn.close()
    return {"ok": True}


def get_room(room_id):
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    conn.close()
    return room


def public_question(question):
    answers = [
        {"original_index": index, "text": text}
        for index, text in enumerate(question["answers"])
    ]
    if SHUFFLE_ANSWERS:
        random.shuffle(answers)

    return {
        "id": question["id"],
        "type": question["type"],
        "question": question["question"],
        "text": question.get("text"),
        "answers": answers,
        "code": question.get("code"),
        "difficulty": question.get("difficulty"),
    }


def compute_rank(percent):
    if percent == 100:
        return "Guido van Rossum?"
    if percent >= 95:
        return "Senior detected"
    if percent >= 80:
        return "Strong Developer"
    if percent >= 60:
        return "Python Enjoyer"
    if percent >= 40:
        return "Junior survivor"
    return "print('help')"


@app.get("/health")
def health():
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        return jsonify({"ok": False}), 503
    return jsonify({"ok": True})


def avatar_lab():
    """Temporary visual calibration page for the layered avatar source images."""
    return render_template("avatar_lab.html")


if settings.avatar_lab_path:
    app.add_url_rule(f"/{settings.avatar_lab_path}", endpoint="avatar_lab", view_func=avatar_lab, methods=["GET"])


def get_open_duel(conn, room_id):
    return conn.execute(
        """
        SELECT * FROM duel_rounds
        WHERE room_id = ? AND status != 'closed'
        ORDER BY id DESC
        LIMIT 1
        """,
        (room_id,),
    ).fetchone()


def clear_room_runtime(conn, room_id):
    """Remove activities/attempts but keep room participants and quiz content."""
    duel_ids = "SELECT id FROM duel_rounds WHERE room_id = ?"
    activity_ids = "SELECT id FROM activities WHERE room_id = ?"
    attempt_ids = f"SELECT id FROM quiz_attempts WHERE activity_id IN ({activity_ids})"
    conn.execute(
        "UPDATE room_runtime SET current_activity_id = NULL, state = 'lobby', version = version + 1, updated_at = ? WHERE room_id = ?",
        (now_iso(), room_id),
    )
    conn.execute(f"DELETE FROM duel_votes WHERE round_id IN ({duel_ids})", (room_id,))
    conn.execute(f"DELETE FROM duel_participants WHERE round_id IN ({duel_ids})", (room_id,))
    conn.execute("DELETE FROM duel_rounds WHERE room_id = ?", (room_id,))
    conn.execute(f"DELETE FROM quiz_attempt_answers WHERE attempt_id IN ({attempt_ids})", (room_id,))
    conn.execute(f"DELETE FROM quiz_attempts WHERE activity_id IN ({activity_ids})", (room_id,))
    conn.execute("DELETE FROM activities WHERE room_id = ?", (room_id,))
    # Delete legacy runtime records during the transition. The quiz library and
    # room participants remain intact.
    round_ids = "SELECT id FROM roulette_rounds WHERE room_id = ?"
    participant_ids = "SELECT id FROM students WHERE room_id = ?"
    conn.execute(f"DELETE FROM roulette_votes WHERE round_id IN ({round_ids})", (room_id,))
    conn.execute(f"DELETE FROM roulette_participants WHERE round_id IN ({round_ids})", (room_id,))
    conn.execute("DELETE FROM roulette_rounds WHERE room_id = ?", (room_id,))
    conn.execute(f"DELETE FROM answers WHERE student_id IN ({participant_ids})", (room_id,))
    conn.execute("DELETE FROM students WHERE room_id = ?", (room_id,))


def serialize_roulette(conn, round_row, viewer_id=None):
    if not round_row:
        return None

    participant_rows = conn.execute(
        """
        SELECT p.participant_id AS student_id, rp.display_name AS name, p.answer_text, p.answered_at,
               COUNT(v.voter_id) AS votes
        FROM duel_participants p
        JOIN room_participants rp ON rp.id = p.participant_id
        LEFT JOIN duel_votes v
            ON v.round_id = p.round_id AND v.choice_participant_id = p.participant_id
        WHERE p.round_id = ?
        GROUP BY p.participant_id, rp.display_name, p.answer_text, p.answered_at
        ORDER BY p.participant_id
        """,
        (round_row["id"],),
    ).fetchall()

    participants = [dict(row) for row in participant_rows]
    participant_ids = {participant["student_id"] for participant in participants}
    user_vote = None
    if viewer_id:
        vote = conn.execute(
            """
            SELECT choice_participant_id FROM duel_votes
            WHERE round_id = ? AND voter_id = ?
            """,
            (round_row["id"], viewer_id),
        ).fetchone()
        user_vote = vote["choice_participant_id"] if vote else None

    return {
        "id": round_row["id"],
        "question": round_row["question"],
        "candidate_pool": json.loads(round_row["candidate_pool_json"]),
        "status": round_row["status"],
        "created_at": round_row["created_at"],
        "participants": participants,
        "can_answer": bool(
            viewer_id
            and round_row["status"] == "answering"
            and any(
                participant["student_id"] == viewer_id and not participant["answer_text"]
                for participant in participants
            )
        ),
        "can_vote": bool(
            viewer_id
            and round_row["status"] == "voting"
            and viewer_id not in participant_ids
            and not user_vote
        ),
        "user_vote": user_vote,
    }


@app.get("/")
def index():
    participant = current_participant()
    if participant:
        return redirect(url_for("lobby"))
    room = get_current_host_room()
    if room:
        return redirect(url_for("host_lobby" if room["status"] == "lobby" else "admin"))
    return render_template("index.html")


@app.post("/rooms")
def create_new_room():
    conn = get_db()
    room, access_token = create_room(conn)
    get_runtime(conn, room["id"])
    conn.commit()
    conn.close()
    session.clear()
    session["host_room_id"] = room["id"]
    session["host_access_token"] = access_token
    session["room_id"] = room["id"]
    return redirect(url_for("host_lobby"))


@app.post("/join")
def join_room():
    name = (request.form.get("name") or "").strip()
    code = (request.form.get("code") or "").strip().upper()
    if not name or not code:
        return render_template("index.html", error="Введіть код кімнати та ім'я."), 400

    conn = get_db()
    room = get_room_by_code(conn, code)
    if not room or room["status"] == "finished":
        conn.close()
        return render_template("index.html", error="Кімнату не знайдено або її вже завершено."), 404
    participant_id, reconnect_token = create_room_participant(conn, room["id"], name)
    conn.commit()
    conn.close()

    session.clear()
    session["participant_id"] = participant_id
    session["room_id"] = room["id"]
    session["participant_reconnect_token"] = reconnect_token
    session["sound_enabled"] = True
    emit_room_event(room["id"], "room:presence", {"participant_id": participant_id})
    return redirect(url_for("lobby"))


@app.get("/lobby")
def lobby():
    host_room = get_current_host_room()
    if host_room:
        return redirect(url_for("host_lobby" if host_room["status"] == "lobby" else "admin"))
    participant = current_participant()
    if not participant:
        return redirect(url_for("index"))
    room = get_room(participant["room_id"])
    if not room:
        session.clear()
        return redirect(url_for("index"))
    conn = get_db()
    touch_participant(conn, participant["id"])
    runtime = get_runtime(conn, room["id"])
    active_attempt = get_active_attempt(conn, participant["id"], room["id"])
    conn.commit()
    conn.close()
    if runtime["state"] == "active" and active_attempt and not active_attempt["finished_at"]:
        return redirect(url_for("quiz"))
    return render_template("lobby.html", room=room, participant_name=participant["display_name"])


@app.get("/lobby/host")
def host_lobby():
    room = get_current_host_room()
    if not room:
        return redirect(url_for("index"))
    if room["status"] != "lobby":
        return redirect(url_for("admin"))
    return render_template("host_lobby.html", room=room)


@app.get("/api/lobby")
def lobby_state():
    room_id = session.get("room_id")
    if not room_id:
        return jsonify({"error": "No active room"}), 401
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    participant = current_participant(conn)
    if participant:
        touch_participant(conn, participant["id"])
    participants = conn.execute(
        """
        SELECT id, display_name AS name, last_seen_at, left_at, metadata_json
        FROM room_participants WHERE room_id = ? AND left_at IS NULL ORDER BY joined_at
        """,
        (room_id,),
    ).fetchall()
    if not room:
        conn.close()
        return jsonify({"error": "Room not found"}), 404
    runtime = get_runtime(conn, room_id)
    current_activity = get_activity(conn, runtime["current_activity_id"])
    settings_json = json.loads(room["settings_json"] or "{}")
    now = datetime.now()
    active_attempt = get_active_attempt(conn, participant["id"], room_id) if participant else None
    conn.commit()
    conn.close()
    participant_payload = []
    for row in participants:
        last_seen = datetime.fromisoformat(row["last_seen_at"])
        participant_payload.append({
            "id": row["id"],
            "name": row["name"],
            "presence_state": "online" if last_seen >= now - timedelta(seconds=60) else "away",
            "appearance": participant_appearance(row["metadata_json"]),
        })
    return jsonify({
        "status": room["status"], "participants": participant_payload,
        "mode": settings_json.get("mode", "self_paced"),
        "server_time": datetime.now().astimezone().isoformat(),
        "runtime_state": runtime["state"],
        "runtime_version": runtime["version"],
        "current_activity_type": current_activity["type"] if current_activity else None,
        "has_active_attempt": bool(active_attempt and not active_attempt["finished_at"]),
        "boosts": {},
        "boost_enabled": settings.lobby_boost_enabled,
        "viewer_id": participant["id"] if participant else None,
    })


@app.post("/api/presence/heartbeat")
def presence_heartbeat():
    conn = get_db()
    participant = current_participant(conn)
    if not participant or participant["left_at"]:
        conn.close()
        return jsonify({"error": "No active participant session"}), 401
    touch_participant(conn, participant["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "last_seen_at": now_iso()})


@app.post("/api/profile/avatar")
def update_participant_avatar():
    payload = request.get_json(silent=True) or {}
    appearance = payload.get("appearance") if isinstance(payload, dict) else None
    if not isinstance(appearance, dict):
        return jsonify({"error": "Передайте налаштування аватара."}), 400
    avatar = appearance.get("avatar")
    headwear = appearance.get("headwear")
    if avatar not in AVATAR_OPTIONS or (headwear is not None and headwear not in HEADWEAR_OPTIONS):
        return jsonify({"error": "Обраний елемент аватара недоступний."}), 400

    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "Немає активної сесії учасника."}), 401
    try:
        metadata = json.loads(participant["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata["appearance"] = {"avatar": avatar, "headwear": headwear}
    conn.execute(
        "UPDATE room_participants SET metadata_json = ?, last_seen_at = ? WHERE id = ?",
        (json.dumps(metadata), now_iso(), participant["id"]),
    )
    conn.commit()
    room_id = participant["room_id"]
    conn.close()
    emit_room_event(room_id, "room:presence", {"participant_id": participant["id"]})
    return jsonify({"ok": True, "appearance": metadata["appearance"]})


@app.post("/api/lobby/boost")
def lobby_boost():
    # Boost remains intentionally inactive. It will be reintroduced on top of
    # room_participants rather than the legacy students table.
    return jsonify({"error": "Функцію boost тимчасово вимкнено."}), 404


@app.post("/api/lobby/start")
def start_quiz():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "self_paced")
    if mode not in {"self_paced", "live"}:
        return jsonify({"error": "Невідомий режим кімнати."}), 400
    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    if runtime["current_activity_id"]:
        conn.close()
        return jsonify({"error": "Спершу завершіть або скасуйте поточну активність."}), 409
    questions = load_room_questions(conn, room["id"])
    if not questions:
        conn.close()
        return jsonify({"error": "Спочатку оберіть квіз із питаннями."}), 400
    activity_id = conn.insert_and_get_id(
        """
        INSERT INTO activities (room_id, type, status, config_json, started_at)
        VALUES (?, 'quiz', 'active', ?, ?)
        """,
        (
            room["id"],
            json.dumps({
                "mode": mode,
                "questions": questions,
                "shuffle_questions": SHUFFLE_QUESTIONS,
                "quiz_title": get_room_quiz_title(conn, room),
            }, ensure_ascii=False),
            now_iso(),
        ),
    )
    participants = conn.execute(
        "SELECT id FROM room_participants WHERE room_id = ? AND left_at IS NULL",
        (room["id"],),
    ).fetchall()
    question_ids = [question["id"] for question in questions]
    for participant in participants:
        order = list(question_ids)
        if SHUFFLE_QUESTIONS:
            random.shuffle(order)
        conn.execute(
            """
            INSERT INTO quiz_attempts
            (activity_id, participant_id, question_order_json, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (activity_id, participant["id"], json.dumps(order), now_iso()),
        )
    set_runtime(conn, room["id"], activity_id, "active")
    conn.execute(
        "UPDATE rooms SET status = 'active', settings_json = ? WHERE id = ?",
        (json.dumps({"mode": mode}), room["id"]),
    )
    conn.commit()
    conn.close()
    emit_room_state(room["id"])
    return jsonify({"ok": True})


@app.get("/quiz")
def quiz():
    conn = get_db()
    participant = current_participant(conn)
    if not participant or participant["left_at"]:
        conn.close()
        session.clear()
        return redirect(url_for("index"))
    touch_participant(conn, participant["id"])
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (participant["room_id"],)).fetchone()
    attempt = get_active_attempt(conn, participant["id"], participant["room_id"])
    if not room or not attempt:
        conn.commit()
        conn.close()
        return redirect(url_for("lobby"))
    runtime = get_runtime(conn, participant["room_id"])
    current_activity = get_activity(conn, runtime["current_activity_id"])
    if attempt["finished_at"] and current_activity and current_activity["type"] == "duel":
        conn.commit()
        conn.close()
        return redirect(url_for("activity_stage"))
    if attempt["finished_at"]:
        conn.commit()
        conn.close()
        return redirect(url_for("result"))
    activity = get_activity(conn, attempt["activity_id"])
    order = json.loads(attempt["question_order_json"])
    index = attempt["current_question"]
    question = activity_question_map(activity).get(order[index]) if activity and index < len(order) else None
    conn.commit()
    conn.close()
    if not question:
        return redirect(url_for("result"))
    return render_template(
        "quiz.html",
        question=public_question(question),
        question_number=index + 1,
        total_questions=len(order),
        participant_name=participant["display_name"],
        room_title=room["title"],
    )


@app.get("/activity")
def activity_stage():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return redirect(url_for("index"))
    touch_participant(conn, participant["id"])
    round_row = get_open_duel(conn, participant["room_id"])
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (participant["room_id"],)).fetchone()
    conn.commit()
    conn.close()
    if not round_row:
        return redirect(url_for("lobby"))
    return render_template("activity.html", room=room, participant_name=participant["display_name"])


@app.post("/api/answer")
def answer():
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    selected = data.get("selected_answers", [])
    response_time = data.get("response_time", 0)

    if not isinstance(selected, list) or not selected:
        return jsonify({"error": "Select at least one answer"}), 400

    try:
        response_time = max(0.0, float(response_time))
        selected = sorted({int(x) for x in selected})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid answer data"}), 400

    conn = get_db()
    participant = current_participant(conn)
    if not participant or participant["left_at"]:
        conn.close()
        return jsonify({"error": "No active participant session"}), 401
    touch_participant(conn, participant["id"])
    attempt = get_active_attempt(conn, participant["id"], participant["room_id"])
    if not attempt or attempt["finished_at"]:
        conn.commit()
        conn.close()
        return jsonify({"error": "Quiz attempt is not active"}), 400
    runtime = get_runtime(conn, participant["room_id"])
    activity = get_activity(conn, attempt["activity_id"])
    if runtime["current_activity_id"] != attempt["activity_id"] or not activity or activity["status"] != "active":
        conn.commit()
        conn.close()
        return jsonify({"error": "Квіз призупинено іншою активністю.", "code": "activity_paused"}), 409

    order = json.loads(attempt["question_order_json"])
    current_index = attempt["current_question"]
    if current_index >= len(order):
        conn.commit()
        conn.close()
        return jsonify({"error": "Quiz already finished"}), 400
    expected_question_id = order[current_index]
    if question_id != expected_question_id:
        conn.commit()
        conn.close()
        return jsonify({"error": "Question mismatch"}), 409
    question = activity_question_map(activity).get(question_id)
    if not question:
        conn.commit()
        conn.close()
        return jsonify({"error": "Unknown question"}), 404
    correct = sorted(question["correct"])
    is_correct = selected == correct
    existing = conn.execute(
        "SELECT id FROM quiz_attempt_answers WHERE attempt_id = ? AND question_id = ?",
        (attempt["id"], question_id),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Answer already submitted"}), 409

    conn.execute(
        """
        INSERT INTO quiz_attempt_answers
        (attempt_id, question_id, selected_answers_json, is_correct, response_time, answered_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            attempt["id"],
            question_id,
            json.dumps(selected),
            is_correct,
            response_time,
            now_iso(),
        ),
    )

    new_index = current_index + 1
    new_score = attempt["score"] + int(is_correct)
    finished_at = now_iso() if new_index >= len(order) else None

    conn.execute(
        """
        UPDATE quiz_attempts
        SET current_question = ?, score = ?, finished_at = COALESCE(?, finished_at)
        WHERE id = ?
        """,
        (new_index, new_score, finished_at, attempt["id"]),
    )
    conn.commit()
    conn.close()
    emit_room_event(participant["room_id"], "room:results_updated")

    return jsonify(
        {
            "ok": True,
            "is_correct": is_correct,
            "correct_answers": correct,
            "explanation": question.get("explanation", ""),
            "finished": new_index >= len(order),
            "score": new_score,
        }
    )


@app.get("/api/roulette/current")
def current_roulette():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    touch_participant(conn, participant["id"])
    round_row = get_open_duel(conn, participant["room_id"])
    payload = serialize_roulette(conn, round_row, participant["id"])
    conn.commit()
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/roulette/answer")
def roulette_answer():
    data = request.get_json(silent=True) or {}
    answer_text = (data.get("answer") or "").strip()
    if not answer_text or len(answer_text) > 1000:
        return jsonify({"error": "Answer must contain 1–1000 characters"}), 400

    conn = get_db()
    participant_session = current_participant(conn)
    if not participant_session:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    participant_id = participant_session["id"]
    room_id = participant_session["room_id"]
    touch_participant(conn, participant_id)
    round_row = get_open_duel(conn, room_id)
    if not round_row or round_row["status"] != "answering":
        conn.close()
        return jsonify({"error": "No active answering round"}), 409

    participant = conn.execute(
        """
        SELECT answer_text FROM duel_participants
        WHERE round_id = ? AND participant_id = ?
        """,
        (round_row["id"], participant_id),
    ).fetchone()
    if not participant or participant["answer_text"]:
        conn.close()
        return jsonify({"error": "You cannot submit an answer for this round"}), 403

    conn.execute(
        """
        UPDATE duel_participants
        SET answer_text = ?, answered_at = ?
        WHERE round_id = ? AND participant_id = ?
        """,
        (answer_text, now_iso(), round_row["id"], participant_id),
    )
    answered_count = conn.execute(
        """
        SELECT COUNT(*) AS count FROM duel_participants
        WHERE round_id = ? AND answer_text IS NOT NULL
        """,
        (round_row["id"],),
    ).fetchone()["count"]
    if answered_count == 2:
        conn.execute(
            "UPDATE duel_rounds SET status = 'voting' WHERE id = ?",
            (round_row["id"],),
        )
    conn.commit()
    round_row = get_open_duel(conn, room_id)
    payload = serialize_roulette(conn, round_row, participant_id)
    conn.close()
    emit_room_event(room_id, "room:duel_updated")
    return jsonify({"round": payload})


@app.post("/api/roulette/vote")
def roulette_vote():
    data = request.get_json(silent=True) or {}
    choice_student_id = data.get("choice_student_id")
    try:
        choice_student_id = int(choice_student_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid choice"}), 400

    conn = get_db()
    participant_session = current_participant(conn)
    if not participant_session:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    participant_id = participant_session["id"]
    room_id = participant_session["room_id"]
    touch_participant(conn, participant_id)
    round_row = get_open_duel(conn, room_id)
    if not round_row or round_row["status"] != "voting":
        conn.close()
        return jsonify({"error": "Voting is not active"}), 409

    participants = conn.execute(
        "SELECT participant_id FROM duel_participants WHERE round_id = ?",
        (round_row["id"],),
    ).fetchall()
    participant_ids = {row["participant_id"] for row in participants}
    if participant_id in participant_ids or choice_student_id not in participant_ids:
        conn.close()
        return jsonify({"error": "You cannot vote for this participant"}), 403

    existing_vote = conn.execute(
        "SELECT 1 FROM duel_votes WHERE round_id = ? AND voter_id = ?",
        (round_row["id"], participant_id),
    ).fetchone()
    if existing_vote:
        conn.close()
        return jsonify({"error": "You have already liked an answer"}), 409

    conn.execute(
        """
        INSERT INTO duel_votes (round_id, voter_id, choice_participant_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (round_row["id"], participant_id, choice_student_id, now_iso()),
    )
    conn.commit()
    payload = serialize_roulette(conn, round_row, participant_id)
    conn.close()
    emit_room_event(room_id, "room:duel_updated")
    return jsonify({"round": payload})


@app.get("/result")
def result():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return redirect(url_for("index"))
    touch_participant(conn, participant["id"])
    attempt = get_active_attempt(conn, participant["id"], participant["room_id"])
    runtime = get_runtime(conn, participant["room_id"])
    current_activity = get_activity(conn, runtime["current_activity_id"])
    if current_activity and current_activity["type"] == "duel":
        conn.commit()
        conn.close()
        return redirect(url_for("activity_stage"))
    if not attempt or not attempt["finished_at"]:
        conn.commit()
        conn.close()
        return redirect(url_for("lobby"))
    total = len(json.loads(attempt["question_order_json"]))
    score = attempt["score"]
    percent = round((score / total) * 100) if total else 0
    rows = conn.execute(
        "SELECT response_time FROM quiz_attempt_answers WHERE attempt_id = ?",
        (attempt["id"],),
    ).fetchall()
    conn.commit()
    conn.close()
    total_seconds = int(sum(row["response_time"] for row in rows))
    minutes, seconds = divmod(total_seconds, 60)

    return render_template(
        "result.html",
        student=participant,
        score=score,
        total=total,
        percent=percent,
        rank=compute_rank(percent),
        total_time=f"{minutes:02d}:{seconds:02d}",
    )


@app.post("/leave")
def leave_room():
    conn = get_db()
    participant = current_participant(conn)
    room_id = participant["room_id"] if participant else None
    if participant:
        conn.execute(
            "UPDATE room_participants SET left_at = ? WHERE id = ? AND room_id = ?",
            (now_iso(), participant["id"], participant["room_id"]),
        )
        conn.commit()
    conn.close()
    if room_id:
        emit_room_event(room_id, "room:presence", {"participant_id": participant["id"], "left": True})
    session.clear()
    return redirect(url_for("index"))


@app.post("/retry")
def retry_quiz():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return redirect(url_for("index"))
    attempt = get_active_attempt(conn, participant["id"], participant["room_id"])
    runtime = get_runtime(conn, participant["room_id"])
    if not attempt or not attempt["finished_at"] or runtime["current_activity_id"] != attempt["activity_id"]:
        conn.close()
        return redirect(url_for("lobby"))
    activity = get_activity(conn, attempt["activity_id"])
    question_ids = [question["id"] for question in activity_questions(activity)]
    if json.loads(activity["config_json"]).get("shuffle_questions"):
        random.shuffle(question_ids)
    conn.execute(
        "UPDATE quiz_attempts SET abandoned_at = ? WHERE id = ?",
        (now_iso(), attempt["id"]),
    )
    conn.execute(
        """
        INSERT INTO quiz_attempts (activity_id, participant_id, question_order_json, started_at)
        VALUES (?, ?, ?, ?)
        """,
        (activity["id"], participant["id"], json.dumps(question_ids), now_iso()),
    )
    touch_participant(conn, participant["id"])
    conn.commit()
    conn.close()
    emit_room_event(participant["room_id"], "room:results_updated")
    return redirect(url_for("quiz"))


@app.get("/admin")
def admin():
    room = get_current_host_room()
    if not room:
        return redirect(url_for("index"))
    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    current_activity = get_activity(conn, runtime["current_activity_id"])
    quiz_title = get_room_quiz_title(conn, room)
    extra_round = get_open_duel(conn, room["id"]) if current_activity and current_activity["type"] == "duel" else None
    quiz_question_count = len(load_room_questions(conn, room["id"]))
    if current_activity and current_activity["type"] == "quiz":
        quiz_config = json.loads(current_activity["config_json"] or "{}")
        quiz_title = quiz_config.get("quiz_title") or quiz_title
        quiz_question_count = len(quiz_config.get("questions", [])) or quiz_question_count
    conn.commit()
    conn.close()
    return render_template(
        "admin.html",
        authenticated=True,
        room=room,
        runtime=runtime,
        current_activity=current_activity,
        extra_round=extra_round,
        quiz_title=quiz_title,
        quiz_question_count=quiz_question_count,
    )


@app.get("/admin/quizzes")
def quizzes():
    room = get_current_host_room()
    if not room:
        return redirect(url_for("index"))
    return render_template("quizzes.html", room=room)


@app.get("/api/admin/quizzes")
def admin_quizzes():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, questions_json, created_at FROM quizzes WHERE room_id = ? ORDER BY id DESC",
        (room["id"],),
    ).fetchall()
    conn.close()
    quizzes = [{
        "id": row["id"], "title": row["title"], "count": len(json.loads(row["questions_json"])),
        "created_at": row["created_at"], "active": row["id"] == room["active_quiz_id"],
    } for row in rows]
    return jsonify({
        "active_quiz_id": room["active_quiz_id"],
        "built_in": {"id": None, "title": "Django та Git — готовий квіз", "count": len(load_questions()), "active": not room["active_quiz_id"]},
        "quizzes": quizzes,
    })


@app.post("/api/admin/quizzes")
def save_quiz():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        title, questions = validate_quiz_payload(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    conn = get_db()
    quiz_id = conn.insert_and_get_id(
        "INSERT INTO quizzes (room_id, title, questions_json, created_at) VALUES (?, ?, ?, ?)",
        (room["id"], title, json.dumps(questions, ensure_ascii=False), now_iso()),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": quiz_id, "title": title, "count": len(questions)}), 201


@app.post("/api/admin/quizzes/<int:quiz_id>/activate")
def activate_quiz(quiz_id):
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    quiz = conn.execute("SELECT id FROM quizzes WHERE id = ? AND room_id = ?", (quiz_id, room["id"])).fetchone()
    if runtime["current_activity_id"]:
        conn.close()
        return jsonify({"error": "Спершу очистіть результати кімнати, щоб змінити квіз."}), 409
    if not quiz:
        conn.close()
        return jsonify({"error": "Квіз не знайдено."}), 404
    conn.execute("UPDATE rooms SET active_quiz_id = ? WHERE id = ?", (quiz_id, room["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.post("/api/admin/quizzes/default/activate")
def activate_default_quiz():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    if runtime["current_activity_id"]:
        conn.close()
        return jsonify({"error": "Спершу очистіть результати кімнати, щоб змінити квіз."}), 409
    conn.execute("UPDATE rooms SET active_quiz_id = NULL WHERE id = ?", (room["id"],))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.post("/admin/logout")
def admin_logout():
    # Logging out only ends the host browser session. It never resets a room.
    session.clear()
    return redirect(url_for("index"))


@app.get("/api/admin/roulette")
def admin_roulette():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_duel(conn, room["id"])
    payload = serialize_roulette(conn, round_row)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/admin/roulette")
def start_roulette():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question or len(question) > 1000:
        return jsonify({"error": "Question must contain 1–1000 characters"}), 400

    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    quiz_activity = get_activity(conn, runtime["current_activity_id"])
    if not quiz_activity or quiz_activity["type"] != "quiz" or quiz_activity["status"] != "active":
        conn.close()
        return jsonify({"error": "ДВИЖ-ДУЕЛЬ можна запустити лише під час активного квіза."}), 409
    participant_rows = conn.execute(
        """
        SELECT id, display_name AS name, last_seen_at FROM room_participants
        WHERE room_id = ? AND left_at IS NULL
        ORDER BY id
        """,
        (room["id"],),
    ).fetchall()
    online_threshold = datetime.now() - timedelta(seconds=60)
    active_participants = [row for row in participant_rows if datetime.fromisoformat(row["last_seen_at"]) >= online_threshold]
    if len(active_participants) < 2:
        conn.close()
        return jsonify({"error": "At least two active participants are needed"}), 400

    selected = random.sample(active_participants, 2)
    conn.execute("UPDATE activities SET status = 'paused', paused_at = ? WHERE id = ?", (now_iso(), quiz_activity["id"]))
    duel_activity_id = conn.insert_and_get_id(
        """
        INSERT INTO activities (room_id, type, status, config_json, started_at)
        VALUES (?, 'duel', 'active', ?, ?)
        """,
        (room["id"], json.dumps({"resume_activity_id": quiz_activity["id"]}), now_iso()),
    )
    round_id = conn.insert_and_get_id(
        """
        INSERT INTO duel_rounds (room_id, activity_id, question, candidate_pool_json, status, created_at)
        VALUES (?, ?, ?, ?, 'answering', ?)
        """,
        (room["id"], duel_activity_id, question, json.dumps([participant["name"] for participant in active_participants]), now_iso()),
    )
    conn.executemany(
        """
        INSERT INTO duel_participants (round_id, participant_id)
        VALUES (?, ?)
        """,
        [(round_id, participant["id"]) for participant in selected],
    )
    set_runtime(conn, room["id"], duel_activity_id, "active")
    conn.commit()
    round_row = get_open_duel(conn, room["id"])
    payload = serialize_roulette(conn, round_row)
    conn.close()
    emit_room_state(room["id"])
    emit_room_event(room["id"], "room:duel_updated")
    return jsonify({"round": payload}), 201


@app.post("/api/admin/roulette/close")
def close_roulette():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_duel(conn, room["id"])
    if not round_row:
        conn.close()
        return jsonify({"error": "Немає активного ДВИЖ-ДУЕЛЮ."}), 409

    conn.execute(
        "UPDATE duel_rounds SET status = 'closed' WHERE id = ?",
        (round_row["id"],),
    )
    duel_activity = get_activity(conn, round_row["activity_id"])
    conn.execute("UPDATE activities SET status = 'finished', finished_at = ? WHERE id = ?", (now_iso(), duel_activity["id"]))
    resume_activity_id = json.loads(duel_activity["config_json"]).get("resume_activity_id")
    if resume_activity_id:
        conn.execute("UPDATE activities SET status = 'active', paused_at = NULL WHERE id = ?", (resume_activity_id,))
        set_runtime(conn, room["id"], resume_activity_id, "active")
    else:
        set_runtime(conn, room["id"], None, "lobby")
    conn.commit()
    conn.close()
    emit_room_state(room["id"])
    return jsonify({"ok": True})


@app.get("/api/admin/results")
def admin_results():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    latest_quiz = conn.execute(
        "SELECT id FROM activities WHERE room_id = ? AND type = 'quiz' ORDER BY id DESC LIMIT 1",
        (room["id"],),
    ).fetchone()
    activity_id = latest_quiz["id"] if latest_quiz else -1
    rows = conn.execute(
        """
        SELECT
            rp.id, rp.display_name AS name, rp.joined_at,
            qa.score, qa.finished_at, qa.question_order_json,
            COUNT(a.id) AS answered,
            COALESCE(SUM(a.response_time), 0) AS total_time
        FROM room_participants rp
        LEFT JOIN quiz_attempts qa ON qa.id = (
            SELECT qa2.id FROM quiz_attempts qa2
            WHERE qa2.participant_id = rp.id AND qa2.activity_id = ?
            ORDER BY qa2.id DESC LIMIT 1
        )
        LEFT JOIN quiz_attempt_answers a ON a.attempt_id = qa.id
        WHERE rp.room_id = ?
        GROUP BY rp.id, rp.display_name, rp.joined_at, qa.score, qa.finished_at, qa.question_order_json
        ORDER BY rp.joined_at DESC
        """,
        (activity_id, room["id"]),
    ).fetchall()
    conn.close()

    students = []
    for row in rows:
        total = len(json.loads(row["question_order_json"])) if row["question_order_json"] else 0
        score = row["score"] or 0
        percent = round((score / total) * 100) if total else 0
        students.append(
            {
                "id": row["id"],
                "name": row["name"],
                "answered": row["answered"],
                "total": total,
                "score": score,
                "percent": percent,
                "finished": bool(row["finished_at"]),
                "total_time": round(row["total_time"], 1),
                "started_at": row["joined_at"],
            }
        )

    return jsonify(
        {
            "students": students,
            "connected": len(students),
            "finished": sum(1 for s in students if s["finished"]),
            "active": sum(1 for s in students if not s["finished"]),
        }
    )


@app.get("/api/admin/student/<int:student_id>")
def admin_student(student_id):
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    student = conn.execute(
        "SELECT * FROM room_participants WHERE id = ? AND room_id = ?",
        (student_id, room["id"]),
    ).fetchone()
    attempt = conn.execute(
        """
        SELECT qa.*, a.config_json FROM quiz_attempts qa
        JOIN activities a ON a.id = qa.activity_id
        WHERE qa.participant_id = ? AND a.room_id = ?
        ORDER BY qa.id DESC LIMIT 1
        """,
        (student_id, room["id"]),
    ).fetchone()
    answers = conn.execute(
        """
        SELECT * FROM quiz_attempt_answers
        WHERE attempt_id = ?
        ORDER BY id
        """,
        (attempt["id"] if attempt else -1,),
    ).fetchall()
    conn.close()

    if not student:
        return jsonify({"error": "Student not found"}), 404

    questions = json.loads(attempt["config_json"]).get("questions", []) if attempt else []
    qmap = {question["id"]: question for question in questions}
    details = []
    for answer in answers:
        q = qmap.get(answer["question_id"])
        if not q:
            continue
        selected_indexes = json.loads(answer["selected_answers_json"])
        details.append(
            {
                "question_id": answer["question_id"],
                "question": q["question"],
                "selected": [q["answers"][i] for i in selected_indexes if i < len(q["answers"])],
                "correct_answers": [q["answers"][i] for i in q["correct"]],
                "is_correct": bool(answer["is_correct"]),
                "response_time": round(answer["response_time"], 1),
            }
        )

    return jsonify({"student": dict(student), "answers": details})


@app.post("/api/admin/reset")
def admin_reset():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    clear_room_runtime(conn, room["id"])
    conn.execute("UPDATE rooms SET status = 'lobby' WHERE id = ?", (room["id"],))
    conn.commit()
    conn.close()
    emit_room_state(room["id"])
    return jsonify({"ok": True})


@app.post("/api/admin/return-to-lobby")
def admin_return_to_lobby():
    """End a completed quiz activity while preserving its temporary results."""
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    activity = get_activity(conn, runtime["current_activity_id"])
    if not activity or activity["type"] != "quiz" or activity["status"] != "active":
        conn.close()
        return jsonify({"error": "Немає активного квіза для завершення."}), 409
    unfinished = conn.execute(
        """
        SELECT COUNT(*) AS count FROM quiz_attempts
        WHERE activity_id = ? AND abandoned_at IS NULL AND finished_at IS NULL
        """,
        (activity["id"],),
    ).fetchone()["count"]
    if unfinished:
        conn.close()
        return jsonify({"error": "Повернутися до лобі можна після завершення всіх активних спроб."}), 409

    conn.execute(
        "UPDATE activities SET status = 'finished', finished_at = ? WHERE id = ?",
        (now_iso(), activity["id"]),
    )
    set_runtime(conn, room["id"], None, "lobby")
    conn.execute("UPDATE rooms SET status = 'lobby' WHERE id = ?", (room["id"],))
    conn.commit()
    conn.close()
    emit_room_state(room["id"])
    return jsonify({"ok": True})


@app.post("/api/admin/finish")
def admin_finish_room():
    """Explicitly end a live room; unlike logout this affects the room."""
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    clear_room_runtime(conn, room["id"])
    conn.execute("UPDATE room_participants SET left_at = COALESCE(left_at, ?) WHERE room_id = ?", (now_iso(), room["id"]))
    conn.execute("UPDATE rooms SET status = 'finished' WHERE id = ?", (room["id"],))
    conn.commit()
    conn.close()
    emit_room_state(room["id"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
