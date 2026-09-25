"""Database boundary for local SQLite and production PostgreSQL.

Routes use the small connection adapter so existing query code is independent
from the DB-API placeholder syntax. PostgreSQL is selected with DATABASE_URL.
"""

import sqlite3
from pathlib import Path
from typing import Any, Iterable


POSTGRES_PREFIXES = ("postgres://", "postgresql://")


def is_postgres(database_url: str | None) -> bool:
    return bool(database_url and database_url.startswith(POSTGRES_PREFIXES))


def _query_for_driver(query: str, database_url: str | None) -> str:
    return query.replace("?", "%s") if is_postgres(database_url) else query


class DatabaseConnection:
    """Portable subset of a DB-API connection used by the application."""

    def __init__(self, connection: Any, database_url: str | None):
        self._connection = connection
        self._database_url = database_url

    def execute(self, query: str, params: Iterable[Any] = ()):
        return self._connection.execute(_query_for_driver(query, self._database_url), params)

    def executemany(self, query: str, params: Iterable[Iterable[Any]]):
        return self._connection.executemany(_query_for_driver(query, self._database_url), params)

    def commit(self):
        self._connection.commit()

    def close(self):
        self._connection.close()

    def insert_and_get_id(self, query: str, params: Iterable[Any]) -> int:
        if is_postgres(self._database_url):
            cursor = self.execute(f"{query.rstrip()} RETURNING id", params)
            return cursor.fetchone()["id"]
        cursor = self.execute(query, params)
        return cursor.lastrowid


def connect_database(database_url: str | None, sqlite_path: Path) -> DatabaseConnection:
    if is_postgres(database_url):
        try:
            from psycopg import connect
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("PostgreSQL requires the psycopg package") from error
        connection = connect(database_url, row_factory=dict_row)
        return DatabaseConnection(connection, database_url)

    path = sqlite_path
    if database_url and database_url.startswith("sqlite:///"):
        path = Path(database_url.removeprefix("sqlite:///"))
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return DatabaseConnection(connection, database_url)


SQLITE_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        current_question INTEGER NOT NULL DEFAULT 0,
        score INTEGER NOT NULL DEFAULT 0,
        total_questions INTEGER NOT NULL,
        question_order TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        selected_answers TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        response_time REAL NOT NULL,
        answered_at TEXT NOT NULL,
        UNIQUE(student_id, question_id),
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """,
)

POSTGRES_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS students (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        current_question INTEGER NOT NULL DEFAULT 0,
        score INTEGER NOT NULL DEFAULT 0,
        total_questions INTEGER NOT NULL,
        question_order TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS answers (
        id BIGSERIAL PRIMARY KEY,
        student_id BIGINT NOT NULL REFERENCES students(id),
        question_id INTEGER NOT NULL,
        selected_answers TEXT NOT NULL,
        is_correct BOOLEAN NOT NULL,
        response_time DOUBLE PRECISION NOT NULL,
        answered_at TEXT NOT NULL,
        UNIQUE(student_id, question_id)
    )
    """,
)

SQLITE_ROULETTE_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS roulette_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        candidate_pool TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'answering',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roulette_participants (
        round_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        answer_text TEXT,
        answered_at TEXT,
        PRIMARY KEY (round_id, student_id),
        FOREIGN KEY(round_id) REFERENCES roulette_rounds(id),
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roulette_votes (
        round_id INTEGER NOT NULL,
        voter_id INTEGER NOT NULL,
        choice_student_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (round_id, voter_id),
        FOREIGN KEY(round_id) REFERENCES roulette_rounds(id),
        FOREIGN KEY(voter_id) REFERENCES students(id),
        FOREIGN KEY(choice_student_id) REFERENCES students(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_answers_student_id ON answers(student_id)",
    "CREATE INDEX IF NOT EXISTS idx_students_active ON students(finished_at)",
    "CREATE INDEX IF NOT EXISTS idx_roulette_rounds_status ON roulette_rounds(status, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_roulette_votes_round_id ON roulette_votes(round_id)",
)

POSTGRES_ROULETTE_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS roulette_rounds (
        id BIGSERIAL PRIMARY KEY,
        question TEXT NOT NULL,
        candidate_pool TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'answering',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roulette_participants (
        round_id BIGINT NOT NULL REFERENCES roulette_rounds(id),
        student_id BIGINT NOT NULL REFERENCES students(id),
        answer_text TEXT,
        answered_at TEXT,
        PRIMARY KEY (round_id, student_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roulette_votes (
        round_id BIGINT NOT NULL REFERENCES roulette_rounds(id),
        voter_id BIGINT NOT NULL REFERENCES students(id),
        choice_student_id BIGINT NOT NULL REFERENCES students(id),
        created_at TEXT NOT NULL,
        PRIMARY KEY (round_id, voter_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_answers_student_id ON answers(student_id)",
    "CREATE INDEX IF NOT EXISTS idx_students_active ON students(finished_at)",
    "CREATE INDEX IF NOT EXISTS idx_roulette_rounds_status ON roulette_rounds(status, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_roulette_votes_round_id ON roulette_votes(round_id)",
)


def initialize_database(database_url: str | None, sqlite_path: Path) -> None:
    connection = connect_database(database_url, sqlite_path)
    try:
        schema = (
            POSTGRES_SCHEMA + POSTGRES_ROULETTE_SCHEMA
            if is_postgres(database_url)
            else SQLITE_SCHEMA + SQLITE_ROULETTE_SCHEMA
        )
        for statement in schema:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()
