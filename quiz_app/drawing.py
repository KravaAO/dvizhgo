"""Room drawing game and seven-day drawing retention."""
import base64
import binascii
import json
import secrets
import struct
import threading
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for
from quiz_app.services.room_runtime import get_activity, get_runtime, now_iso, set_runtime

bp = Blueprint("drawing", __name__)
_cleanup_started = False


def api():
    from quiz_app import routes
    return routes


def cleanup():
    conn = api().get_db()
    try:
        conn.execute("DELETE FROM drawing_votes WHERE drawing_id IN (SELECT id FROM drawings WHERE expires_at <= ?)", (now_iso(),))
        conn.execute("DELETE FROM drawings WHERE expires_at <= ?", (now_iso(),))
        conn.commit()
    finally:
        conn.close()


def start_cleanup():
    global _cleanup_started
    if _cleanup_started:
        return
    _cleanup_started = True
    def worker():
        while True:
            try:
                cleanup()
            except Exception:
                api().app.logger.exception("Drawing cleanup failed")
            threading.Event().wait(60)
    threading.Thread(target=worker, daemon=True, name="drawing-retention").start()


def identity(conn):
    r = api()
    participant = r.current_participant(conn)
    host = r.find_host_room(conn, session.get("host_room_id"), session.get("host_access_token"))
    return participant, host


def current(conn, room_id):
    runtime = get_runtime(conn, room_id)
    activity = get_activity(conn, runtime["current_activity_id"])
    return activity if activity and activity["type"] == "drawing" else None


def validated_settings(data):
    prompts = data.get("prompts")
    rounds = data.get("rounds", 3)
    if not isinstance(prompts, list) or not all(isinstance(p, str) and 0 < len(p.strip()) <= 200 for p in prompts):
        raise ValueError("Додайте непорожні теми до 200 символів кожна.")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 30:
        raise ValueError("Кількість раундів має бути від 1 до 30.")
    if len(prompts) < rounds or len(prompts) > 30:
        raise ValueError("Додайте окрему тему для кожного раунду (до 30 тем).")
    return {"prompts": [p.strip() for p in prompts], "rounds": rounds}


@bp.route('/api/drawing/settings', methods=['GET', 'POST'])
def settings_route():
    room = api().get_current_host_room()
    if not room:
        return jsonify(error="Немає доступу."), 401
    conn = api().get_db()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room['id'],)).fetchone()
    settings = json.loads(room['settings_json'] or '{}')
    if request.method == 'POST':
        if room['status'] != 'lobby':
            conn.close()
            return jsonify(error="Налаштування доступні в лобі."), 409
        try:
            settings['drawing'] = validated_settings(request.get_json(silent=True) or {})
        except ValueError as error:
            conn.close()
            return jsonify(error=str(error)), 400
        conn.execute('UPDATE rooms SET settings_json = ? WHERE id = ?', (json.dumps(settings, ensure_ascii=False), room['id']))
        conn.commit()
    conn.close()
    return jsonify(settings=settings.get('drawing', {'rounds': 3, 'prompts': []}))


@bp.post('/api/drawing/start')
def start():
    room = api().get_current_host_room()
    if not room:
        return jsonify(error="Немає доступу."), 401
    conn = api().get_db()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room['id'],)).fetchone()
    if room['status'] != 'lobby' or get_runtime(conn, room['id'])['current_activity_id']:
        conn.close()
        return jsonify(error="Спершу завершіть поточну активність."), 409
    try:
        config = validated_settings(json.loads(room['settings_json'] or '{}').get('drawing', {}))
    except ValueError as error:
        conn.close()
        return jsonify(error=str(error)), 400
    config.update(round=1, phase='drawing')
    activity_id = conn.insert_and_get_id("INSERT INTO activities (room_id, type, status, config_json, started_at) VALUES (?, 'drawing', 'active', ?, ?)", (room['id'], json.dumps(config, ensure_ascii=False), now_iso()))
    set_runtime(conn, room['id'], activity_id, 'active')
    conn.execute("UPDATE rooms SET status = 'active' WHERE id = ?", (room['id'],))
    conn.commit()
    conn.close()
    api().emit_room_state(room['id'])
    return jsonify(ok=True)


@bp.get('/drawing')
def page():
    conn = api().get_db()
    participant, host = identity(conn)
    room_id = participant['room_id'] if participant else host['id'] if host else None
    activity = current(conn, room_id) if room_id else None
    conn.close()
    if not activity:
        return redirect(url_for('index'))
    return render_template('drawing.html', is_host=bool(host))


def state(conn, activity, participant, is_host):
    config = json.loads(activity['config_json'])
    rows = conn.execute('SELECT * FROM drawings WHERE activity_id = ? AND expires_at > ? ORDER BY round_number, share_token', (activity['id'], now_iso())).fetchall()
    number, phase = config['round'], config['phase']
    result = {'round': number, 'rounds': config['rounds'], 'phase': phase,
              'prompt': config['prompts'][number - 1], 'is_host': is_host,
              'voting_joined': api().voting_joined(participant), 'submitted': bool(participant and any(r['round_number'] == number and r['participant_id'] == participant['id'] for r in rows))}
    if phase == 'voting':
        vote = conn.execute('SELECT drawing_id FROM drawing_votes WHERE activity_id = ? AND round_number = ? AND voter_id = ?', (activity['id'], number, participant['id'] if participant else -1)).fetchone()
        result['voted'] = bool(vote)
        result['drawings'] = [{'id': row['id'], 'url': url_for('drawing.image', token=row['share_token']), 'own': bool(participant and row['participant_id'] == participant['id'])} for row in rows if row['round_number'] == number]
    elif phase == 'results':
        counts = conn.execute('SELECT drawing_id, COUNT(*) AS n FROM drawing_votes WHERE activity_id = ? GROUP BY drawing_id', (activity['id'],)).fetchall()
        votes = {r['drawing_id']: r['n'] for r in counts}
        winners = []
        for n in range(1, config['rounds'] + 1):
            works = [r for r in rows if r['round_number'] == n]
            best = max((votes.get(r['id'], 0) for r in works), default=0)
            winners.append({'round': n, 'prompt': config['prompts'][n-1], 'names': [r['author'] for r in works if best and votes.get(r['id'], 0) == best]})
        result['winners'] = winners
        result['drawings'] = [{'url': url_for('drawing.image', token=r['share_token']), 'author': r['author'], 'prompt': r['prompt'], 'round': r['round_number'], 'expires_at': r['expires_at']} for r in rows]
    return result


@bp.get('/api/drawing/current')
def get_state():
    conn = api().get_db()
    participant, host = identity(conn)
    room_id = participant['room_id'] if participant else host['id'] if host else None
    activity = current(conn, room_id) if room_id else None
    if not activity:
        conn.close()
        return jsonify(error='Немає активної малювалки.'), 404
    payload = state(conn, activity, participant, bool(host))
    conn.close()
    return jsonify(payload)


@bp.post('/api/drawing/submit')
def submit():
    data = request.get_json(silent=True) or {}
    image = data.get('image', '')
    if not isinstance(image, str) or not image.startswith('data:image/png;base64,') or len(image) > 1400000:
        return jsonify(error='Невірний або завеликий малюнок.'), 400
    try:
        raw = base64.b64decode(image.split(',', 1)[1], validate=True)
        if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR' or not (1 <= len(raw) <= 1000000):
            raise ValueError()
        width, height = struct.unpack('>II', raw[16:24])
        if not (1 <= width <= 2048 and 1 <= height <= 2048):
            raise ValueError()
    except (ValueError, binascii.Error, struct.error):
        return jsonify(error='Невірний формат малюнка.'), 400
    conn = api().get_db()
    participant, _ = identity(conn)
    activity = current(conn, participant['room_id']) if participant else None
    if not activity:
        conn.close()
        return jsonify(error='Немає активної гри.'), 403
    config = json.loads(activity['config_json'])
    if config['phase'] != 'drawing' or data.get('round') != config['round']:
        conn.close()
        return jsonify(error='Цей раунд уже завершено.'), 409
    existing = conn.execute('SELECT id FROM drawings WHERE activity_id = ? AND round_number = ? AND participant_id = ?', (activity['id'], config['round'], participant['id'])).fetchone()
    if existing:
        conn.close()
        return jsonify(error='Малюнок уже надіслано.'), 409
    now = datetime.now()
    conn.execute('INSERT INTO drawings (activity_id, room_id, round_number, participant_id, author, prompt, image, share_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (activity['id'], participant['room_id'], config['round'], participant['id'], participant['display_name'], config['prompts'][config['round']-1], image, secrets.token_urlsafe(32), now.isoformat(timespec='seconds'), (now + timedelta(days=7)).isoformat(timespec='seconds')))
    conn.commit()
    conn.close()
    api().emit_room_event(participant['room_id'], 'room:drawing_updated')
    return jsonify(ok=True)


@bp.post('/api/drawing/vote')
def vote():
    data = request.get_json(silent=True) or {}
    conn = api().get_db()
    participant, _ = identity(conn)
    activity = current(conn, participant['room_id']) if participant else None
    if not activity or not api().voting_joined(participant):
        conn.close()
        return jsonify(error='Спершу приєднайтеся до голосування.'), 403
    config = json.loads(activity['config_json'])
    if config['phase'] != 'voting' or data.get('round') != config['round']:
        conn.close()
        return jsonify(error='Голосування не активне.'), 409
    work = conn.execute('SELECT * FROM drawings WHERE id = ? AND activity_id = ? AND round_number = ? AND expires_at > ?', (data.get('drawing_id'), activity['id'], config['round'], now_iso())).fetchone()
    if not work or work['participant_id'] == participant['id']:
        conn.close()
        return jsonify(error='Не можна голосувати за цю роботу.'), 403
    existing = conn.execute('SELECT 1 FROM drawing_votes WHERE activity_id = ? AND round_number = ? AND voter_id = ?', (activity['id'], config['round'], participant['id'])).fetchone()
    if existing:
        conn.close()
        return jsonify(error='Ваш голос уже зараховано.'), 409
    conn.execute('INSERT INTO drawing_votes (activity_id, round_number, voter_id, drawing_id) VALUES (?, ?, ?, ?)', (activity['id'], config['round'], participant['id'], work['id']))
    conn.commit()
    conn.close()
    api().emit_room_event(participant['room_id'], 'room:drawing_updated')
    return jsonify(ok=True)


@bp.post('/api/drawing/advance')
def advance():
    host = api().get_current_host_room()
    if not host:
        return jsonify(error='Немає доступу.'), 401
    conn = api().get_db()
    activity = current(conn, host['id'])
    if not activity:
        conn.close()
        return jsonify(error='Немає активної гри.'), 409
    config = json.loads(activity['config_json'])
    data = request.get_json(silent=True) or {}
    if data.get('phase') != config['phase'] or data.get('round') != config['round']:
        conn.close()
        return jsonify(error='Стан гри змінився. Оновіть сторінку.'), 409
    if config['phase'] == 'drawing':
        config['phase'] = 'voting'
    elif config['phase'] == 'voting':
        if config['round'] < config['rounds']:
            config['round'] += 1
            config['phase'] = 'drawing'
        else:
            config['phase'] = 'results'
    else:
        conn.execute("UPDATE activities SET status = 'finished', finished_at = ? WHERE id = ?", (now_iso(), activity['id']))
        set_runtime(conn, host['id'], None, 'lobby')
        conn.execute("UPDATE rooms SET status = 'lobby' WHERE id = ?", (host['id'],))
        conn.commit()
        conn.close()
        api().emit_room_state(host['id'])
        return jsonify(ok=True)
    conn.execute('UPDATE activities SET config_json = ? WHERE id = ?', (json.dumps(config, ensure_ascii=False), activity['id']))
    conn.commit()
    conn.close()
    api().emit_room_event(host['id'], 'room:drawing_updated')
    return jsonify(ok=True)


@bp.get('/drawings/<token>.png')
def image(token):
    conn = api().get_db()
    row = conn.execute('SELECT * FROM drawings WHERE share_token = ? AND expires_at > ?', (token, now_iso())).fetchone()
    if row:
        activity = get_activity(conn, row['activity_id'])
        config = json.loads(activity['config_json']) if activity else None
        participant, host = identity(conn)
        # During the drawing phase only the artist can view their unpublished work.
        if config and config.get('phase') == 'drawing' and config.get('round') == row['round_number'] and not (participant and participant['id'] == row['participant_id']):
            row = None
    conn.close()
    if not row:
        return '', 404
    response = Response(base64.b64decode(row['image'].split(',', 1)[1]), mimetype='image/png')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
