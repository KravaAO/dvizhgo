# DvizhGO: поточний цикл гри та правила переходів

**Статус документа:** зафіксований фактичний стан станом на 2026-09-29.
Це джерело правди для UI-текстів, тестів та подальшої роботи над state machine.

## Ключова модель

```text
Room — довгоживуча live-сесія
├── RoomParticipant — учасник і його reconnect/presence
├── Activity — один запуск формату в room
│   ├── quiz
│   ├── duel
│   └── flash_question
├── QuizAttempt — одна спроба participant у конкретному quiz activity
└── RoomRuntime — поточна активність і стан інтерфейсу room
```

Room не дорівнює одному квізу. Після завершення квіза room може повернутися у
стан очікування, зберегти учасників та запустити наступний квіз.

## Стан room та activity

| Рівень | Стани | Значення |
|---|---|---|
| `rooms.status` | `lobby`, `active`, `finished` | Життєвий цикл усієї room. |
| `room_runtime.state` | `lobby`, `active` | Що зараз показувати клієнтам. |
| `activities.status` | `active`, `paused`, `finished` | Життєвий цикл одного запуску. |
| `quiz_attempts` | active / `finished_at` / `abandoned_at` | Прогрес конкретного participant. |

## Повний сценарій

```text
1. Host створює room
   → room.status=lobby, runtime=lobby

2. Host обирає або створює квіз
   → квіз належить бібліотеці room; activity ще не існує

3. Учасники входять за кодом
   → створюється RoomParticipant; у lobby спроби квіза немає

4. Host запускає квіз
   → створюється Activity(type=quiz, status=active)
   → створюється QuizAttempt для кожного active participant
   → room.status=active, runtime=current quiz / active

5. Учасник відповідає
   → відповідь належить його QuizAttempt
   → після останнього питання attempt завершено
   → participant бачить Result, але залишається в room

6. Host завершує квіз після всіх спроб
   → quiz Activity стає finished
   → runtime=lobby, room.status=lobby
   → результати й завершені attempts збережені
   → room host та participant-и повертаються у waiting lobby

7. Host може обрати та запустити наступний квіз
   → створюється нова quiz Activity і нові QuizAttempt
   → учасники не повинні входити в room повторно

8. Host явно завершує room
   → room.status=finished, participant-и позначаються left
   → новий join за кодом заборонений
```

## Переходи host

| Дія UI | Коли доступна | Фактична дія | Що зберігається |
|---|---|---|---|
| Створити room | з головної | створює room у `lobby` | room, host access token |
| Обрати квіз | у бібліотеці | встановлює `active_quiz_id` | бібліотека квізів |
| Почати квіз | lobby, немає current activity | створює active quiz activity і attempts | snapshot питань, attempts |
| ДВИЖ-ДУЕЛЬ | лише під час active quiz | quiz `paused`, duel `active` | quiz progress не втрачається |
| Завершити ДВИЖ-ДУЕЛЬ | duel active | повертає paused quiz у `active` | відповіді дуелі й quiz progress |
| Flash Question | лише під час active quiz | quiz `paused`, flash `active` | quiz progress не втрачається |
| Завершити Flash | flash active або timeout | відновлює paused quiz | flash answers і quiz progress |
| **Завершити квіз** | усі незалишені attempts finished | active quiz → `finished`; room → `lobby` | results, attempts, participant-и |
| Скинути room | host підтвердив дію | очищає runtime activities/attempts, room → `lobby` | participant-и й library квізів |
| Завершити room | host підтвердив дію | room → `finished`, учасники → left | room/quiz library; runtime очищується |
| Вийти (host logout) | будь-коли | очищає лише host browser session | уся room і runtime |

## Чому host може перейти з `/admin` у waiting lobby

Поточна поведінка є **навмисною** і захищена двома перевірками в
`POST /api/admin/return-to-lobby`:

1. Поточна activity має бути `quiz` зі статусом `active`.
2. Не має бути жодної спроби без `finished_at` або `abandoned_at`.

Якщо хоча б один participant ще проходить квіз, сервер повертає `409`, а не
переводить room у lobby. Якщо всі завершили, сервер:

```text
activity.status = finished
room_runtime.current_activity_id = null
room_runtime.state = lobby
rooms.status = lobby
```

Результати не видаляються. Це покрито інтеграційним тестом
`test_completed_participant_can_return_to_lobby_while_host_stays_on_live_control`.

### Проблема UI

Назва кнопки **«До лобі»** вводить в оману: вона виглядає як звичайна
навігація, але насправді завершує active quiz. До production її слід перейменувати:

```text
«Завершити квіз і відкрити лобі»
```

І додати confirmation modal:

```text
Усі учасники завершили квіз.
Квіз буде завершено, результати збережено,
а room повернеться в режим очікування.

[Продовжити квіз] [Завершити квіз]
```

Звичайний перехід host у лобі без зміни state має бути окремим link лише тоді,
коли `room.status=lobby`. Під час active quiz `/lobby` і `/lobby/host` мають
перенаправляти в `/admin` — це поточна й правильна поведінка.

## Правила participant

| Ситуація | Куди потрапляє participant | Що може робити |
|---|---|---|
| Join до старту | `/lobby` | presence, avatar, lobby boost |
| Join під час active quiz | `/quiz` | отримує late-join attempt |
| Join під час duel/flash | `/activity` | бачить current extra activity; отримує late quiz attempt для resume |
| Active quiz | `/quiz` | відповідає лише за свою attempt |
| Duel або flash | `/activity` | quiz answer API повертає `409 activity_paused` |
| Завершив quiz | `/result` → може повернутися у lobby | переглядає результат, очікує next activity |
| Explicit leave | `/` | `left_at` встановлено, room не завершується |

## Основні можливості current release

- створення ізольованих room із коротким кодом;
- host/session доступ без participant registration;
- library квізів room, JSON import, preview, редактор карток і ручна карусель;
- single, multiple, true/false, порядок питань per attempt;
- live presence, avatar, reconnect token, heartbeat;
- self-paced quiz, результати й деталі відповідей;
- ДВИЖ-ДУЕЛЬ, який ставить quiz на паузу;
- Flash Question із таймером, completion і автоматичним поверненням до quiz;
- Socket.IO room events для state, presence та results;
- explicit reset, finish room і host logout із різною семантикою.

## Інваріанти, які не можна порушити

1. У room лише одна current active activity.
2. Quiz answer приймається лише коли attempt відповідає current active quiz.
3. Extra activity не знищує progress paused quiz.
4. `logout` не дорівнює `reset` і не дорівнює `finish room`.
5. Повернення в lobby після completed quiz зберігає results і participant-ів.
6. `reset room` потребує окремого підтвердження, бо знищує runtime.
7. `finish room` незворотно закриває join для room code.

## Найближчі UI-виправлення

- [ ] Перейменувати `До лобі` на `Завершити квіз і відкрити лобі`.
- [ ] Додати confirmation modal з наслідками цієї дії.
- [ ] Додати окремий read-only badge у `/admin`: `Квіз активний`,
  `Очікуємо N завершень` або `Квіз готовий до завершення`.
- [ ] Показувати history завершених activity/квізів room в аналітиці, а не
  змішувати її з current runtime.
- [ ] Покрити тестами UI-contract: кнопка не є навігацією і недоступна, поки
  хоча б одна спроба active.
