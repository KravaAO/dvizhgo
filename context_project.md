# Контекст проєкту

Проєкт починався як одноразова мемна контрольна робота для власного уроку: Flask-застосунок запускався локально та роздавався учням через ngrok.

Після розробки та обговорення концепція змінилася.

Тепер це не варто розглядати лише як quiz/test application.

Цільовий напрямок:

**Live Classroom Platform / інтерактивний цифровий шар поверх звичайного уроку.**

Викладач створює одну live-кімнату на початку уроку. Учні заходять у неї один раз і можуть залишатися підключеними протягом усього уроку.

Протягом заняття викладач у будь-який момент запускає різні activity/event:

- повторення;
- quick question;
- quiz;
- assessment;
- duel;
- vote;
- teacher reaction;
- break;
- mini-game;
- reflection;
- у майбутньому інші live activities.

Платформа не повинна диктувати сценарій уроку.

Її задача — дати викладачу набір інструментів, які він запускає спонтанно залежно від ситуації в класі.

---

# Поточний стан

Backend:

- Python;
- Flask;
- SQLite;
- Flask session;
- JSON-файл із питаннями;
- без складної архітектури;
- один Flask application.

Поточна БД вже містить:

### students

Зберігаються:

- ім'я;
- час старту;
- час завершення;
- поточне питання;
- score;
- кількість питань;
- порядок питань.

### answers

Зберігаються:

- student_id;
- question_id;
- selected_answers;
- correct/incorrect;
- response_time;
- answered_at.

Для одного учня одна відповідь на одне питання захищена UNIQUE constraint.

### Live Roulette / Duel

Уже реалізовані таблиці:

- `roulette_rounds`;
- `roulette_participants`;
- `roulette_votes`.

Тобто Live Duel уже існує і працює.

---

# Поточний Quiz Flow

Учень:

1. відкриває головну;
2. вводить ім'я та прізвище;
3. отримує Flask session;
4. проходить питання;
5. кожна відповідь окремо зберігається на сервері;
6. сервер перевіряє правильність;
7. після завершення показується score, percentage, rank та час.

Підтримуються:

- single answer;
- multiple answer;
- true/false;
- code block;
- shuffled answers;
- shuffled questions через configuration.

На frontend уже передається:

- question;
- original answer indexes;
- difficulty;
- code.

Візуально питання показуються картками.

У frontend уже присутні:

- progress;
- sound toggle;
- combo;
- reaction toast;
- character layer;
- rain/special-effect layer;
- roulette overlay.

ВАЖЛИВО:

не ламати існуючі мемні реакції, звуки, спецефекти та UI механіки.

Вони вже допрацьовані окремо.

---

# Уже реалізований Live Duel

Поточна назва в коді — Roulette.

Механіка:

1. викладач відкриває admin;
2. натискає запуск рулетки;
3. вводить довільне питання;
4. backend бере активних учнів;
5. випадково вибирає двох;
6. створює live round;
7. двоє обраних учнів отримують питання;
8. кожен пише власну текстову відповідь;
9. коли відповіли обидва, round переходить у voting;
10. інші учні голосують за одну з відповідей;
11. самі учасники голосувати не можуть;
12. один учень може проголосувати тільки один раз;
13. викладач бачить відповіді та кількість голосів;
14. викладач може завершити event;
15. після завершення учні повертаються до основного тесту.

Ця механіка вже протестована та її потрібно зберегти.

У майбутньому термін `Roulette` бажано відокремити від `Duel`, тому що roulette може стати лише способом вибору учасників, а Duel — окремим activity type.

---

# Поточна Admin Panel

Є:

- login викладача через пароль;
- кількість підключених;
- кількість тих, хто завершив;
- кількість активних;
- таблиця результатів;
- progress кожного учня;
- score;
- час;
- статус;
- перегляд детальних відповідей конкретного учня;
- запуск Roulette/Duel;
- перегляд стану Duel;
- завершення Duel;
- очищення результатів.

Поточна live-синхронізація admin реалізована polling:

- `/api/admin/results`;
- `/api/admin/roulette`;

приблизно раз на 3 секунди.

Це нормально для поточного prototype.

Не потрібно негайно переписувати все на WebSocket, якщо rooms можна реалізувати простіше.

Але архітектура повинна дозволяти пізніше перейти на WebSocket/SSE.

---

# Головна проблема поточної архітектури

Зараз система фактично має:

**один глобальний урок / один глобальний набір учнів / одну глобальну Roulette.**

Немає поняття Room.

Це головне, що потрібно змінити наступним.

Необхідно перейти від:

`students → quiz`

до:

`room → participants → activities`.

---

# Найближча велика задача — Rooms

Потрібно додати ізольовані кімнати.

Teacher створює room.

Наприклад:

`K7M4Q2`

Учень заходить:

`/join/K7M4Q2`

або вводить room code на головній сторінці.

Room має бути ізольований від інших room:

- свої participants;
- свій quiz;
- свої results;
- свої live events;
- своя roulette/duel;
- свої teacher reactions;
- свій activity state.

Не можна більше використовувати глобальний `get_open_roulette()`, який знаходить просто останній незакритий round у всьому застосунку.

Live event завжди повинен бути прив'язаний до `room_id`.

---

# Мінімальна модель Room

Не переускладнювати.

Наприклад:

### rooms

- id
- code
- title
- status
- created_at
- expires_at
- settings_json

Можливі status:

- lobby
- live
- finished

### participants

У майбутньому current `students` можна адаптувати або перейменувати.

Потрібно мати:

- room_id;
- name;
- joined_at;
- last_seen;
- finished_at;
- current_activity/current_question;
- score.

Не робити акаунти учнів.

Учень заходить по room code + nickname/name.

---

# Room Lifetime

Платформа повинна залишатися легкою.

Rooms ефемерні.

Орієнтовно:

- active room існує протягом уроку;
- після завершення ще деякий час доступні результати;
- старі results автоматично очищаються;
- не зберігати нескінченну історію проходжень.

На майбутнє:

- results TTL ~7 днів;
- inactive room cleanup;
- старі деталізовані answers cleanup.

Ці цифри поки можуть бути configuration, а не hardcoded business rule.

---

# Room Settings

Перед запуском викладач створює кімнату та отримує просту панель налаштувань.

Не робити 30–40 toggles.

Початковий набір:

### Session type

- Lesson
- Quiz
- Assessment

Це presets, а не три різні системи.

### Fun level

- Full
- Light
- Off

Керує:

- memes;
- sounds;
- decorative effects;
- characters.

### Teacher reactions

On / Off

### Student reactions

On / Off

### Immediate correctness

On / Off

Чи бачить учень правильність одразу після submit.

### Leaderboard

On / Off

### Live events

On / Off

Duel, Extra тощо.

### Break activities

On / Off

### Join after start

On / Off

Налаштування зберігати в `settings_json`, щоб поки що не створювати багато колонок.

---

# Lobby

Після створення room викладач потрапляє в Lobby.

Lobby є важливою частиною UX.

На teacher/projector screen:

- room title;
- великий room code;
- QR/code може бути доданий пізніше;
- кількість учасників;
- список тих, хто вже підключився;
- status online;
- кнопка Start Lesson.

Приклад:

LIVE LESSON

ROOM CODE  
K7M4Q2

12 учнів підключено

Оля  
Максим  
Данило  
Іра  
...

[ START LESSON ]

Lobby має виглядати як готовий сучасний продукт, а не admin table.

---

# Teacher Live Dashboard

Після Start Lesson викладач бачить не просто "результати тесту".

Це має стати Control Center уроку.

Основні action buttons:

- Quick Question
- Quiz
- Duel
- Vote
- Teacher Reaction
- Break
- Reflection

Поки не реалізовувати всі як складні системи.

Головне — закласти правильну структуру UI.

Наприклад:

LIVE ROOM · K7M4Q2  
18 online

[ Quick Question ]  
[ Duel ]  
[ Vote ]  
[ Reaction ]  
[ Break ]  
[ Reflection ]

Нижче participants:

Оля        online  
Максим     online  
Данило     answering  
...

Для Quiz Activity можна додатково показувати:

- question progress;
- accuracy;
- score.

---

# Activity Concept

Це важливий напрямок архітектури.

Не створювати окремий незалежний застосунок для кожної механіки.

У Room запускаються Activity.

Майбутні типи:

- quiz;
- quick_question;
- duel;
- vote;
- reflection;
- break;
- mini_game;
- assessment.

Room має current activity/state.

Activity може тимчасово переривати quiz і після завершення повертати учня до попереднього стану.

Саме так уже фактично працює Roulette Overlay.

Цю ідею потрібно узагальнити.

---

# Lesson Mode

Головний майбутній сценарій.

Учні заходять у room на початку уроку і залишаються в ньому весь урок.

Приклад:

Start Lesson

→ Warm-up  
3–5 quick questions

→ пояснення теми  
platform idle

→ Quick Check  
1–2 питання

→ Duel  
двоє відповідають, клас голосує

→ Break

→ практика

→ Teacher Reaction

→ Reflection

→ End Session

Платформа є другим інтерактивним екраном уроку.

Викладач вирішує, коли її використовувати.

---

# Quiz Mode

Коротке повторення або ігровий quiz.

Тут допустимі:

- memes;
- sounds;
- combo;
- animations;
- reactions;
- leaderboard;
- occasional special events.

---

# Assessment Mode

Контрольна / зріз знань.

Повинен бути значно спокійнішим.

Наприклад:

- Fun = Off/Light;
- no student reactions;
- no breaks;
- no mini-games;
- optional no immediate correctness;
- timer;
- results;
- question analytics.

Не створювати окремий backend assessment engine.

Це preset над тією самою системою.

---

# Reflection

Це важлива майбутня Activity.

Використовується наприкінці уроку.

Приклади:

### Scale

"Наскільки зрозуміла тема?"

1 2 3 4 5

### Multiple choice

"Що треба повторити?"

- loops
- functions
- lists
- OOP

### Short text

"Що сьогодні було найскладніше?"

### Confidence

"Чи зміг би ти пояснити тему іншому?"

- Так
- Частково
- Ні

Teacher бачить aggregated summary.

Наприклад:

Understanding: 4.1 / 5

Need repeat:
Loops — 6
Functions — 3
Lists — 1

Це одна з найкорисніших активностей і потенційно може використовуватися майже на кожному уроці.

---

# Teacher Reactions

Одна з майбутніх live-механік.

Teacher може надіслати reaction:

- конкретному student;
- усім;
- тільки тим, хто ще працює.

Приклади preset:

- 👀
- 🤔
- 🔥
- 🫡
- 🗿

Можливий короткий teacher message.

Наприклад:

"Я все бачу 👀"

або

"Подумай ще раз 🤔"

Reaction:

- не повинен блокувати UI;
- з'являється збоку/toast;
- сам зникає;
- не повинен бути постійним;
- це occasional live effect.

Не робити student-to-student free chat.

---

# Finished Student Mode

Після завершення activity учень не повинен просто сидіти на Result Page.

У майбутньому:

"Ти завершив"

12 / 15

Поки інші працюють:

- support reaction;
- optional bonus task;
- mini-game;
- waiting screen.

Це дозволить зайняти тих, хто закінчив раніше.

---

# Student Reactions

Якщо реалізовувати:

тільки preset reactions.

Без довільного тексту між учнями.

Наприклад:

👏 🔥 ❤️ 🧠 🫡

Потрібні:

- rate limit;
- aggregation;
- teacher toggle.

Наприклад замість 10 окремих reactions:

👏 × 8  
"Клас підтримує тебе"

---

# Break Mode

Під час уроку teacher може натиснути Break.

У майбутньому:

`BREAK ROULETTE`

Рулетка обирає activity із дозволеного pool.

Наприклад:

- mini-game;
- reaction race;
- truth/fake;
- random fact;
- movement break;
- teacher vs class;
- simple rest.

Teacher контролює pool.

Обов'язково:

- Skip;
- Reroll;
- Manual Start.

Рулетка — декоративний елемент, teacher завжди має остаточний контроль.

---

# Mini-games

Не реалізовувати великий набір зараз.

Майбутня ідея:

- Fly Rush;
- Reaction Race;
- Memory;
- Dodge;
- інші 30–60 секундні break games.

Mini-game не впливає на academic score.

Розділяти:

Knowledge Score

і

Game/Fun Score.

Mini-games особливо корисні для:

- break;
- finished students;
- short energy reset.

---

# Battle Ideas

Не є пріоритетом наступної ітерації.

Можливі майбутні режими:

- Team Battle;
- Last Brain Standing;
- Class vs Boss.

Але не реалізовувати Heroes-like battle зараз.

Це значно збільшує складність.

Якщо тестувати Battle, спочатку зробити дешеву версію:

### Mass Challenge

Всі відповідають одночасно.

18 players

→ question

12 correct remain

→ question

8 remain

→ question

3 finalists

Це можна побудувати на існуючому question engine без складного HP/attack system.

---

# AI / MCP

Не є пріоритетом beta.

У майбутньому платформа може мати власний MCP/server та AI generation.

Teacher може:

- вибрати тему;
- завантажити матеріал;
- вставити текст;
- обрати lesson content;

і AI генерує:

- quiz;
- quick question;
- extra question;
- reflection;
- adaptive question.

AI output завжди бажано показувати teacher preview перед запуском.

Не будувати AI частину до перевірки основного live classroom flow.

---

# Збереження даних

Сервіс повинен залишатися light.

Не будувати LMS.

Не зберігати все назавжди.

Майбутній принцип:

### Permanent-ish

- teacher;
- saved quizzes;
- configuration.

### Temporary

- rooms;
- participants;
- activity state;
- results;
- detailed answers.

### Pure live / RAM

За можливості:

- online users;
- heartbeat;
- transient UI state;
- live counters;
- temporary mini-game scores.

Не зберігати в БД hover/click/movement telemetry.

---

# Saved Quizzes

У майбутньому teacher зможе зберігати готові quiz templates.

Потрібен limit.

Наприклад:

10–20 saved quizzes на teacher.

Це не monetization зараз.

Причина:

- тримати продукт легким;
- не перетворювати систему у file storage;
- контролювати ресурси.

---

# Product Positioning

НЕ:

"ще один Kahoot"

НЕ:

"сайт для контрольних"

НЕ:

"мемний quiz"

Основне бачення:

**Live Classroom Toolkit / Classroom Control Center**

або:

**цифровий інтерактивний шар поверх звичайного уроку.**

Ключова особливість:

викладач не просто запускає заздалегідь створений quiz.

Він у реальному часі керує подіями уроку.

Наприклад:

Quiz

→ teacher запускає Duel

→ class Vote

→ назад у Quiz

→ teacher Reaction

→ Break

→ практика

→ Reflection.

---

# UX принцип

Teacher control > automation.

Система може пропонувати випадковість, але teacher завжди може:

- skip;
- reroll;
- stop;
- select manually;
- disable feature.

Не дозволяти системі керувати уроком замість викладача.

---

# UI Direction

До першої beta важливий хороший interface.

Не потрібно повністю переписувати frontend.

Потрібно зробити цілісний visual language.

Напрямок:

- dark UI;
- spacious layout;
- large cards;
- rounded corners;
- subtle gradients;
- clean typography;
- один основний accent;
- плавні короткі transitions;
- мінімум зайвого тексту;
- дуже чітка hierarchy.

Різні Activity можуть мати accent variations.

Наприклад:

Quiz — основний accent  
Duel — warm/red accent  
Reflection — calm purple/blue  
Break — brighter playful accent

Але вся платформа залишається одним дизайном.

---

# Що НЕ потрібно робити зараз

Не реалізовувати:

- складну battle system;
- boss HP;
- character classes;
- багато mini-games;
- AI generation;
- MCP;
- student accounts;
- subscriptions;
- payment;
- ads;
- complex analytics;
- long-term LMS storage;
- social/chat system.

---

# Найближчий roadmap

## Етап 1 — зараз

Поточний quiz + Duel повинні залишатися робочими.

Не ламати existing behaviour.

## Етап 2 — Rooms

Додати:

- room model;
- room code;
- create room;
- join room;
- room isolation;
- participants;
- lobby;
- room settings;
- start/end session.

## Етап 3 — Teacher Live Dashboard

Перетворити admin з "таблиці результатів" на live control center.

При цьому результати та student details залишити.

## Етап 4 — Teacher Reactions

Додати:

- reaction конкретному учню;
- broadcast reaction.

## Етап 5 — Reflection

Мінімум:

- scale;
- choice;
- text;
- teacher summary.

## Етап 6 — Break

Спочатку простий Break Event / Roulette.

Не потрібно одразу робити mini-games.

---

# Найближча beta

Ціль — не зробити завершений EdTech product.

Ціль — дати кільком реальним викладачам провести через систему урок.

Потрібно перевірити:

1. Чи легко teacher створює room?
2. Чи легко учні підключаються?
3. Чи можна залишити room відкритим весь урок?
4. Чи teacher реально використовує live activities?
5. Чи Duel покращує engagement?
6. Чи teacher reactions корисні або просто прикольні?
7. Чи Reflection хочеться використовувати регулярно?
8. Яких кнопок teacher не вистачає під час реального уроку?
9. Які features насправді не використовуються?
10. Чи хоче teacher провести через систему ще один урок?

---

# Поточні технічні моменти, які треба врахувати

1. Поточний `get_open_roulette()` глобальний.

Після Rooms він має працювати лише в контексті конкретної room.

2. Roulette зараз обирає учнів із глобального списку `students WHERE finished_at IS NULL`.

Після Rooms вибір повинен бути тільки серед participants конкретної кімнати.

3. `/api/admin/results` також зараз глобальний.

Потрібні room-scoped results.

4. Reset зараз видаляє всі дані системи.

Після Rooms потрібен:

`reset/end current room`

а не глобальний DELETE всіх students/results.

5. Admin auth зараз один глобальний password.

Для найближчого prototype це можна тимчасово залишити.

Не потрібно зараз будувати повноцінну teacher auth систему, якщо це затримає rooms.

6. Polling кожні 3 секунди поки допустимий.

Не переписувати систему на WebSocket лише заради архітектурної "чистоти".

Rooms та хороший UX зараз важливіші.

7. У quiz template зараз progress text містить hardcoded:

`Завдання {{ question_number }} / 67`

Це потрібно замінити на:

`{{ total_questions }}`.

8. Поточна стартова сторінка досі називає продукт "Контрольна" і використовує `PYTHON CONTROL MODE`.

Після Rooms вона повинна стати нейтральною landing/join page платформи.

---

# Головний принцип наступної роботи

Не переписувати працюючий prototype з нуля.

Поточні:

- quiz;
- answers;
- scoring;
- memes/effects;
- Roulette/Duel;
- admin results

вже є базою.

Потрібно поступово перетворити існуючу систему:

**Quiz Application**

на:

**Room-based Live Classroom Platform**

без втрати працюючих механік.