# Інтерактивна контрольна робота

Невеликий Flask-застосунок для проведення контрольної роботи в класі через локальний сервер + ngrok.

## Що є в проєкті

- стартова сторінка з ім'ям учня;
- питання-картки;
- single / multiple / true_false;
- випадкове перемішування відповідей;
- задумливі смайли, які визирають з країв екрана;
- другий персонаж для multiple-choice без прив'язки до правильності;
- реакція після довгого роздумування;
- випадкові success/error звуки;
- combo system;
- автоматичне збереження кожної відповіді;
- SQLite;
- відновлення поточного питання після перезавантаження сторінки;
- live admin page;
- перегляд відповідей конкретного учня;
- очищення результатів;
- mobile layout;
- sound toggle;
- prefers-reduced-motion.

## 1. Встановлення

Створити virtual environment:

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS / Linux:

```bash
source venv/bin/activate
```

Встановити залежності:

```bash
pip install -r requirements.txt
```

## 2. Запуск

```bash
python app.py
```

Сайт:

```text
http://127.0.0.1:5000
```

Сторінка викладача:

```text
http://127.0.0.1:5000/admin
```

Пароль за замовчуванням:

```text
teacher123
```

Перед реальною контрольною пароль краще змінити через змінну середовища.

### Windows PowerShell

```powershell
$env:ADMIN_PASSWORD="мій_пароль"
python app.py
```

### macOS / Linux

```bash
export ADMIN_PASSWORD="мій_пароль"
python app.py
```

Так само можна встановити:

```text
SECRET_KEY
SHUFFLE_ANSWERS=true
SHUFFLE_QUESTIONS=false
```

## 3. Ngrok

Після запуску Flask:

```bash
ngrok http 5000
```

Ngrok покаже HTTPS-адресу на кшталт:

```text
https://example.ngrok-free.app
```

Саме її можна відправити учням.

## 4. Питання

Усі питання знаходяться у:

```text
questions.json
```

Приклад single:

```json
{
  "id": 1,
  "type": "single",
  "question": "Що повертає len([1, 2, 3])?",
  "answers": ["2", "3", "4", "Помилка"],
  "correct": [1]
}
```

Індекси `correct` починаються з 0.

Тобто:

```text
0 = перша відповідь
1 = друга
2 = третя
3 = четверта
```

Multiple:

```json
{
  "id": 2,
  "type": "multiple",
  "question": "Які типи mutable?",
  "answers": ["list", "dict", "tuple", "str"],
  "correct": [0, 1]
}
```

True / False:

```json
{
  "id": 3,
  "type": "true_false",
  "question": "range(5) дає значення 0..4",
  "answers": ["Правда", "Неправда"],
  "correct": [0]
}
```

Для коду можна додати:

```json
"code": "print('Hello')"
```

Також підтримуються:

```json
"explanation": "Коротке пояснення",
"difficulty": "easy"
```

## 5. Звуки

Файли лежать у:

```text
static/sounds/
```

Можна просто замінити:

```text
correct_1.wav
correct_2.wav
correct_3.wav
wrong_1.wav
wrong_2.wav
```

на свої короткі WAV-файли з такими самими назвами.

Якщо хочеш MP3, зміни масиви `correctSounds` / `wrongSounds` у:

```text
static/js/quiz.js
```

## 6. Мемні повідомлення

У `static/js/quiz.js` є:

```javascript
const correctMessages = [...]
const wrongMessages = [...]
```

Їх можна редагувати без змін backend.

## 7. Персонажі з країв

Зараз використовуються emoji:

```text
🤔 👀 🧐 😏 🫣 🗿
```

Логіка знаходиться у:

```text
static/js/quiz.js
```

Функція:

```javascript
showCharacter(...)
```

За бажанням її легко замінити на `<img>` і використовувати PNG/WebP.

## 8. База

`quiz.db` створюється автоматично після першого запуску.

Зберігається:

- ім'я;
- час старту;
- прогрес;
- результат;
- відповідь на кожне питання;
- правильність;
- час відповіді.

На сторінці `/admin` є кнопка очищення результатів.

## 9. Перед контрольною

Рекомендовано:

1. замінити питання у `questions.json`;
2. запустити сайт;
3. пройти його самому;
4. відкрити `/admin`;
5. очистити тестові результати;
6. тільки після цього відкрити ngrok;
7. роздати URL учням.

## Важливо

Це навчальний локальний застосунок, а не production-система. Flask debug mode увімкнений для зручності. Для одноразового використання в класі цього достатньо.
