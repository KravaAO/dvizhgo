# DvizhGO

<p>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white" alt="Flask 3.1">
  <img src="https://img.shields.io/badge/Socket.IO-010101?logo=socketdotio&logoColor=white" alt="Socket.IO">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/Redis-7-FF4438?logo=redis&logoColor=white" alt="Redis 7">
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
</p>

DvizhGO — платформа для спільних квізів та інтерактивних активностей у кімнатах.

## Запуск через Docker

```bash
cp .env.example .env
docker network create msschool_default
docker compose up --build -d
```

Застосунок: [http://localhost:5000](http://localhost:5000).

## Запуск без Docker

Потрібен Python 3.12. Дані зберігаються в локальній SQLite-базі `quiz.db`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Тести

```bash
python -m unittest discover -s tests
```

## Ліцензія

[MIT](LICENSE)
