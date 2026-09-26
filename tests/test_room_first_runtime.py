import json
import tempfile
import unittest
from pathlib import Path

import app as server


class RoomFirstRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_url = server.DATABASE_URL
        self.original_db_path = server.DB_PATH
        server.DATABASE_URL = f"sqlite:///{Path(self.temporary_directory.name, 'runtime.sqlite3').as_posix()}"
        server.DB_PATH = Path(self.temporary_directory.name, "runtime.sqlite3")
        server.app.config["TESTING"] = True
        server.init_db()

    def tearDown(self):
        server.DATABASE_URL = self.original_database_url
        server.DB_PATH = self.original_db_path
        self.temporary_directory.cleanup()

    def test_quiz_attempt_is_created_on_start_and_duel_pauses_it(self):
        host = server.app.test_client()
        self.assertEqual(host.post("/rooms").status_code, 302)
        with host.session_transaction() as host_session:
            room_id = host_session["host_room_id"]

        conn = server.get_db()
        room_code = conn.execute("SELECT code FROM rooms WHERE id = ?", (room_id,)).fetchone()["code"]
        conn.close()

        first = server.app.test_client()
        second = server.app.test_client()
        self.assertEqual(first.post("/join", data={"name": "Оля", "code": room_code}).status_code, 302)
        self.assertEqual(second.post("/join", data={"name": "Макс", "code": room_code}).status_code, 302)

        self.assertEqual(host.post("/api/lobby/start", json={"mode": "self_paced"}).status_code, 200)

        conn = server.get_db()
        runtime = server.get_runtime(conn, room_id)
        activity = server.get_activity(conn, runtime["current_activity_id"])
        attempts = conn.execute("SELECT * FROM quiz_attempts WHERE activity_id = ? ORDER BY id", (activity["id"],)).fetchall()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(
            json.loads(attempts[0]["question_order_json"]),
            [question["id"] for question in server.activity_questions(activity)],
        )
        first_attempt = attempts[0]
        question = server.activity_question_map(activity)[json.loads(first_attempt["question_order_json"])[0]]
        conn.close()

        answered = first.post(
            "/api/answer",
            json={"question_id": question["id"], "selected_answers": question["correct"], "response_time": 1},
        )
        self.assertEqual(answered.status_code, 200)

        self.assertEqual(host.post("/api/admin/roulette", json={"question": "Поясніть відповідь"}).status_code, 201)

        conn = server.get_db()
        attempt = server.get_active_attempt(conn, first_attempt["participant_id"], room_id)
        activity = server.get_activity(conn, attempt["activity_id"])
        next_question = server.activity_question_map(activity)[json.loads(attempt["question_order_json"])[attempt["current_question"]]]
        conn.close()
        paused = first.post(
            "/api/answer",
            json={"question_id": next_question["id"], "selected_answers": next_question["correct"], "response_time": 1},
        )
        self.assertEqual(paused.status_code, 409)
        self.assertEqual(paused.get_json()["code"], "activity_paused")

        self.assertEqual(host.post("/api/admin/roulette/close").status_code, 200)
        self.assertEqual(host.post("/admin/logout").status_code, 302)

        conn = server.get_db()
        runtime = server.get_runtime(conn, room_id)
        resumed_quiz = server.get_activity(conn, runtime["current_activity_id"])
        conn.close()
        self.assertEqual((resumed_quiz["type"], resumed_quiz["status"]), ("quiz", "active"))

    def test_presence_uses_heartbeat_and_not_just_left_at(self):
        host = server.app.test_client()
        host.post("/rooms")
        with host.session_transaction() as host_session:
            room_id = host_session["host_room_id"]
        conn = server.get_db()
        room_code = conn.execute("SELECT code FROM rooms WHERE id = ?", (room_id,)).fetchone()["code"]
        conn.close()

        participant = server.app.test_client()
        participant.post("/join", data={"name": "Іра", "code": room_code})
        self.assertEqual(participant.post("/api/presence/heartbeat").status_code, 200)

        with participant.session_transaction() as participant_session:
            participant_id = participant_session["participant_id"]
        conn = server.get_db()
        conn.execute(
            "UPDATE room_participants SET last_seen_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00", participant_id),
        )
        conn.commit()
        conn.close()

        state = host.get("/api/lobby").get_json()
        current = next(item for item in state["participants"] if item["id"] == participant_id)
        self.assertEqual(current["presence_state"], "away")

    def test_completed_participant_can_return_to_lobby_while_host_stays_on_live_control(self):
        host = server.app.test_client()
        host.post("/rooms")
        with host.session_transaction() as host_session:
            room_id = host_session["host_room_id"]

        conn = server.get_db()
        room_code = conn.execute("SELECT code FROM rooms WHERE id = ?", (room_id,)).fetchone()["code"]
        conn.close()

        participant = server.app.test_client()
        participant.post("/join", data={"name": "Alex", "code": room_code})
        self.assertEqual(host.post("/api/lobby/start", json={"mode": "self_paced"}).status_code, 200)

        self.assertTrue(host.get("/lobby").location.endswith("/admin"))
        self.assertTrue(host.get("/lobby/host").location.endswith("/admin"))

        conn = server.get_db()
        runtime = server.get_runtime(conn, room_id)
        activity = server.get_activity(conn, runtime["current_activity_id"])
        questions = server.activity_questions(activity)
        conn.close()
        for question in questions:
            response = participant.post(
                "/api/answer",
                json={"question_id": question["id"], "selected_answers": question["correct"], "response_time": 1},
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(host.post("/api/admin/return-to-lobby").status_code, 200)
        self.assertEqual(host.get("/lobby/host").status_code, 200)
        self.assertEqual(participant.get("/result").status_code, 200)
        self.assertEqual(participant.get("/lobby").status_code, 200)

    def test_room_socket_broadcasts_activity_start_without_polling(self):
        host = server.app.test_client()
        host.post("/rooms")
        with host.session_transaction() as host_session:
            room_id = host_session["host_room_id"]

        conn = server.get_db()
        room_code = conn.execute("SELECT code FROM rooms WHERE id = ?", (room_id,)).fetchone()["code"]
        conn.close()

        participant = server.app.test_client()
        participant.post("/join", data={"name": "Socket participant", "code": room_code})
        client = server.socketio.test_client(server.app, flask_test_client=participant)
        self.assertTrue(client.is_connected())
        client.get_received()

        self.assertEqual(host.post("/api/lobby/start", json={"mode": "self_paced"}).status_code, 200)
        events = client.get_received()
        states = [event["args"][0] for event in events if event["name"] == "room:state"]
        self.assertTrue(any(state["activity_type"] == "quiz" for state in states))
        client.disconnect()

    def test_participant_can_keep_a_random_avatar_and_change_its_parts(self):
        host = server.app.test_client()
        host.post("/rooms")
        with host.session_transaction() as host_session:
            room_id = host_session["host_room_id"]
        conn = server.get_db()
        room_code = conn.execute("SELECT code FROM rooms WHERE id = ?", (room_id,)).fetchone()["code"]
        conn.close()

        participant = server.app.test_client()
        self.assertEqual(participant.post("/join", data={"name": "Avatar player", "code": room_code}).status_code, 302)
        state = participant.get("/api/lobby").get_json()
        current = next(item for item in state["participants"] if item["id"] == state["viewer_id"])
        self.assertIn(current["appearance"]["avatar"], server.AVATAR_OPTIONS)
        self.assertIn(current["appearance"]["headwear"], server.HEADWEAR_OPTIONS)

        updated = participant.post(
            "/api/profile/avatar",
            json={"appearance": {"avatar": "avatar-4", "headwear": "headwear-2"}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["appearance"], {"avatar": "avatar-4", "headwear": "headwear-2"})

        without_headwear = participant.post(
            "/api/profile/avatar",
            json={"appearance": {"avatar": "avatar-4", "headwear": None}},
        )
        self.assertEqual(without_headwear.status_code, 200)
        self.assertEqual(without_headwear.get_json()["appearance"], {"avatar": "avatar-4", "headwear": None})

        invalid = participant.post(
            "/api/profile/avatar",
            json={"appearance": {"avatar": "not-an-asset", "headwear": "headwear-2"}},
        )
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
