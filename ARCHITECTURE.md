# Архітектура масштабування

## Поточні межі

- `app.py` — HTTP-контролери та сумісний стартовий файл для локальної розробки.
- `quiz_app/config.py` — конфігурація лише через змінні середовища.
- `quiz_app/database.py` — єдиний адаптер до SQLite та PostgreSQL, ініціалізація схеми й різниця між `?` та `%s` у SQL.
- `templates/` і `static/` — лише інтерфейс; вони не містять правил збереження даних.

Локальний запуск без `DATABASE_URL` використовує SQLite у WAL-режимі. Для Docker і будь-якого багатокористувацького запуску обов'язковий PostgreSQL через `DATABASE_URL`.

## Контури в Docker

`web` — Flask/Gunicorn, stateless HTTP-процеси.

`db` — PostgreSQL з іменованим volume `postgres_data`.

Запуск:

```bash
copy .env.example .env
# замінити SECRET_KEY, ADMIN_PASSWORD і POSTGRES_PASSWORD у .env
docker compose up --build
```

## Наступний етап: WebSocket

WebSocket поки не реалізований. Коли він знадобиться, додається окремий realtime-шар без зміни контрактів БД:

1. Винести правила тесту й рулетки з HTTP-контролерів у `quiz_app/services/`.
2. Додати ASGI-процес (наприклад, Flask-SocketIO або окремий FastAPI/Starlette gateway).
3. Додати Redis як pub/sub і спільний adapter для Socket.IO; це обов'язково для кількох worker-ів чи контейнерів.
4. Канали: `class:{class_id}` для рулетки та `student:{student_id}` для персональних оновлень.
5. HTTP endpoints лишаються fallback, а після зміни стану сервіс публікує подію `roulette.created`, `roulette.voting` або `roulette.closed`.

PostgreSQL лишається джерелом істини; Redis не зберігає результати тесту.
