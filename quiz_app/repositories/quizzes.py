"""Database queries for a room's selected quiz."""

import json


class QuizRepository:
    def __init__(self, connection):
        self.connection = connection

    def selected_questions(self, room_id):
        room = self.connection.execute(
            "SELECT active_quiz_id FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if not room or not room["active_quiz_id"]:
            return None
        quiz = self.connection.execute(
            "SELECT questions_json FROM quizzes WHERE id = ? AND room_id = ?",
            (room["active_quiz_id"], room_id),
        ).fetchone()
        return json.loads(quiz["questions_json"]) if quiz else None

    def selected_title(self, room):
        if not room["active_quiz_id"]:
            return None
        quiz = self.connection.execute(
            "SELECT title FROM quizzes WHERE id = ? AND room_id = ?",
            (room["active_quiz_id"], room["id"]),
        ).fetchone()
        return quiz["title"] if quiz else None
