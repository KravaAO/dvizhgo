import json
import random
import logging
from datetime import datetime, timedelta

from flask import (
    jsonify, redirect, render_template,
    request, session, url_for
)
from flask_socketio import SocketIO, join_room as join_socket_room
from quiz_app.bootstrap import app, socketio
from quiz_app.config import settings
from quiz_app.database import connect_database, initialize_database
from quiz_app.rooms import (
    create_room,
    get_host_room as find_host_room,
    get_room_by_code,
)
from quiz_app.services import quiz_content
from quiz_app.repositories.quizzes import QuizRepository
from quiz_app.services.room_runtime import (
    create_late_quiz_attempt as create_late_quiz_attempt_service,
    get_active_attempt,
    get_activity,
    get_runtime,
    now_iso,
    resumed_quiz_activity,
    room_socket_state,
    set_runtime,
)
from quiz_app.services import participants as participant_service

BASE_DIR = settings.base_dir
DB_PATH = settings.sqlite_path
DATABASE_URL = settings.database_url
QUESTIONS_PATH = BASE_DIR / "questions.json"

ADMIN_PASSWORD = settings.admin_password
SHUFFLE_ANSWERS = settings.shuffle_answers
SHUFFLE_QUESTIONS = settings.shuffle_questions
AVATAR_OPTIONS = ("avatar-1", "avatar-2", "avatar-3", "avatar-4")
HEADWEAR_OPTIONS = (
    "headwear-1", "headwear-2", "headwear-3", "headwear-4", "headwear-5",
    "headwear-6", "headwear-7", "headwear-8", "headwear-9",
)
BOOST_DURATION_SECONDS = 5
BOOST_COOLDOWN_SECONDS = 15
LOBBY_BOOST_ACTIVE = True
DVD_TELEMETRY_SEEN = {}
FLASH_QUESTION_DEFAULT_SECONDS = 20
FLASH_QUESTION_MIN_SECONDS = 10
FLASH_QUESTION_MAX_SECONDS = 180
FLASH_QUESTION_INTRO_SECONDS = 2
FLASH_QUESTION_CLOSE_DELAY_SECONDS = 5


def get_db():
    return connect_database(DATABASE_URL, DB_PATH)


def init_db():
    initialize_database(DATABASE_URL, DB_PATH)


def load_questions():
    return quiz_content.load_questions(QUESTIONS_PATH)


def load_room_questions(conn, room_id):
    return quiz_content.load_room_questions(QuizRepository(conn), room_id, QUESTIONS_PATH)


def get_room_quiz_title(conn, room):
    return quiz_content.get_room_quiz_title(QuizRepository(conn), room)


def get_question_map(room_id=None):
    if not room_id:
        return {q["id"]: q for q in load_questions()}
    conn = get_db()
    questions = load_room_questions(conn, room_id)
    conn.close()
    return {q["id"]: q for q in questions}


def validate_quiz_payload(payload):
    return quiz_content.validate_quiz_payload(payload)


def token_hash(token):
    return participant_service.token_hash(token)


def random_avatar_appearance():
    return participant_service.random_avatar_appearance(AVATAR_OPTIONS, HEADWEAR_OPTIONS)


def participant_appearance(metadata_json):
    return participant_service.participant_appearance(metadata_json, AVATAR_OPTIONS, HEADWEAR_OPTIONS)


def current_participant(conn=None):
    own_connection = conn is None
    if own_connection:
        conn = get_db()
    row = participant_service.current_participant(
        conn, session.get("participant_id"), session.get("room_id"), session.get("participant_reconnect_token"),
    )
    if own_connection:
        conn.close()
    return row


def create_room_participant(conn, room_id, display_name):
    return participant_service.create_room_participant(
        conn, room_id, display_name, AVATAR_OPTIONS, HEADWEAR_OPTIONS,
    )


def touch_participant(conn, participant_id):
    participant_service.touch_participant(conn, participant_id)


def lobby_boost_state(conn, room_id):
    return participant_service.lobby_boost_state(conn, room_id)


def socket_room_name(room_id):
    return f"room:{room_id}"


def emit_room_event(room_id, event, payload=None):
    socketio.emit(event, payload or {}, to=socket_room_name(room_id))


def emit_room_state(room_id):
    conn = get_db()
    payload = room_socket_state(conn, room_id)
    conn.commit()
    conn.close()
    emit_room_event(room_id, "room:state", payload)


def activity_questions(activity):
    return quiz_content.activity_questions(activity)


def activity_question_map(activity):
    return quiz_content.activity_question_map(activity)


def create_late_quiz_attempt(conn, participant_id, quiz_activity):
    return create_late_quiz_attempt_service(conn, participant_id, quiz_activity, activity_questions)


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
    return quiz_content.public_question(question, SHUFFLE_ANSWERS)


def compute_rank(percent):
    return quiz_content.compute_rank(percent)


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


def get_open_flash_question(conn, room_id):
    return conn.execute(
        """
        SELECT * FROM activities
        WHERE room_id = ? AND type = 'flash_question' AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (room_id,),
    ).fetchone()


def flash_question_closes_at(activity, config):
    closes_at = config.get("closes_at")
    if closes_at:
        return closes_at
    ends_at = config.get("ends_at")
    if not ends_at:
        return None
    return (datetime.fromisoformat(ends_at) + timedelta(
        seconds=FLASH_QUESTION_CLOSE_DELAY_SECONDS
    )).isoformat(timespec="seconds")


def flash_question_target_status(conn, activity, config=None):
    config = config or json.loads(activity["config_json"] or "{}")
    raw_ids = config.get("target_participant_ids") or []
    target_ids = sorted({int(participant_id) for participant_id in raw_ids if str(participant_id).isdigit()})
    if not target_ids:
        return 0, 0, False

    placeholders = ",".join("?" for _ in target_ids)
    active_rows = conn.execute(
        f"SELECT id FROM room_participants WHERE left_at IS NULL AND id IN ({placeholders})",
        target_ids,
    ).fetchall()
    active_ids = [row["id"] for row in active_rows]
    if not active_ids:
        return 0, 0, True

    active_placeholders = ",".join("?" for _ in active_ids)
    answered_count = conn.execute(
        f"""
        SELECT COUNT(*) AS count FROM flash_question_answers
        WHERE activity_id = ? AND participant_id IN ({active_placeholders})
        """,
        (activity["id"], *active_ids),
    ).fetchone()["count"]
    return len(active_ids), answered_count, answered_count >= len(active_ids)


def complete_flash_question_if_all_answered(conn, activity):
    if not activity:
        return False
    config = json.loads(activity["config_json"] or "{}")
    target_count, target_answer_count, all_answered = flash_question_target_status(conn, activity, config)
    if not all_answered or not target_count or config.get("completion_reason"):
        return False
    ends_at = config.get("ends_at")
    if ends_at and datetime.fromisoformat(ends_at) <= datetime.now():
        return False

    completed_at = datetime.now()
    config["ends_at"] = completed_at.isoformat(timespec="seconds")
    config["closes_at"] = (completed_at + timedelta(
        seconds=FLASH_QUESTION_CLOSE_DELAY_SECONDS
    )).isoformat(timespec="seconds")
    config["completion_reason"] = "all_answered"
    config["target_answer_count"] = target_answer_count
    conn.execute(
        "UPDATE activities SET config_json = ? WHERE id = ? AND status = 'active'",
        (json.dumps(config, ensure_ascii=False), activity["id"]),
    )
    return True


def finish_flash_question_activity(conn, activity):
    """Finish one active Flash Question and restore its paused quiz atomically."""
    updated = conn.execute(
        "UPDATE activities SET status = 'finished', finished_at = ? WHERE id = ? AND status = 'active'",
        (now_iso(), activity["id"]),
    )
    if updated.rowcount != 1:
        return False

    config = json.loads(activity["config_json"] or "{}")
    runtime = get_runtime(conn, activity["room_id"])
    if runtime["current_activity_id"] != activity["id"]:
        return True
    resume_activity_id = config.get("resume_activity_id")
    if resume_activity_id:
        conn.execute(
            "UPDATE activities SET status = 'active', paused_at = NULL WHERE id = ? AND status = 'paused'",
            (resume_activity_id,),
        )
        set_runtime(conn, activity["room_id"], resume_activity_id, "active")
    else:
        set_runtime(conn, activity["room_id"], None, "lobby")
    return True


def finish_flash_question_if_expired(conn, activity):
    if not activity:
        return False
    config = json.loads(activity["config_json"] or "{}")
    closes_at = flash_question_closes_at(activity, config)
    if not closes_at or datetime.fromisoformat(closes_at) > datetime.now():
        return False
    return finish_flash_question_activity(conn, activity)


def serialize_flash_question(conn, activity, participant_id=None, is_host=False):
    if not activity:
        return None
    config = json.loads(activity["config_json"] or "{}")
    answers = config.get("answers", [])
    ends_at = config.get("ends_at")
    duration_seconds = config.get("duration_seconds")
    if duration_seconds is None and ends_at:
        try:
            duration_seconds = max(1, round(
                (datetime.fromisoformat(ends_at) - datetime.fromisoformat(activity["started_at"])).total_seconds()
            ))
        except (TypeError, ValueError):
            duration_seconds = FLASH_QUESTION_DEFAULT_SECONDS
    duration_seconds = duration_seconds or FLASH_QUESTION_DEFAULT_SECONDS
    deadline_reached = bool(ends_at and datetime.fromisoformat(ends_at) <= datetime.now())
    submitted = None
    if participant_id:
        submitted = conn.execute(
            "SELECT selected_index FROM flash_question_answers WHERE activity_id = ? AND participant_id = ?",
            (activity["id"], participant_id),
        ).fetchone()
    answer_count = conn.execute(
        "SELECT COUNT(*) AS count FROM flash_question_answers WHERE activity_id = ?",
        (activity["id"],),
    ).fetchone()["count"]
    target_count, target_answer_count, all_answered = flash_question_target_status(conn, activity, config)
    payload = {
        "id": activity["id"],
        "question": config.get("question", ""),
        "answers": answers,
        "duration_seconds": duration_seconds,
        "starts_at": config.get("starts_at", activity["started_at"]),
        "ends_at": ends_at,
        "closes_at": flash_question_closes_at(activity, config),
        "close_delay_seconds": FLASH_QUESTION_CLOSE_DELAY_SECONDS,
        "completion_reason": config.get("completion_reason"),
        "server_time": now_iso(),
        "answer_count": answer_count,
        "target_count": target_count,
        "target_answer_count": target_answer_count,
        "all_answered": all_answered,
        "answered": bool(submitted),
        "deadline_reached": deadline_reached,
    }
    if submitted or deadline_reached or is_host:
        payload["correct_index"] = config.get("correct_index")
    if submitted:
        payload["selected_index"] = submitted["selected_index"]
    return payload


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
    conn.execute(f"DELETE FROM flash_question_answers WHERE activity_id IN ({activity_ids})", (room_id,))
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
    duel_activity = get_activity(conn, round_row["activity_id"])
    activity_config = json.loads(duel_activity["config_json"] or "{}") if duel_activity else {}
    selected_order = activity_config.get("selected_participant_ids") or []
    selected_positions = {participant_id: index for index, participant_id in enumerate(selected_order)}
    participants.sort(key=lambda participant: selected_positions.get(participant["student_id"], len(selected_positions)))
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


@app.get("/how-it-works")
def how_it_works():
    """Public onboarding guide; it deliberately contains no room data."""
    return render_template("how_it_works.html")


@app.get("/how-it-works/dvizh-duel")
def dvizh_duel_info():
    return render_template(
        "activity_mode.html",
        mode={
            "slug": "duel",
            "eyebrow": "EXTRA ACTIVITY / × 2 PLAYERS",
            "name": "ДВИЖ-ДУЕЛЬ",
            "headline": "Два гравці.<br>Один <span>виклик.</span>",
            "intro": "Коротка жива пауза в квізі: система випадково обирає двох активних учасників, а група обирає відповідь, яка їй сподобалась найбільше.",
            "when": "Коли енергія падає, хочеться залучити тих, хто менше говорив, або швидко перезавантажити увагу групи.",
            "steps": [
                ("01", "Сформулюйте виклик", "Напишіть коротке відкрите завдання для двох учасників."),
                ("02", "DvizhGO обере двох", "Квіз стане на паузу, а система випадково обере двох активних людей."),
                ("03", "Відповіді та голосування", "Двоє відповідають, а решта групи обирає відповідь, яка їм подобається."),
                ("04", "Повернення до квіза", "Завершіть режим — усі автоматично продовжать свій поточний квіз."),
            ],
            "notice": "Для запуску потрібно щонайменше двоє активних учасників.",
        },
    )


@app.get("/how-it-works/flash-question")
def flash_question_info():
    return render_template(
        "activity_mode.html",
        mode={
            "slug": "flash",
            "eyebrow": "EXTRA ACTIVITY / ALL PLAY",
            "name": "FLASH QUESTION",
            "headline": "Одне питання.<br><span>Уся</span> кімната.",
            "intro": "Швидке питання з трьома варіантами відповіді для всіх учасників одночасно. Це короткий спосіб перевірити увагу або змінити ритм заняття.",
            "when": "Коли потрібна швидка перевірка розуміння, розігрів перед наступною темою або спільний момент для всієї групи.",
            "steps": [
                ("01", "Додайте питання", "Вкажіть питання, три варіанти та правильну відповідь."),
                ("02", "Оберіть час", "Встановіть від 10 секунд до 3 хвилин на відповідь."),
                ("03", "Усі відповідають", "Квіз стане на паузу, а завдання відкриється учасникам одночасно."),
                ("04", "Квіз продовжується", "Після завершення Flash Question учасники повернуться до свого квіза."),
            ],
            "notice": "Найкраще працюють короткі зрозумілі питання, які можна прочитати за кілька секунд.",
        },
    )


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
    runtime = get_runtime(conn, room["id"])
    current_activity = get_activity(conn, runtime["current_activity_id"])
    destination = "lobby"
    if current_activity and current_activity["status"] == "active":
        quiz_activity = resumed_quiz_activity(conn, current_activity)
        if quiz_activity and create_late_quiz_attempt(conn, participant_id, quiz_activity):
            destination = "activity" if current_activity["type"] in {"duel", "flash_question"} else "quiz"
    conn.commit()
    conn.close()

    session.clear()
    session["participant_id"] = participant_id
    session["room_id"] = room["id"]
    session["participant_reconnect_token"] = reconnect_token
    session["sound_enabled"] = True
    emit_room_event(room["id"], "room:presence", {"participant_id": participant_id})
    return redirect(url_for("activity_stage" if destination == "activity" else destination))


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
    current_activity = get_activity(conn, runtime["current_activity_id"])
    active_attempt = get_active_attempt(conn, participant["id"], room["id"])
    conn.commit()
    conn.close()
    if current_activity and current_activity["type"] in {"duel", "flash_question"}:
        return redirect(url_for("activity_stage"))
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
    boosts = lobby_boost_state(conn, room_id)
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
        "boosts": boosts,
        "boost_enabled": LOBBY_BOOST_ACTIVE,
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
    if not LOBBY_BOOST_ACTIVE:
        return jsonify({"error": "Boost тимчасово недоступний."}), 404
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "Немає активної сесії учасника."}), 401
    room = conn.execute("SELECT status FROM rooms WHERE id = ?", (participant["room_id"],)).fetchone()
    runtime = get_runtime(conn, participant["room_id"])
    if not room or room["status"] != "lobby" or runtime["current_activity_id"]:
        conn.close()
        return jsonify({"error": "Boost доступний лише у лобі до старту квіза."}), 409
    now = datetime.now()
    existing = conn.execute(
        "SELECT cooldown_until FROM room_lobby_boosts WHERE room_id = ? AND participant_id = ?",
        (participant["room_id"], participant["id"]),
    ).fetchone()
    if existing and datetime.fromisoformat(existing["cooldown_until"]) > now:
        seconds = max(1, int((datetime.fromisoformat(existing["cooldown_until"]) - now).total_seconds() + .999))
        conn.close()
        return jsonify({"error": f"Boost перезаряджається: ще {seconds} с."}), 409
    boosted_until = now + timedelta(seconds=BOOST_DURATION_SECONDS)
    cooldown_until = now + timedelta(seconds=BOOST_COOLDOWN_SECONDS)
    conn.execute(
        """
        INSERT INTO room_lobby_boosts (room_id, participant_id, boosted_until, cooldown_until)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(room_id, participant_id) DO UPDATE SET
            boosted_until = excluded.boosted_until,
            cooldown_until = excluded.cooldown_until
        """,
        (participant["room_id"], participant["id"], boosted_until.isoformat(timespec="seconds"), cooldown_until.isoformat(timespec="seconds")),
    )
    touch_participant(conn, participant["id"])
    conn.commit()
    payload = lobby_boost_state(conn, participant["room_id"]).get(str(participant["id"]), {})
    conn.close()
    app.logger.info(
        "dvd_boost room_id=%s participant_id=%s duration=%s cooldown=%s",
        participant["room_id"], participant["id"], BOOST_DURATION_SECONDS, BOOST_COOLDOWN_SECONDS,
    )
    emit_room_event(participant["room_id"], "room:presence", {"participant_id": participant["id"], "boost": True})
    return jsonify({"ok": True, "boost": payload})


@app.post("/api/lobby/dvd-telemetry")
def lobby_dvd_telemetry():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    touch_participant(conn, participant["id"])
    conn.commit()
    conn.close()
    timestamp = datetime.now().timestamp()
    previous = DVD_TELEMETRY_SEEN.get(participant["id"], 0)
    if timestamp - previous < 8:
        return jsonify({"ok": True, "throttled": True}), 202
    DVD_TELEMETRY_SEEN[participant["id"]] = timestamp
    data = request.get_json(silent=True) or {}

    def metric(name, maximum):
        try:
            return max(0, min(maximum, int(float(data.get(name, 0)))))
        except (TypeError, ValueError):
            return 0

    app.logger.info(
        "dvd_metrics room_id=%s participant_id=%s participants=%s frames=%s collisions=%s dropped=%s max_frame_ms=%s max_correction_px=%s boost=%s",
        participant["room_id"], participant["id"], metric("participants", 500), metric("frames", 2000),
        metric("collisions", 100000), metric("dropped_frames", 10000), metric("max_frame_ms", 10000),
        metric("max_correction_px", 1000), bool(data.get("boost_active")),
    )
    return jsonify({"ok": True}), 202


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
    if current_activity and current_activity["type"] in {"duel", "flash_question"}:
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
    runtime = get_runtime(conn, participant["room_id"])
    activity = get_activity(conn, runtime["current_activity_id"])
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (participant["room_id"],)).fetchone()
    conn.commit()
    conn.close()
    if not activity or activity["type"] not in {"duel", "flash_question"}:
        return redirect(url_for("quiz") if activity and activity["type"] == "quiz" else url_for("lobby"))
    return render_template(
        "activity.html", room=room, participant_name=participant["display_name"], activity_type=activity["type"],
    )


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


@app.get("/api/flash-question/current")
def current_flash_question():
    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    touch_participant(conn, participant["id"])
    activity = get_open_flash_question(conn, participant["room_id"])
    completed_early = complete_flash_question_if_all_answered(conn, activity)
    if completed_early:
        activity = get_activity(conn, activity["id"])
    auto_closed = finish_flash_question_if_expired(conn, activity)
    if auto_closed:
        activity = None
    payload = serialize_flash_question(conn, activity, participant["id"])
    runtime = get_runtime(conn, participant["room_id"])
    next_activity = get_activity(conn, runtime["current_activity_id"])
    conn.commit()
    conn.close()
    if auto_closed:
        emit_room_state(participant["room_id"])
    elif completed_early:
        emit_room_event(participant["room_id"], "room:flash_question_updated")
    return jsonify({
        "flash_question": payload,
        "activity_type": next_activity["type"] if next_activity else None,
    })


@app.post("/api/flash-question/answer")
def answer_flash_question():
    data = request.get_json(silent=True) or {}
    try:
        selected_index = int(data.get("selected_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "Оберіть варіант відповіді."}), 400

    conn = get_db()
    participant = current_participant(conn)
    if not participant:
        conn.close()
        return jsonify({"error": "No active session"}), 401
    touch_participant(conn, participant["id"])
    activity = get_open_flash_question(conn, participant["room_id"])
    if not activity:
        conn.close()
        return jsonify({"error": "Flash Question уже завершено."}), 409
    config = json.loads(activity["config_json"] or "{}")
    answers = config.get("answers", [])
    if not 0 <= selected_index < len(answers):
        conn.close()
        return jsonify({"error": "Некоректний варіант відповіді."}), 400
    if datetime.fromisoformat(config["ends_at"]) <= datetime.now():
        conn.close()
        return jsonify({"error": "Час на відповідь завершився."}), 409
    existing = conn.execute(
        "SELECT 1 FROM flash_question_answers WHERE activity_id = ? AND participant_id = ?",
        (activity["id"], participant["id"]),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Відповідь уже зарахована."}), 409
    conn.execute(
        """
        INSERT INTO flash_question_answers (activity_id, participant_id, selected_index, answered_at)
        VALUES (?, ?, ?, ?)
        """,
        (activity["id"], participant["id"], selected_index, now_iso()),
    )
    completed_early = complete_flash_question_if_all_answered(conn, activity)
    if completed_early:
        activity = get_activity(conn, activity["id"])
    payload = serialize_flash_question(conn, activity, participant["id"])
    conn.commit()
    conn.close()
    emit_room_event(participant["room_id"], "room:flash_question_updated")
    return jsonify({"flash_question": payload})


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
    if current_activity and current_activity["type"] in {"duel", "flash_question"}:
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
        (
            room["id"],
            json.dumps({
                "resume_activity_id": quiz_activity["id"],
                "selected_participant_ids": [participant["id"] for participant in selected],
            }),
            now_iso(),
        ),
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


@app.get("/api/admin/flash-question")
def admin_flash_question():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    activity = get_open_flash_question(conn, room["id"])
    completed_early = complete_flash_question_if_all_answered(conn, activity)
    if completed_early:
        activity = get_activity(conn, activity["id"])
    auto_closed = finish_flash_question_if_expired(conn, activity)
    if auto_closed:
        activity = None
    payload = serialize_flash_question(conn, activity, is_host=True)
    conn.commit()
    conn.close()
    if auto_closed:
        emit_room_state(room["id"])
    elif completed_early:
        emit_room_event(room["id"], "room:flash_question_updated")
    return jsonify({"flash_question": payload})


@app.post("/api/admin/flash-question")
def start_flash_question():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()
    answers = data.get("answers")
    try:
        correct_index = int(data.get("correct_index"))
    except (TypeError, ValueError):
        correct_index = -1
    try:
        duration_seconds = int(data.get("duration_seconds", FLASH_QUESTION_DEFAULT_SECONDS))
    except (TypeError, ValueError):
        return jsonify({"error": "Вкажіть час на відповідь у секундах."}), 400
    if not question or len(question) > 1000 or not isinstance(answers, list):
        return jsonify({"error": "Додайте питання та варіанти відповідей."}), 400
    answers = [str(answer).strip()[:240] for answer in answers if str(answer).strip()]
    if not 2 <= len(answers) <= 4 or not 0 <= correct_index < len(answers):
        return jsonify({"error": "Потрібно 2–4 варіанти й одна правильна відповідь."}), 400
    if not FLASH_QUESTION_MIN_SECONDS <= duration_seconds <= FLASH_QUESTION_MAX_SECONDS:
        return jsonify({
            "error": f"Час Flash Question має бути від {FLASH_QUESTION_MIN_SECONDS} до {FLASH_QUESTION_MAX_SECONDS} секунд."
        }), 400

    conn = get_db()
    runtime = get_runtime(conn, room["id"])
    quiz_activity = get_activity(conn, runtime["current_activity_id"])
    if not quiz_activity or quiz_activity["type"] != "quiz" or quiz_activity["status"] != "active":
        conn.close()
        return jsonify({"error": "Flash Question доступне лише під час активного квізу."}), 409
    online_threshold = datetime.now() - timedelta(seconds=60)
    participant_rows = conn.execute(
        "SELECT id, last_seen_at FROM room_participants WHERE room_id = ? AND left_at IS NULL ORDER BY id",
        (room["id"],),
    ).fetchall()
    target_participant_ids = [
        row["id"] for row in participant_rows
        if datetime.fromisoformat(row["last_seen_at"]) >= online_threshold
    ]
    started_at = datetime.now()
    starts_at = started_at + timedelta(seconds=FLASH_QUESTION_INTRO_SECONDS)
    ends_at = starts_at + timedelta(seconds=duration_seconds)
    closes_at = ends_at + timedelta(seconds=FLASH_QUESTION_CLOSE_DELAY_SECONDS)
    conn.execute(
        "UPDATE activities SET status = 'paused', paused_at = ? WHERE id = ?",
        (started_at.isoformat(timespec="seconds"), quiz_activity["id"]),
    )
    activity_id = conn.insert_and_get_id(
        """
        INSERT INTO activities (room_id, type, status, config_json, started_at)
        VALUES (?, 'flash_question', 'active', ?, ?)
        """,
        (
            room["id"],
            json.dumps({
                "resume_activity_id": quiz_activity["id"], "question": question,
                "answers": answers, "correct_index": correct_index,
                "duration_seconds": duration_seconds,
                "target_participant_ids": target_participant_ids,
                "starts_at": starts_at.isoformat(timespec="seconds"),
                "ends_at": ends_at.isoformat(timespec="seconds"),
                "closes_at": closes_at.isoformat(timespec="seconds"),
            }, ensure_ascii=False),
            started_at.isoformat(timespec="seconds"),
        ),
    )
    set_runtime(conn, room["id"], activity_id, "active")
    conn.commit()
    payload = serialize_flash_question(conn, get_activity(conn, activity_id), is_host=True)
    conn.close()
    emit_room_state(room["id"])
    emit_room_event(room["id"], "room:flash_question_updated")
    return jsonify({"flash_question": payload}), 201


@app.post("/api/admin/flash-question/close")
def close_flash_question():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    activity = get_open_flash_question(conn, room["id"])
    if not activity:
        conn.close()
        return jsonify({"error": "Немає активного Flash Question."}), 409
    finish_flash_question_activity(conn, activity)
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
