# Підготовка Quiz Platform до тестового production

## Рішення щодо мережі та портів

Quiz Platform не публікує HTTP-порт на хост. Nginx із
`C:\Users\artem\Documents\knowstack\nginx\nginx.conf` має проксіювати
трафік до контейнера через зовнішню Docker-мережу `msschool_default`.

```text
Internet
  → Nginx (TLS, 80/443)
  → Docker network msschool_default
  → quiz-platform-web:5000
```

Це не створює конфліктів із наявними сервісами:

| Порт | Стан / власник | Дія Quiz Platform |
|---:|---|---|
| 5000 | зайнятий поточним dev-контейнером Quiz | не публікувати в test-prod |
| 5432 | локальний PostgreSQL | не публікувати PostgreSQL Quiz |
| 6379 | Redis Quiz у Docker | не публікувати Redis Quiz |
| 18080 | зарезервований KommoAI | не використовувати |
| 18081 | зарезервувати для KommoAI за домовленістю | не використовувати |

> Якщо Nginx працює не в Docker, не обирати новий порт навмання. Спершу
> інвентаризувати порти сервера і погодити окремий loopback-порт. Основна
> схема цього документа не потребує жодного host-порту для Quiz.

## Передумови

- Nginx KnowStack уже працює у Docker і публікує тільки `80:80` та `443:443`.
- Наявна конфігурація вже використовує Docker DNS (`resolver 127.0.0.11`) для
  `kommoai-api:8000`; Quiz використовує той самий підхід.
- Nginx і Quiz підключені до однієї зовнішньої мережі `msschool_default`.
- Є окремий тестовий hostname, наприклад `quiz-test.tutordesk.site`, та
  випущений для нього TLS-сертифікат.
- Docker і Docker Compose доступні на сервері.
- DNS тестового hostname вказує на сервер, а TLS-сертифікат випущений або
  може бути випущений Nginx/Certbot.

Перевірити мережу до запуску:

```powershell
docker network inspect msschool_default
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
Get-NetTCPConnection -State Listen | Sort-Object LocalPort
```

## 1. Production environment

Створити локальний для сервера файл `.env.production`; не додавати його в Git.
У репозиторії вже є безпечний шаблон `.env.production.example`.

```dotenv
POSTGRES_DB=quiz_test
POSTGRES_USER=quiz_test
POSTGRES_PASSWORD=<generate-a-unique-long-password>
SECRET_KEY=<generate-a-long-random-secret>
ADMIN_PASSWORD=<set-a-unique-admin-password>
SHUFFLE_ANSWERS=true
SHUFFLE_QUESTIONS=false
AVATAR_LAB_PATH=<long-private-path-or-disable-route>
```

Згенерувати секрети, наприклад:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Обов'язково:

- не використовувати значення з `.env.example`;
- не комітити `.env.production`;
- обмежити доступ до файлу лише обліковому запису деплою;
- використати окремі volume і БД `quiz_test`, не dev-дані.

## 2. Compose override для test-prod

У репозиторії вже є `docker-compose.test-prod.yml`. Його потрібно запускати
разом з основним compose; він вимикає всі host-порти та додає upstream alias.
Вміст override:

```yaml
services:
  web:
    ports: !reset []
    networks:
      default: {}
      shared_nginx:
        aliases:
          - quiz-platform-web
    environment:
      AVATAR_LAB_PATH: ${AVATAR_LAB_PATH}

  db:
    ports: !reset []

  redis:
    ports: !reset []

networks:
  shared_nginx:
    name: msschool_default
    external: true
```

Перед запуском перевірити зібрану конфігурацію:

```powershell
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.test-prod.yml config
```

У фінальному output не повинно бути `5000:5000`, `5432:5432` або `6379:6379`.

## 3. Nginx virtual host

У `C:\Users\artem\Documents\knowstack\nginx\nginx.conf` додати вміст
`deploy/nginx/quiz-test.tutordesk.site.conf`. Він повторює патерн наявного
`kommoai.tutordesk.site`; upstream відповідає Docker alias, а не `localhost`.

```nginx
server {
    listen 80;
    server_name quiz-test.tutordesk.site;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name quiz-test.tutordesk.site;
    resolver 127.0.0.11 ipv6=off valid=30s;
    set $quiz_upstream quiz-platform-web:5000;

    ssl_certificate /etc/letsencrypt/live/quiz-test.tutordesk.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/quiz-test.tutordesk.site/privkey.pem;

    client_max_body_size 2m;

    location / {
        proxy_pass http://$quiz_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Flask-SocketIO transport and WebSocket upgrade.
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 75s;
        proxy_send_timeout 75s;
    }
}
```

Перевірити та застосувати конфігурацію лише після успішного тесту:

```powershell
docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx nginx -t
docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx nginx -s reload
```

## 4. Запуск

```powershell
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.test-prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.test-prod.yml ps
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.test-prod.yml logs --tail=100 web db redis
```

Після старту Nginx має бачити `quiz-platform-web` у `msschool_default`.
Перевірка з Nginx-контейнера KnowStack:

```powershell
docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx wget -qO- http://quiz-platform-web:5000/health
```

Очікувана відповідь: `{"ok": true}`.

## 5. Acceptance checklist

- [ ] `https://quiz-test.tutordesk.site/health` відповідає `200` і `{"ok": true}`.
- [ ] HTTP редіректить на HTTPS.
- [ ] Створення кімнати та вхід кількох учасників працюють через домен.
- [ ] Socket.IO не деградує: lobby/presence/quiz activity оновлюються між двома браузерами.
- [ ] Quiz, Duel, Flash Question, leave та reconnect перевірені вручну.
- [ ] Перезапуск `web` не втрачає даних тестової БД.
- [ ] `db` і `redis` недоступні ззовні Docker-мережі.
- [ ] Логи не містять `5xx`, database connection errors або Socket.IO transport errors.
- [ ] Адмін-пароль не збігається з dev-паролем і не є в Git.

## 6. Rollback

1. Прибрати або вимкнути server block `quiz-test.example.com` і виконати
   `nginx -t` / reload.
2. Зупинити лише Quiz stack:

   ```powershell
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.test-prod.yml down
   ```

3. Не запускати `down -v`: volume з test-prod PostgreSQL потрібний для
   діагностики та відновлення.
4. Зберегти логи й зробити backup БД перед будь-яким очищенням даних.
