# Implementation log

## Як вести журнал

Для кожного фактичного етапу додаємо запис у форматі:

```md
## YYYY-MM-DD — Phase N: назва

**Статус:** planned | in progress | done | blocked

### Змінено
- ...

### Міграції / сумісність
- ...

### Перевірено
- ...

### Відомі обмеження
- ...

### Наступний крок
- ...
```

У цей лог не записуємо припущення як виконану роботу. Якщо змінюється архітектурне рішення, спочатку оновлюємо план, потім журнал.

---

## 2026-09-26 — Baseline: room-first refactor planned

**Статус:** planned

### Зафіксовано

- Room визначена як головна live-сутність продукту.
- Participant має бути відокремлений від QuizAttempt.
- Quiz attempt створюється на старті activity, а не при join room.
- Extra Activity має керуватися backend state machine, а не лише frontend overlay.
- Logout, Leave room, Reset room і Finish room мають окрему семантику.
- Для reconnect потрібні heartbeat, `last_seen_at` та стабільний reconnect token.

### Поточний технічний baseline

- Є PostgreSQL і Docker runtime.
- Є room lobby, quiz, roulette/Duel UI, quiz builder і тимчасове очищення runtime-результатів.
- Поточна модель усе ще використовує legacy `students`, `answers` та `question_order` для quiz progress.
- Виявлено ризик: `add_participant()` безумовно shuffle-ить `question_order`, незалежно від `SHUFFLE_QUESTIONS`.

### Не робили в цьому записі

- Не змінювали schema чи API.
- Не виконували міграції даних.
- Не змінювали поточний lifecycle room/quiz.

### Наступний крок

- Почати Phase 0 з safety fixes, API-контрактів і baseline інтеграційних тестів відповідно до [room-first plan](ROOM_FIRST_REFACTOR_PLAN.md).

---

## 2026-09-26 — Phase 0–4: room runtime foundation

**Статус:** done for the current Flask runtime; Socket.IO delivery added.

### Змінено

- Додано `room_participants` з `reconnect_token_hash`, `last_seen_at` і `left_at`.
- Додано `activities`, `room_runtime`, `quiz_attempts`, `quiz_attempt_answers` та duel runtime tables.
- Join room створює лише `RoomParticipant`; quiz attempt створюється під час `POST /api/lobby/start`.
- Питання квіза snapshot-яться у config activity. Порядок генерується лише при створенні attempt і не змінюється, коли `SHUFFLE_QUESTIONS=false`.
- `/api/answer` перевіряє `room_runtime.current_activity_id` та повертає `409` / `activity_paused`, коли quiz перерваний Duel.
- Запуск Duel pause-ить quiz activity; закриття Duel відновлює саме той quiz activity.
- Finish екран не відокремлює participant від room; завершений participant може перейти на live Duel stage і голосувати.
- Додано heartbeat endpoint і Socket.IO heartbeat у lobby, quiz та ДВИЖ-ДУЕЛІ. Online визначається за `last_seen_at` за останні 60 секунд.
- Додано room-scoped Socket.IO events: `room:state`, `room:presence`, `room:results_updated` і `room:duel_updated`. Регулярний HTTP polling для lobby, admin та activity screens прибрано.
- Docker отримав Redis як Socket.IO pub/sub і один Gunicorn worker із 100 threads; масштабування до кількох instances вимагає sticky sessions на load balancer.
- `POST /admin/logout` тепер завершує лише host browser session. `POST /api/admin/reset` і новий `POST /api/admin/finish` залишаються явними room-level діями.

### Міграції / сумісність

- Нові таблиці створюються і для SQLite, і для PostgreSQL через поточний startup migration path.
- Legacy `students` / `answers` / roulette tables ще не видалені: reset очищує їх як перехідні runtime records, але production routes більше не використовують їх для нових flow.

### Перевірено

- Додано `tests/test_room_first_runtime.py`.
- Перевірено ізольований сценарій: join двох participant → start quiz → attempts створено → порядок не shuffle-иться → Duel pause → answer отримує `409 activity_paused` → close Duel resume → host logout не очищує room.

### Відомі обмеження

- Socket.IO client поки завантажується з pinned CDN asset; для production packaging його треба перенести у versioned локальний asset.
- Late join під час уже активного quiz поки залишається в room lobby до наступної activity.
- Host UI для explicit Finish room ще треба додати; API вже існує.

### Наступний крок

- Винести activity lifecycle у окремий service module й узгодити late-join policy перед horizontal scaling.
