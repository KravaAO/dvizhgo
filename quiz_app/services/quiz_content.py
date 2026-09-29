"""Quiz content loading, validation, and presentation rules."""

import json
import random


DEFAULT_QUIZ_TITLE = "Django та Git — готовий квіз"


def load_questions(questions_path):
    with open(questions_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_room_questions(repository, room_id, questions_path):
    return repository.selected_questions(room_id) or load_questions(questions_path)


def get_room_quiz_title(repository, room):
    """Return the selected quiz name without coupling a room to a running attempt."""
    return repository.selected_title(room) or DEFAULT_QUIZ_TITLE


def validate_quiz_payload(payload):
    data = payload if isinstance(payload, dict) else {"questions": payload}
    title = str(data.get("title") or "Мій квіз").strip()[:120]
    questions = data.get("questions")
    if not title or not isinstance(questions, list) or not 1 <= len(questions) <= 67:
        raise ValueError("Потрібно від 1 до 67 питань і назва квіза.")

    valid_types = {"single", "multiple", "true_false"}
    normalized = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Питання {index} має бути об'єктом.")
        kind = item.get("type", "single")
        question = str(item.get("question") or "").strip()
        answers = item.get("answers")
        correct = item.get("correct")
        if kind not in valid_types or not question or not isinstance(answers, list) or not 2 <= len(answers) <= 8:
            raise ValueError(f"Перевірте тип, текст і варіанти питання {index}.")
        answers = [str(answer).strip() for answer in answers]
        if any(not answer for answer in answers) or not isinstance(correct, list) or not correct:
            raise ValueError(f"Питання {index} має містити непорожні варіанти та правильну відповідь.")
        try:
            correct = sorted({int(answer) for answer in correct})
        except (ValueError, TypeError) as error:
            raise ValueError(f"Некоректні правильні відповіді в питанні {index}.") from error
        if any(answer < 0 or answer >= len(answers) for answer in correct):
            raise ValueError(f"Правильна відповідь поза межами варіантів у питанні {index}.")
        if kind in {"single", "true_false"} and len(correct) != 1:
            raise ValueError(f"У питанні {index} типу {kind} має бути одна правильна відповідь.")
        if kind == "true_false" and len(answers) != 2:
            raise ValueError("True/false питання має містити рівно два варіанти.")
        normalized.append({
            "id": index,
            "type": kind,
            "question": question,
            "text": str(item.get("text") or "").strip()[:1800],
            "code": str(item.get("code") or "").strip()[:4000],
            "answers": answers,
            "correct": correct,
            "explanation": str(item.get("explanation") or "").strip()[:500],
            "difficulty": str(item.get("difficulty") or "").strip()[:20],
        })
    return title, normalized


def activity_questions(activity):
    return json.loads(activity["config_json"]).get("questions", [])


def activity_question_map(activity):
    return {question["id"]: question for question in activity_questions(activity)}


def public_question(question, shuffle_answers):
    answers = [{"original_index": index, "text": text} for index, text in enumerate(question["answers"])]
    if shuffle_answers:
        random.shuffle(answers)
    return {
        "id": question["id"], "type": question["type"], "question": question["question"],
        "text": question.get("text"), "answers": answers, "code": question.get("code"),
        "difficulty": question.get("difficulty"),
    }


def compute_rank(percent):
    if percent == 100:
        return "Guido van Rossum?"
    if percent >= 95:
        return "Senior detected"
    if percent >= 80:
        return "Strong Developer"
    if percent >= 60:
        return "Python Enjoyer"
    if percent >= 40:
        return "Junior survivor"
    return "print('help')"
