# Room-first refactor plan

## Статус

**Стан:** runtime foundation (Phase 0–4) реалізовано; WebSocket transport, late-join policy та legacy cleanup залишаються наступними етапами.
**Мета:** зробити кімнату постійним live-контекстом, у якому послідовно запускаються різні активності: квізи, Duel, Live Zones та наступні формати.

## Терміни

У продукті використовуємо такі назви:

- **room** — кімната, центральна сутність live-сесії;
- **room host** — людина, яка створила кімнату і керує активностями;
- **participant** — людина, яка приєдналася до кімнати;
- **activity** — окремий запущений формат у кімнаті: quiz, duel, live zone тощо;
- **attempt** — конкретна спроба participant пройти конкретну activity.

Не прив'язуємо доменну модель до термінів «викладач» чи «учень». Це дозволяє використовувати платформу для будь-яких груп.

## Виявлені проблеми поточної моделі

1. `question_order` створюється під час join. Participant потрапляє в room уже прив'язаним до квіза, хоча room має існувати незалежно від майбутньої activity.
2. Поточний запис participant одночасно зберігає присутність у кімнаті, прогрес квіза, рахунок і результати. Через це завершення квіза фактично завершує участь у room.
3. Extra Activity відображається як frontend-overlay, але backend може й надалі приймати відповіді квіза.
4. Вихід room host раніше очищав runtime-дані. Logout, reset і finish room змішані семантично.
5. `SHUFFLE_QUESTIONS=false` не гарантує відсутність shuffle: `add_participant()` додатково перемішує порядок питань.
6. `left_at IS NULL` описує лише факт явного виходу, а не реальний online-стан. Refresh, закриття вкладки та розрив Wi-Fi не мають надійного lifecycle.

## Цільова модель

```text
Room
├── RoomParticipant (присутність і reconnect)
├── Activity (історія запусків у room)
│   ├── QuizAttempt
│   │   └── QuizAttemptAnswer
│   ├── DuelRound
│   └── LiveZoneState
└── RoomRuntime (поточна активність і її стан)
```

### Room

Room зберігає лише контекст сесії: код, назву, creator/host, налаштування й поточний runtime-стан. Приєднання до room не створює квіз і не обирає питання.

Рекомендовані поля:

```text
id, code, title, created_at, status
active_activity_id, runtime_version, settings_json
```

`runtime_version` збільшується на кожній зміні активності. Він допоможе клієнту виявити, що room змінилася, навіть до WebSocket-впровадження.

### RoomParticipant

Participant існує, доки він або вона є учасником room, незалежно від того, скільки активностей завершено.

Рекомендовані поля:

```text
id, room_id, display_name, reconnect_token_hash
joined_at, last_seen_at, left_at
presence_state, metadata_json
```

`presence_state` — похідний стан: `online`, `away`, `left`. Джерело істини для `online/away` — `last_seen_at`, а не лише `left_at`.

### Activity та RoomRuntime

Кожен запуск activity має власний запис.

```text
Activity:
id, room_id, type, status, config_json, started_at, paused_at, finished_at

RoomRuntime:
room_id, current_activity_id, state, updated_at, version
```

Базові значення `type`: `quiz`, `duel`, `live_zone`. Базові значення `status/state`: `lobby`, `starting`, `active`, `paused`, `finished`, `cancelled`.

Лише одна activity може бути `active` у room одночасно. Це правило має перевіряти backend у транзакції.

### QuizAttempt

Спроба створюється **лише в момент старту quiz activity**, а не при join room.

```text
id, activity_id, participant_id, question_order_json
current_question, score, started_at, finished_at, abandoned_at
```

Відповіді належать `QuizAttempt`, а не participant:

```text
id, attempt_id, question_id, selected_answers_json
is_correct, response_time, answered_at
```

Це дозволяє одному participant пройти кілька квізів у тій самій room без дублювання room-профілю.

## Правила поведінки

### Join room

```text
join room
→ create/reconnect RoomParticipant
→ show room lobby/current activity
→ no quiz attempt yet
```

Якщо quiz уже активний, room host може визначити політику входу: створити late-join attempt, показати очікування або не допускати до поточної activity. Цю політику слід явно зберігати у `config_json` activity.

### Start quiz

```text
room host selects quiz
→ create Activity(type=quiz)
→ snapshot questions/configuration
→ create QuizAttempt for eligible participants
→ mark room runtime as active
```

Question order генерується тут і тільки тут. Shuffle застосовується лише якщо увімкнений у конфігурації activity.

### Pause for Duel / Extra Activity

```text
quiz active
→ host starts duel
→ quiz activity = paused
→ room runtime = duel active
→ answer API rejects quiz answers with 409 activity_paused
→ duel finishes
→ room runtime returns to paused quiz or next chosen activity
```

Frontend overlay є лише відображенням стану. Backend завжди перевіряє, чи `attempt.activity_id == room.current_activity_id` та чи activity має статус `active`.

### Finish quiz

```text
finish QuizAttempt
→ show finish screen
→ participant remains RoomParticipant
→ participant can wait, vote in duel, enter next activity or leave room
```

### Logout, leave, reset, finish room

Це чотири різні дії:

| Дія | Хто виконує | Наслідок |
|---|---|---|
| Leave room | participant або room host | Прибирає лише власну browser-сесію / присутність; room не завершується. |
| Logout | room host | Лише завершує авторизаційну сесію host; не змінює room runtime. |
| Reset room | room host | Явно очищує runtime поточної room і повертає її до lobby; потребує підтвердження. |
| Finish room | room host | Завершує live-сесію для всіх, робить room недоступною для нових join і очищує тимчасові результати за обраною політикою. |

Жодна кнопка «Вийти» або «Logout» не має неявно очищати дані всього уроку.

## Online та reconnect lifecycle

До впровадження WebSocket потрібен надійний polling/heartbeat:

1. Клієнт надсилає `POST /api/presence/heartbeat` кожні 20–30 секунд та при поверненні вкладки у foreground.
2. Backend оновлює `last_seen_at` лише для поточного session/reconnect token.
3. `online` означає heartbeat не старший за 45–60 секунд; старіший — `away`.
4. `left` встановлюється лише після явного leave або коли room host завершує room.
5. Refresh відновлює того самого `RoomParticipant` за signed reconnect token, а не створює дубль.

WebSocket у майбутньому надсилатиме ті ж state-events. Heartbeat і `runtime_version` залишаються fallback-механізмом.

## План реалізації

### Phase 0 — safety fixes і контракти

- Зафіксувати API/error-коди для `activity_paused`, `activity_finished`, `room_finished`, `attempt_not_found`.
- Прибрати безумовний shuffle з `add_participant()`; порядок генерується лише на старті quiz attempt.
- Розділити існуючу кнопку host logout від reset runtime.
- Додати інтеграційні тести поточного join/start/answer/leave сценарію як baseline.

**Готово, коли:** вимкнений shuffle ніколи не змінює порядок питань, а logout host не очищує room.

### Phase 1 — нова схема без switch-over

- Створити таблиці `room_participants`, `activities`, `quiz_attempts`, `quiz_attempt_answers`, `room_runtime`.
- Додати міграції для SQLite і PostgreSQL.
- Залишити legacy `students`/`answers` read-only на час переходу.
- Створити service-layer API для room, presence та activity lifecycle.

**Готово, коли:** можна створити RoomParticipant і Activity без створення legacy student/quiz progress.

### Phase 2 — room presence та reconnect

- Перевести join/lobby/DVD на `room_participants`.
- Додати reconnect token, heartbeat та derived online state.
- Уникнути дублю participant після refresh.

**Готово, коли:** один participant після refresh бачить себе в тій самій room один раз; offline participant переходить у `away` без видалення історії active session.

### Phase 3 — quiz attempts

- Старт квіза створює `Activity` і attempts для визначеної групи participant.
- Перевести question/answer/result endpoints на `quiz_attempts`.
- Snapshot quiz content або immutable quiz version на момент старту.
- Перевести retry на створення нової attempt, а не нового participant.

**Готово, коли:** один participant може завершити quiz, залишитися в room і почати інший quiz без повторного join.

### Phase 4 — activity state machine та Duel

- Ввести транзакційний `current_activity` у room runtime.
- Перевести Duel на Activity subtype/handler.
- Backend блокує quiz answer під час pause або іншої active activity.
- Додати explicit resume/cancel flow.

**Готово, коли:** неможливо записати quiz answer, поки room показує Duel; після resume продовжується той самий attempt.

### Phase 5 — cut-over та очищення legacy

- Переключити admin results, roulette та lobby queries на нову схему.
- Вимкнути dual-read/write після перевіреного періоду.
- Видалити або архівувати legacy `students`, `answers`, `question_order` лише окремою схваленою міграцією.
- Додати retention job для runtime-даних завершених room.

**Готово, коли:** жоден production route не читає legacy quiz state.

## Вимоги до тестування

Мінімальні інтеграційні сценарії для кожної фази:

1. Participant приєднується до lobby без створення quiz attempt.
2. Два participant отримують окремі attempts тільки після старту quiz.
3. `SHUFFLE_QUESTIONS=false` зберігає початковий порядок для всіх відповідних attempts.
4. Participant завершує quiz, але залишається online у room.
5. Host запускає Duel — quiz answer endpoint повертає `409 activity_paused`.
6. Refresh participant не створює другий запис presence.
7. Розрив heartbeat переводить participant у `away`, explicit leave — у `left`.
8. Logout host не змінює runtime room; Reset і Finish room змінюють його лише після підтвердження.

## Нерозв'язані рішення перед реалізацією

1. Чи дозволяється late join під час уже активного квіза, і з якого питання починається його attempt?
2. Чи може participant, який завершив quiz, голосувати у Duel до завершення всієї room?
3. Який retention для тимчасового runtime після Finish room: одразу, 15 хвилин чи до кінця дня?
4. Чи room host може повторно увійти в room після logout через окремий host access token або майбутній account?

Відповіді на ці питання не блокують Phase 0–2, але потрібні перед повним switch-over quiz attempts.
