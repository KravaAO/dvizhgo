import json
import random
from datetime import datetime, timedelta

from flask import (
    jsonify, redirect, render_template,
    request, session, url_for
)
from quiz_app import create_app
from quiz_app.config import settings
from quiz_app.database import connect_database, initialize_database
from quiz_app.rooms import (
    add_participant,
    create_room,
    get_host_room as find_host_room,
    get_participant as find_participant,
    get_room_by_code,
)

BASE_DIR = settings.base_dir
DB_PATH = settings.sqlite_path
DATABASE_URL = settings.database_url
QUESTIONS_PATH = BASE_DIR / "questions.json"

app = create_app()

ADMIN_PASSWORD = settings.admin_password
SHUFFLE_ANSWERS = settings.shuffle_answers
SHUFFLE_QUESTIONS = settings.shuffle_questions


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


def get_participant(participant_id):
    conn = get_db()
    row = find_participant(conn, participant_id, session.get("room_id"))
    conn.close()
    return row


def get_current_host_room():
    conn = get_db()
    room = find_host_room(conn, session.get("host_room_id"), session.get("host_access_token"))
    conn.close()
    return room


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


def get_open_roulette(conn, room_id):
    return conn.execute(
        """
        SELECT * FROM roulette_rounds
        WHERE room_id = ? AND status != 'closed'
        ORDER BY id DESC
        LIMIT 1
        """,
        (room_id,),
    ).fetchone()


def clear_room_runtime(conn, room_id):
    """Remove temporary run data while keeping the room and its quiz library."""
    round_ids = "SELECT id FROM roulette_rounds WHERE room_id = ?"
    participant_ids = "SELECT id FROM students WHERE room_id = ?"
    conn.execute(f"DELETE FROM roulette_votes WHERE round_id IN ({round_ids})", (room_id,))
    conn.execute(f"DELETE FROM roulette_participants WHERE round_id IN ({round_ids})", (room_id,))
    conn.execute("DELETE FROM roulette_rounds WHERE room_id = ?", (room_id,))
    conn.execute(f"DELETE FROM answers WHERE student_id IN ({participant_ids})", (room_id,))
    conn.execute("DELETE FROM lobby_boosts WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM students WHERE room_id = ?", (room_id,))


def serialize_roulette(conn, round_row, viewer_id=None):
    if not round_row:
        return None

    participant_rows = conn.execute(
        """
        SELECT p.student_id, s.name, p.answer_text, p.answered_at,
               COUNT(v.voter_id) AS votes
        FROM roulette_participants p
        JOIN students s ON s.id = p.student_id
        LEFT JOIN roulette_votes v
            ON v.round_id = p.round_id AND v.choice_student_id = p.student_id
        WHERE p.round_id = ?
        GROUP BY p.student_id, s.name, p.answer_text, p.answered_at
        ORDER BY p.student_id
        """,
        (round_row["id"],),
    ).fetchall()

    participants = [dict(row) for row in participant_rows]
    participant_ids = {participant["student_id"] for participant in participants}
    user_vote = None
    if viewer_id:
        vote = conn.execute(
            """
            SELECT choice_student_id FROM roulette_votes
            WHERE round_id = ? AND voter_id = ?
            """,
            (round_row["id"], viewer_id),
        ).fetchone()
        user_vote = vote["choice_student_id"] if vote else None

    return {
        "id": round_row["id"],
        "question": round_row["question"],
        "candidate_pool": json.loads(round_row["candidate_pool"]),
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
    participant_id = session.get("participant_id")
    if participant_id:
        participant = get_participant(participant_id)
        if participant and not participant["finished_at"]:
            return redirect(url_for("quiz"))
    room = get_current_host_room()
    if room:
        return redirect(url_for("host_lobby" if room["status"] == "lobby" else "admin"))
    return render_template("index.html")


@app.post("/rooms")
def create_new_room():
    conn = get_db()
    room, access_token = create_room(conn)
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
    question_ids = [question["id"] for question in load_room_questions(conn, room["id"])]
    if SHUFFLE_QUESTIONS:
        random.shuffle(question_ids)
    participant_id = add_participant(conn, room["id"], name, question_ids)
    conn.close()

    session.clear()
    session["participant_id"] = participant_id
    session["room_id"] = room["id"]
    session["sound_enabled"] = True
    return redirect(url_for("lobby"))


@app.get("/lobby")
def lobby():
    if get_current_host_room():
        return redirect(url_for("host_lobby"))
    participant_id = session.get("participant_id")
    participant = get_participant(participant_id) if participant_id else None
    if not participant:
        return redirect(url_for("index"))
    room = get_room(participant["room_id"])
    if not room:
        session.clear()
        return redirect(url_for("index"))
    if room["status"] == "active":
        return redirect(url_for("quiz"))
    return render_template("lobby.html", room=room, participant_name=participant["name"])


@app.get("/lobby/host")
def host_lobby():
    room = get_current_host_room()
    if not room:
        return redirect(url_for("index"))
    return render_template("host_lobby.html", room=room)


@app.get("/api/lobby")
def lobby_state():
    room_id = session.get("room_id")
    if not room_id:
        return jsonify({"error": "No active room"}), 401
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    participants = conn.execute(
        "SELECT id, name FROM students WHERE room_id = ? AND finished_at IS NULL AND left_at IS NULL ORDER BY started_at",
        (room_id,),
    ).fetchall()
    if not room:
        conn.close()
        return jsonify({"error": "Room not found"}), 404
    settings_json = json.loads(room["settings_json"] or "{}")
    now = datetime.now()
    boost_rows = conn.execute(
        "SELECT participant_id, boosted_until, cooldown_until FROM lobby_boosts WHERE room_id = ?",
        (room_id,),
    ).fetchall()
    conn.close()
    boosts = {}
    for boost in boost_rows:
        boosted_until = datetime.fromisoformat(boost["boosted_until"])
        cooldown_until = datetime.fromisoformat(boost["cooldown_until"])
        boosts[str(boost["participant_id"])] = {
            "active": boosted_until > now,
            "cooldown_seconds": max(0, round((cooldown_until - now).total_seconds())),
        }
    return jsonify({
        "status": room["status"], "participants": [dict(row) for row in participants],
        "mode": settings_json.get("mode", "self_paced"),
        "server_time": datetime.now().astimezone().isoformat(),
        "boosts": boosts,
        "boost_enabled": settings.lobby_boost_enabled,
        "viewer_id": session.get("participant_id"),
    })


@app.post("/api/lobby/boost")
def lobby_boost():
    if not settings.lobby_boost_enabled:
        return jsonify({"error": "Функцію boost тимчасово вимкнено."}), 404
    participant_id = session.get("participant_id")
    participant = get_participant(participant_id) if participant_id else None
    if not participant:
        return jsonify({"error": "Немає активної сесії."}), 401
    room = get_room(participant["room_id"])
    if not room or room["status"] != "lobby":
        return jsonify({"error": "Буст доступний лише в лобі."}), 409

    now = datetime.now()
    conn = get_db()
    boost = conn.execute(
        "SELECT cooldown_until FROM lobby_boosts WHERE room_id = ? AND participant_id = ?",
        (participant["room_id"], participant_id),
    ).fetchone()
    if boost:
        cooldown_until = datetime.fromisoformat(boost["cooldown_until"])
        if cooldown_until > now:
            conn.close()
            return jsonify({"error": "Буст ще перезаряджається.", "cooldown_seconds": round((cooldown_until - now).total_seconds())}), 429

    boosted_until = now + timedelta(seconds=5)
    cooldown_until = now + timedelta(seconds=15)
    conn.execute(
        "DELETE FROM lobby_boosts WHERE room_id = ? AND participant_id = ?",
        (participant["room_id"], participant_id),
    )
    conn.execute(
        "INSERT INTO lobby_boosts (room_id, participant_id, boosted_until, cooldown_until) VALUES (?, ?, ?, ?)",
        (participant["room_id"], participant_id, boosted_until.isoformat(), cooldown_until.isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "boost_seconds": 5, "cooldown_seconds": 15})


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
    questions = load_room_questions(conn, room["id"])
    if not questions:
        conn.close()
        return jsonify({"error": "Спочатку оберіть квіз із питаннями."}), 400
    conn.execute(
        "UPDATE rooms SET status = 'active', settings_json = ? WHERE id = ?",
        (json.dumps({"mode": mode}), room["id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/quiz")
def quiz():
    participant_id = session.get("participant_id")
    if not participant_id:
        return redirect(url_for("index"))

    participant = get_participant(participant_id)
    if not participant:
        session.clear()
        return redirect(url_for("index"))

    if participant["finished_at"]:
        return redirect(url_for("result"))

    room = get_room(participant["room_id"])
    if not room or room["status"] != "active":
        return redirect(url_for("lobby"))

    order = json.loads(participant["question_order"])
    index = participant["current_question"]
    if index >= len(order):
        return redirect(url_for("result"))

    qmap = get_question_map(participant["room_id"])
    question = qmap[order[index]]

    return render_template(
        "quiz.html",
        question=public_question(question),
        question_number=index + 1,
        total_questions=len(order),
        participant_name=participant["name"],
        room_title=room["title"],
    )


@app.post("/api/answer")
def answer():
    participant_id = session.get("participant_id")
    if not participant_id:
        return jsonify({"error": "No active session"}), 401

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

    participant = get_participant(participant_id)
    if not participant or participant["finished_at"]:
        return jsonify({"error": "Quiz is not active"}), 400

    room = get_room(participant["room_id"])
    if not room or room["status"] != "active":
        return jsonify({"error": "Квіз ще не розпочато."}), 409

    order = json.loads(participant["question_order"])
    current_index = participant["current_question"]
    if current_index >= len(order):
        return jsonify({"error": "Quiz already finished"}), 400

    expected_question_id = order[current_index]
    if question_id != expected_question_id:
        return jsonify({"error": "Question mismatch"}), 409

    qmap = get_question_map(participant["room_id"])
    question = qmap.get(question_id)
    if not question:
        return jsonify({"error": "Unknown question"}), 404

    correct = sorted(question["correct"])
    is_correct = selected == correct

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM answers WHERE student_id = ? AND question_id = ?",
        (participant_id, question_id),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Answer already submitted"}), 409

    conn.execute(
        """
        INSERT INTO answers
        (student_id, question_id, selected_answers, is_correct, response_time, answered_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            participant_id,
            question_id,
            json.dumps(selected),
            is_correct,
            response_time,
            now_iso(),
        ),
    )

    new_index = current_index + 1
    new_score = participant["score"] + int(is_correct)
    finished_at = now_iso() if new_index >= len(order) else None

    conn.execute(
        """
        UPDATE students
        SET current_question = ?, score = ?, finished_at = COALESCE(?, finished_at)
        WHERE id = ?
        """,
        (new_index, new_score, finished_at, participant_id),
    )
    conn.commit()
    conn.close()

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
    participant_id = session.get("participant_id")
    room_id = session.get("room_id")
    if not participant_id or not room_id:
        return jsonify({"error": "No active session"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn, room_id)
    payload = serialize_roulette(conn, round_row, participant_id)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/roulette/answer")
def roulette_answer():
    participant_id = session.get("participant_id")
    room_id = session.get("room_id")
    data = request.get_json(silent=True) or {}
    answer_text = (data.get("answer") or "").strip()
    if not participant_id or not room_id:
        return jsonify({"error": "No active session"}), 401
    if not answer_text or len(answer_text) > 1000:
        return jsonify({"error": "Answer must contain 1–1000 characters"}), 400

    conn = get_db()
    round_row = get_open_roulette(conn, room_id)
    if not round_row or round_row["status"] != "answering":
        conn.close()
        return jsonify({"error": "No active answering round"}), 409

    participant = conn.execute(
        """
        SELECT answer_text FROM roulette_participants
        WHERE round_id = ? AND student_id = ?
        """,
        (round_row["id"], participant_id),
    ).fetchone()
    if not participant or participant["answer_text"]:
        conn.close()
        return jsonify({"error": "You cannot submit an answer for this round"}), 403

    conn.execute(
        """
        UPDATE roulette_participants
        SET answer_text = ?, answered_at = ?
        WHERE round_id = ? AND student_id = ?
        """,
        (answer_text, now_iso(), round_row["id"], participant_id),
    )
    answered_count = conn.execute(
        """
        SELECT COUNT(*) AS count FROM roulette_participants
        WHERE round_id = ? AND answer_text IS NOT NULL
        """,
        (round_row["id"],),
    ).fetchone()["count"]
    if answered_count == 2:
        conn.execute(
            "UPDATE roulette_rounds SET status = 'voting' WHERE id = ?",
            (round_row["id"],),
        )
    conn.commit()
    round_row = get_open_roulette(conn, room_id)
    payload = serialize_roulette(conn, round_row, participant_id)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/roulette/vote")
def roulette_vote():
    participant_id = session.get("participant_id")
    room_id = session.get("room_id")
    data = request.get_json(silent=True) or {}
    choice_student_id = data.get("choice_student_id")
    if not participant_id or not room_id:
        return jsonify({"error": "No active session"}), 401
    try:
        choice_student_id = int(choice_student_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid choice"}), 400

    conn = get_db()
    round_row = get_open_roulette(conn, room_id)
    if not round_row or round_row["status"] != "voting":
        conn.close()
        return jsonify({"error": "Voting is not active"}), 409

    participants = conn.execute(
        "SELECT student_id FROM roulette_participants WHERE round_id = ?",
        (round_row["id"],),
    ).fetchall()
    participant_ids = {row["student_id"] for row in participants}
    if participant_id in participant_ids or choice_student_id not in participant_ids:
        conn.close()
        return jsonify({"error": "You cannot vote for this participant"}), 403

    existing_vote = conn.execute(
        "SELECT 1 FROM roulette_votes WHERE round_id = ? AND voter_id = ?",
        (round_row["id"], participant_id),
    ).fetchone()
    if existing_vote:
        conn.close()
        return jsonify({"error": "You have already liked an answer"}), 409

    conn.execute(
        """
        INSERT INTO roulette_votes (round_id, voter_id, choice_student_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (round_row["id"], participant_id, choice_student_id, now_iso()),
    )
    conn.commit()
    payload = serialize_roulette(conn, round_row, participant_id)
    conn.close()
    return jsonify({"round": payload})


@app.get("/result")
def result():
    participant_id = session.get("participant_id")
    if not participant_id:
        return redirect(url_for("index"))

    participant = get_participant(participant_id)
    if not participant:
        return redirect(url_for("index"))

    total = participant["total_questions"]
    score = participant["score"]
    percent = round((score / total) * 100) if total else 0

    conn = get_db()
    rows = conn.execute(
        "SELECT response_time FROM answers WHERE student_id = ?",
        (participant_id,),
    ).fetchall()
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
    participant_id = session.get("participant_id")
    room_id = session.get("room_id")
    if participant_id and room_id:
        conn = get_db()
        conn.execute(
            "UPDATE students SET left_at = ? WHERE id = ? AND room_id = ? AND finished_at IS NULL",
            (now_iso(), participant_id, room_id),
        )
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for("index"))


@app.post("/retry")
def retry_quiz():
    participant_id = session.get("participant_id")
    participant = get_participant(participant_id) if participant_id else None
    if not participant or not participant["finished_at"]:
        return redirect(url_for("index"))

    room_id = participant["room_id"]
    question_ids = json.loads(participant["question_order"])
    conn = get_db()
    room = conn.execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not room or room["status"] == "finished":
        conn.close()
        session.clear()
        return redirect(url_for("index"))
    new_participant_id = add_participant(conn, room_id, participant["name"], question_ids)
    conn.close()

    session.clear()
    session["participant_id"] = new_participant_id
    session["room_id"] = room_id
    session["sound_enabled"] = True
    return redirect(url_for("quiz"))


@app.get("/admin")
def admin():
    room = get_current_host_room()
    if not room:
        return redirect(url_for("index"))
    return render_template("admin.html", authenticated=True, room=room)


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
    started = conn.execute("SELECT 1 FROM students WHERE room_id = ? LIMIT 1", (room["id"],)).fetchone()
    quiz = conn.execute("SELECT id FROM quizzes WHERE id = ? AND room_id = ?", (quiz_id, room["id"])).fetchone()
    if started:
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
    started = conn.execute("SELECT 1 FROM students WHERE room_id = ? LIMIT 1", (room["id"],)).fetchone()
    if started:
        conn.close()
        return jsonify({"error": "Спершу очистіть результати кімнати, щоб змінити квіз."}), 409
    conn.execute("UPDATE rooms SET active_quiz_id = NULL WHERE id = ?", (room["id"],))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.post("/admin/logout")
def admin_logout():
    room = get_current_host_room()
    if room:
        conn = get_db()
        clear_room_runtime(conn, room["id"])
        conn.execute("UPDATE rooms SET status = 'lobby' WHERE id = ?", (room["id"],))
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for("index"))


@app.get("/api/admin/roulette")
def admin_roulette():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn, room["id"])
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
    active_participants = conn.execute(
        """
        SELECT id, name FROM students
        WHERE room_id = ? AND finished_at IS NULL AND left_at IS NULL
        ORDER BY id
        """,
        (room["id"],),
    ).fetchall()
    if len(active_participants) < 2:
        conn.close()
        return jsonify({"error": "At least two active participants are needed"}), 400

    selected = random.sample(active_participants, 2)
    conn.execute("UPDATE roulette_rounds SET status = 'closed' WHERE room_id = ? AND status != 'closed'", (room["id"],))
    round_id = conn.insert_and_get_id(
        """
        INSERT INTO roulette_rounds (room_id, question, candidate_pool, status, created_at)
        VALUES (?, ?, ?, 'answering', ?)
        """,
        (room["id"], question, json.dumps([participant["name"] for participant in active_participants]), now_iso()),
    )
    conn.executemany(
        """
        INSERT INTO roulette_participants (round_id, student_id)
        VALUES (?, ?)
        """,
        [(round_id, participant["id"]) for participant in selected],
    )
    conn.commit()
    round_row = get_open_roulette(conn, room["id"])
    payload = serialize_roulette(conn, round_row)
    conn.close()
    return jsonify({"round": payload}), 201


@app.post("/api/admin/roulette/close")
def close_roulette():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn, room["id"])
    if not round_row:
        conn.close()
        return jsonify({"error": "No active roulette round"}), 409

    conn.execute(
        "UPDATE roulette_rounds SET status = 'closed' WHERE id = ?",
        (round_row["id"],),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/admin/results")
def admin_results():
    room = get_current_host_room()
    if not room:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    rows = conn.execute(
        """
        SELECT
            s.*,
            COUNT(a.id) AS answered,
            COALESCE(SUM(a.response_time), 0) AS total_time
        FROM students s
        LEFT JOIN answers a ON a.student_id = s.id
        WHERE s.room_id = ?
        GROUP BY s.id
        ORDER BY s.started_at DESC
        """,
        (room["id"],),
    ).fetchall()
    conn.close()

    students = []
    for row in rows:
        total = row["total_questions"]
        percent = round((row["score"] / total) * 100) if total else 0
        students.append(
            {
                "id": row["id"],
                "name": row["name"],
                "answered": row["answered"],
                "total": total,
                "score": row["score"],
                "percent": percent,
                "finished": bool(row["finished_at"]),
                "total_time": round(row["total_time"], 1),
                "started_at": row["started_at"],
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
    student = conn.execute("SELECT * FROM students WHERE id = ? AND room_id = ?", (student_id, room["id"])).fetchone()
    answers = conn.execute(
        """
        SELECT * FROM answers
        WHERE student_id = ?
        ORDER BY id
        """,
        (student_id,),
    ).fetchall()
    conn.close()

    if not student:
        return jsonify({"error": "Student not found"}), 404

    qmap = get_question_map(room["id"])
    details = []
    for answer in answers:
        q = qmap.get(answer["question_id"])
        if not q:
            continue
        selected_indexes = json.loads(answer["selected_answers"])
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
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
