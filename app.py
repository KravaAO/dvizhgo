import json
import random
from datetime import datetime

from flask import (
    jsonify, redirect, render_template,
    request, session, url_for
)
from quiz_app import create_app
from quiz_app.config import settings
from quiz_app.database import connect_database, initialize_database

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


def get_question_map():
    return {q["id"]: q for q in load_questions()}


def get_student(student_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    return row


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


def get_open_roulette(conn):
    return conn.execute(
        """
        SELECT * FROM roulette_rounds
        WHERE status != 'closed'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


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
    student_id = session.get("student_id")
    if student_id:
        student = get_student(student_id)
        if student and not student["finished_at"]:
            return redirect(url_for("quiz"))
    return render_template("index.html")


@app.post("/start")
def start():
    name = (request.form.get("name") or "").strip()
    if not name:
        return render_template("index.html", error="Введи ім'я перед стартом."), 400

    questions = load_questions()
    order = [q["id"] for q in questions]
    if SHUFFLE_QUESTIONS:
        random.shuffle(order)

    conn = get_db()
    student_id = conn.insert_and_get_id(
        """
        INSERT INTO students (name, started_at, total_questions, question_order)
        VALUES (?, ?, ?, ?)
        """,
        (name[:80], now_iso(), len(order), json.dumps(order)),
    )
    conn.commit()
    conn.close()

    session.clear()
    session["student_id"] = student_id
    session["sound_enabled"] = True
    return redirect(url_for("quiz"))


@app.get("/quiz")
def quiz():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("index"))

    student = get_student(student_id)
    if not student:
        session.clear()
        return redirect(url_for("index"))

    if student["finished_at"]:
        return redirect(url_for("result"))

    order = json.loads(student["question_order"])
    index = student["current_question"]
    if index >= len(order):
        return redirect(url_for("result"))

    qmap = get_question_map()
    question = qmap[order[index]]

    return render_template(
        "quiz.html",
        question=public_question(question),
        question_number=index + 1,
        total_questions=len(order),
        student_name=student["name"],
    )


@app.post("/api/answer")
def answer():
    student_id = session.get("student_id")
    if not student_id:
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

    student = get_student(student_id)
    if not student or student["finished_at"]:
        return jsonify({"error": "Quiz is not active"}), 400

    order = json.loads(student["question_order"])
    current_index = student["current_question"]
    if current_index >= len(order):
        return jsonify({"error": "Quiz already finished"}), 400

    expected_question_id = order[current_index]
    if question_id != expected_question_id:
        return jsonify({"error": "Question mismatch"}), 409

    qmap = get_question_map()
    question = qmap.get(question_id)
    if not question:
        return jsonify({"error": "Unknown question"}), 404

    correct = sorted(question["correct"])
    is_correct = selected == correct

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM answers WHERE student_id = ? AND question_id = ?",
        (student_id, question_id),
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
            student_id,
            question_id,
            json.dumps(selected),
            is_correct,
            response_time,
            now_iso(),
        ),
    )

    new_index = current_index + 1
    new_score = student["score"] + int(is_correct)
    finished_at = now_iso() if new_index >= len(order) else None

    conn.execute(
        """
        UPDATE students
        SET current_question = ?, score = ?, finished_at = COALESCE(?, finished_at)
        WHERE id = ?
        """,
        (new_index, new_score, finished_at, student_id),
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
    student_id = session.get("student_id")
    if not student_id:
        return jsonify({"error": "No active session"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn)
    payload = serialize_roulette(conn, round_row, student_id)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/roulette/answer")
def roulette_answer():
    student_id = session.get("student_id")
    data = request.get_json(silent=True) or {}
    answer_text = (data.get("answer") or "").strip()
    if not student_id:
        return jsonify({"error": "No active session"}), 401
    if not answer_text or len(answer_text) > 1000:
        return jsonify({"error": "Answer must contain 1–1000 characters"}), 400

    conn = get_db()
    round_row = get_open_roulette(conn)
    if not round_row or round_row["status"] != "answering":
        conn.close()
        return jsonify({"error": "No active answering round"}), 409

    participant = conn.execute(
        """
        SELECT answer_text FROM roulette_participants
        WHERE round_id = ? AND student_id = ?
        """,
        (round_row["id"], student_id),
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
        (answer_text, now_iso(), round_row["id"], student_id),
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
    round_row = get_open_roulette(conn)
    payload = serialize_roulette(conn, round_row, student_id)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/roulette/vote")
def roulette_vote():
    student_id = session.get("student_id")
    data = request.get_json(silent=True) or {}
    choice_student_id = data.get("choice_student_id")
    if not student_id:
        return jsonify({"error": "No active session"}), 401
    try:
        choice_student_id = int(choice_student_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid choice"}), 400

    conn = get_db()
    round_row = get_open_roulette(conn)
    if not round_row or round_row["status"] != "voting":
        conn.close()
        return jsonify({"error": "Voting is not active"}), 409

    participants = conn.execute(
        "SELECT student_id FROM roulette_participants WHERE round_id = ?",
        (round_row["id"],),
    ).fetchall()
    participant_ids = {row["student_id"] for row in participants}
    if student_id in participant_ids or choice_student_id not in participant_ids:
        conn.close()
        return jsonify({"error": "You cannot vote for this participant"}), 403

    existing_vote = conn.execute(
        "SELECT 1 FROM roulette_votes WHERE round_id = ? AND voter_id = ?",
        (round_row["id"], student_id),
    ).fetchone()
    if existing_vote:
        conn.close()
        return jsonify({"error": "You have already liked an answer"}), 409

    conn.execute(
        """
        INSERT INTO roulette_votes (round_id, voter_id, choice_student_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (round_row["id"], student_id, choice_student_id, now_iso()),
    )
    conn.commit()
    payload = serialize_roulette(conn, round_row, student_id)
    conn.close()
    return jsonify({"round": payload})


@app.get("/result")
def result():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("index"))

    student = get_student(student_id)
    if not student:
        return redirect(url_for("index"))

    total = student["total_questions"]
    score = student["score"]
    percent = round((score / total) * 100) if total else 0

    conn = get_db()
    rows = conn.execute(
        "SELECT response_time FROM answers WHERE student_id = ?",
        (student_id,),
    ).fetchall()
    conn.close()
    total_seconds = int(sum(row["response_time"] for row in rows))
    minutes, seconds = divmod(total_seconds, 60)

    return render_template(
        "result.html",
        student=student,
        score=score,
        total=total,
        percent=percent,
        rank=compute_rank(percent),
        total_time=f"{minutes:02d}:{seconds:02d}",
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(url_for("admin"))
        return render_template("admin.html", authenticated=False, error="Невірний пароль.")

    return render_template(
        "admin.html",
        authenticated=bool(session.get("admin_authenticated")),
    )


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin"))


@app.get("/api/admin/roulette")
def admin_roulette():
    if not session.get("admin_authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn)
    payload = serialize_roulette(conn, round_row)
    conn.close()
    return jsonify({"round": payload})


@app.post("/api/admin/roulette")
def start_roulette():
    if not session.get("admin_authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question or len(question) > 1000:
        return jsonify({"error": "Question must contain 1–1000 characters"}), 400

    conn = get_db()
    active_students = conn.execute(
        """
        SELECT id, name FROM students
        WHERE finished_at IS NULL
        ORDER BY id
        """
    ).fetchall()
    if len(active_students) < 2:
        conn.close()
        return jsonify({"error": "At least two active students are needed"}), 400

    selected = random.sample(active_students, 2)
    conn.execute("UPDATE roulette_rounds SET status = 'closed' WHERE status != 'closed'")
    round_id = conn.insert_and_get_id(
        """
        INSERT INTO roulette_rounds (question, candidate_pool, status, created_at)
        VALUES (?, ?, 'answering', ?)
        """,
        (question, json.dumps([student["name"] for student in active_students]), now_iso()),
    )
    conn.executemany(
        """
        INSERT INTO roulette_participants (round_id, student_id)
        VALUES (?, ?)
        """,
        [(round_id, student["id"]) for student in selected],
    )
    conn.commit()
    round_row = get_open_roulette(conn)
    payload = serialize_roulette(conn, round_row)
    conn.close()
    return jsonify({"round": payload}), 201


@app.post("/api/admin/roulette/close")
def close_roulette():
    if not session.get("admin_authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    round_row = get_open_roulette(conn)
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
    if not session.get("admin_authenticated"):
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
        GROUP BY s.id
        ORDER BY s.started_at DESC
        """
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
    if not session.get("admin_authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
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

    qmap = get_question_map()
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
    if not session.get("admin_authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    conn.execute("DELETE FROM roulette_votes")
    conn.execute("DELETE FROM roulette_participants")
    conn.execute("DELETE FROM roulette_rounds")
    conn.execute("DELETE FROM answers")
    conn.execute("DELETE FROM students")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
