import os
from dataclasses import dataclass
from pathlib import Path


def as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    database_url: str | None
    secret_key: str
    admin_password: str
    shuffle_answers: bool
    shuffle_questions: bool
    default_locale: str
    lobby_boost_enabled: bool

    @property
    def sqlite_path(self) -> Path:
        return self.base_dir / "quiz.db"

    @classmethod
    def from_environment(cls) -> "Settings":
        base_dir = Path(__file__).resolve().parent.parent
        return cls(
            base_dir=base_dir,
            database_url=os.getenv("DATABASE_URL") or None,
            secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"),
            admin_password=os.getenv("ADMIN_PASSWORD", "teacher123"),
            shuffle_answers=as_bool(os.getenv("SHUFFLE_ANSWERS"), True),
            shuffle_questions=as_bool(os.getenv("SHUFFLE_QUESTIONS"), False),
            default_locale=os.getenv("DEFAULT_LOCALE", "uk").strip().lower(),
            lobby_boost_enabled=as_bool(os.getenv("LOBBY_BOOST_ENABLED"), False),
        )


settings = Settings.from_environment()
