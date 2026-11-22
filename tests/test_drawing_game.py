import base64
import json
import sqlite3
import struct
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
import zlib

from quiz_app import routes as server
from quiz_app import drawing
from quiz_app.database import initialize_database

PNG = 'data:image/png;base64,' + base64.b64encode(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aS8AAAAASUVORK5CYII=')).decode()


def white_png(width):
    """A valid white PNG, width x 1, to tell saved pictures apart."""
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    header = struct.pack('>IIBBBBB', width, 1, 8, 0, 0, 0, 0)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b'\x00' + b'\xff' * width)) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(data).decode()

class DrawingGameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_url, self.old_path = server.DATABASE_URL, server.DB_PATH
        server.DB_PATH = Path(self.tmp.name, 'test.sqlite')
        server.DATABASE_URL = 'sqlite:///' + server.DB_PATH.as_posix()
        server.app.config['TESTING'] = True
        server.init_db()
        self.host = server.app.test_client()
        self.host.post('/rooms')
        with self.host.session_transaction() as sess:
            self.room_id = sess['room_id']
        conn = server.get_db()
        self.room_code = conn.execute('SELECT code FROM rooms WHERE id = ?', (self.room_id,)).fetchone()['code']
        conn.close()
        self.players = [server.app.test_client() for _ in range(3)]
        for i, player in enumerate(self.players):
            player.post('/join', data={'name': f'Player {i}', 'code': self.room_code})

    def tearDown(self):
        server.DATABASE_URL, server.DB_PATH = self.old_url, self.old_path
        self.tmp.cleanup()

    def test_rounds_voting_anonymity_sharing_and_expiry(self):
        host = self.host
        a, b, voter = self.players
        self.assertEqual(host.post('/api/drawing/settings', json={'prompts':[]}).status_code, 400)
        self.assertEqual(host.post('/api/drawing/settings', json={'prompts':['one','two']}).status_code, 200)
        self.assertEqual(host.post('/api/drawing/start').status_code, 200)
        self.assertTrue(a.get('/lobby').location.endswith('/drawing'))
        self.assertTrue(host.get('/admin').location.endswith('/drawing'))
        for player in (a,b):
            self.assertEqual(player.post('/api/drawing/submit', json={'round':1,'image':PNG}).status_code, 200)
        self.assertEqual(a.post('/api/drawing/submit', json={'round':1,'image':PNG}).status_code, 409)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':1,'phase':'drawing'}).status_code, 200)
        state = voter.get('/api/drawing/current').get_json()
        self.assertEqual(len(state['drawings']), 2)
        self.assertNotIn('author', state['drawings'][0])
        self.assertTrue(state['can_vote'])
        choice = state['drawings'][0]['id']
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':1,'drawing_id':choice}).status_code, 200)
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':1,'drawing_id':choice}).status_code, 409)
        self.assertFalse(voter.get('/api/drawing/current').get_json()['can_vote'])
        self.assertFalse(host.get('/api/drawing/current').get_json()['can_vote'])
        own = next(w for w in a.get('/api/drawing/current').get_json()['drawings'] if w['own'])
        self.assertEqual(a.post('/api/drawing/vote', json={'round':1,'drawing_id':own['id']}).status_code, 403)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':1,'phase':'voting'}).status_code, 200)
        self.assertEqual(a.post('/api/drawing/submit', json={'round':2,'image':PNG}).status_code, 200)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':2,'phase':'drawing'}).status_code, 200)
        late = server.app.test_client()
        self.assertTrue(late.post('/join', data={'name':'Late', 'code':self.room_code}).location.endswith('/drawing'))
        state = late.get('/api/drawing/current').get_json()
        self.assertTrue(state['can_vote'])
        second_work = state['drawings'][0]['id']
        self.assertEqual(late.post('/api/drawing/vote', json={'round':2,'drawing_id':second_work}).status_code, 200)
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':2,'drawing_id':second_work}).status_code, 200)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':2,'phase':'voting'}).status_code, 200)
        result = voter.get('/api/drawing/current').get_json()
        self.assertEqual(result['phase'], 'results')
        self.assertEqual(len(result['winners'][0]['names']), 1)
        self.assertNotIn('votes', json.dumps(result))
        link = result['drawings'][0]['url']
        self.assertEqual(server.app.test_client().get(link).status_code, 200)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':2,'phase':'results'}).status_code, 200)
        self.assertEqual(server.app.test_client().get(link).status_code, 200)
        conn = server.get_db()
        conn.execute('UPDATE drawings SET expires_at = ?', ((datetime.now()-timedelta(seconds=1)).isoformat(timespec='seconds'),))
        conn.commit(); conn.close()
        self.assertEqual(server.app.test_client().get(link).status_code, 404)
        drawing.cleanup()
        conn = server.get_db()
        self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM drawings').fetchone()['n'], 0)
        self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM drawing_votes').fetchone()['n'], 0)
        conn.close()

    def test_published_pictures_are_cached_until_the_link_expires(self):
        host = self.host
        a, b, _ = self.players
        host.post('/api/drawing/settings', json={'prompts':['one']})
        host.post('/api/drawing/start')
        self.assertEqual(a.post('/api/drawing/submit', json={'round':1,'image':PNG}).status_code, 200)
        conn = server.get_db()
        link = '/drawings/%s.png' % conn.execute('SELECT share_token FROM drawings').fetchone()['share_token']
        conn.close()
        # Still drawing: the artist sees it uncached, everyone else gets an uncached 404.
        own = a.get(link)
        self.assertEqual((own.status_code, own.headers['Cache-Control']), (200, 'no-store'))
        hidden = b.get(link)
        self.assertEqual((hidden.status_code, hidden.headers['Cache-Control']), (404, 'no-store'))
        self.assertEqual(host.post('/api/drawing/advance', json={'round':1,'phase':'drawing'}).status_code, 200)
        published = b.get(link)
        self.assertEqual(published.status_code, 200)
        cache = published.headers['Cache-Control']
        self.assertTrue(cache.startswith('private, max-age=') and cache.endswith(', immutable'), cache)
        max_age = int(cache.split('max-age=')[1].split(',')[0])
        self.assertTrue(7 * 86400 - 60 <= max_age <= 7 * 86400, max_age)
        self.assertEqual(drawing.image_cache_control((datetime.now() - timedelta(seconds=5)).isoformat(), False), 'no-store')

    def set_round_deadline(self, seconds_from_now):
        conn = server.get_db()
        row = conn.execute("SELECT id, config_json FROM activities WHERE type = 'drawing' AND status = 'active'").fetchone()
        config = json.loads(row['config_json'])
        config['ends_at'] = (datetime.now() + timedelta(seconds=seconds_from_now)).isoformat(timespec='milliseconds')
        conn.execute('UPDATE activities SET config_json = ? WHERE id = ?', (json.dumps(config), row['id']))
        conn.commit(); conn.close()

    def test_time_limit_is_validated_counted_down_and_enforced(self):
        host = self.host
        a, b, _ = self.players
        base = {'prompts': ['one', 'two']}
        for invalid in (45, 0, '60', True, 3600):
            self.assertEqual(host.post('/api/drawing/settings', json={**base, 'time_limit': invalid}).status_code, 400)
        saved = host.post('/api/drawing/settings', json={**base, 'time_limit': 30}).get_json()['settings']
        self.assertEqual(saved['time_limit'], 30)
        self.assertIn(b'value="30" checked', host.get('/admin/drawing').data)
        self.assertEqual(host.post('/api/drawing/start').status_code, 200)

        state = a.get('/api/drawing/current').get_json()
        self.assertEqual(state['time_limit'], 30)
        self.assertTrue(25000 < state['time_left_ms'] <= 30000)
        self.assertEqual(state['submit_grace_ms'], drawing.SUBMIT_GRACE_SECONDS * 1000)

        # An auto-submit that lands inside the grace window is accepted...
        self.set_round_deadline(-(drawing.SUBMIT_GRACE_SECONDS - 2))
        self.assertEqual(a.get('/api/drawing/current').get_json()['time_left_ms'], 0)
        self.assertEqual(a.post('/api/drawing/submit', json={'round': 1, 'image': PNG}).status_code, 200)
        # ...but anything later is rejected.
        self.set_round_deadline(-(drawing.SUBMIT_GRACE_SECONDS + 1))
        late = b.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        self.assertEqual(late.status_code, 409)

        # The next round gets a fresh timer; voting carries no countdown.
        self.assertEqual(host.post('/api/drawing/advance', json={'round': 1, 'phase': 'drawing'}).status_code, 200)
        self.assertNotIn('time_left_ms', host.get('/api/drawing/current').get_json())
        self.assertEqual(host.post('/api/drawing/advance', json={'round': 1, 'phase': 'voting'}).status_code, 200)
        self.assertTrue(25000 < a.get('/api/drawing/current').get_json()['time_left_ms'] <= 30000)

    def phase(self):
        conn = server.get_db()
        row = conn.execute("SELECT config_json FROM activities WHERE type = 'drawing' AND status = 'active'").fetchone()
        conn.close()
        return json.loads(row['config_json'])['phase']

    def start_drawing(self, rounds=2):
        prompts = ['one', 'two', 'three'][:rounds]
        self.assertEqual(self.host.post('/api/drawing/settings', json={'prompts': prompts, 'time_limit': 60}).status_code, 200)
        self.assertEqual(self.host.post('/api/drawing/start').status_code, 200)

    def test_voting_opens_only_after_every_online_player_submitted(self):
        self.start_drawing()
        a, b, c = self.players
        a.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        state = self.host.get('/api/drawing/current').get_json()
        self.assertEqual((state['phase'], state['submitted_count'], state['expected_count']), ('drawing', 1, 3))
        b.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        self.assertEqual(self.phase(), 'drawing')
        # Voting is refused while pictures are still missing.
        self.assertEqual(a.post('/api/drawing/vote', json={'round': 1, 'drawing_id': 1}).status_code, 409)
        # The last picture opens voting without any host action.
        self.assertEqual(c.post('/api/drawing/submit', json={'round': 1, 'image': PNG}).status_code, 200)
        self.assertEqual(self.phase(), 'voting')
        state = c.get('/api/drawing/current').get_json()
        self.assertEqual(len(state['drawings']), 3)
        self.assertTrue(state['can_vote'])

    def test_offline_players_do_not_block_voting(self):
        self.start_drawing()
        a, b, c = self.players
        conn = server.get_db()
        stale = (datetime.now() - timedelta(seconds=drawing.PRESENCE_WINDOW_SECONDS + 5)).isoformat(timespec='seconds')
        conn.execute("UPDATE room_participants SET last_seen_at = ? WHERE display_name = 'Player 2'", (stale,))
        conn.commit(); conn.close()
        a.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        self.assertEqual(b.post('/api/drawing/submit', json={'round': 1, 'image': PNG}).status_code, 200)
        self.assertEqual(self.phase(), 'voting')

    def test_deadline_opens_voting_and_host_can_end_drawing_early(self):
        self.start_drawing()
        a, _, _ = self.players
        a.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        self.set_round_deadline(-(drawing.SUBMIT_GRACE_SECONDS - 2))
        self.assertEqual(a.get('/api/drawing/current').get_json()['phase'], 'drawing')
        self.set_round_deadline(-(drawing.SUBMIT_GRACE_SECONDS + 1))
        self.assertEqual(a.get('/api/drawing/current').get_json()['phase'], 'voting')
        # Round two: the host skips the wait while two players are still drawing.
        self.assertEqual(self.host.post('/api/drawing/advance', json={'round': 1, 'phase': 'voting'}).status_code, 200)
        self.assertEqual(a.post('/api/drawing/submit', json={'round': 2, 'image': PNG}).status_code, 200)
        self.assertEqual(self.phase(), 'drawing')
        self.assertEqual(self.host.post('/api/drawing/advance', json={'round': 2, 'phase': 'drawing'}).status_code, 200)
        self.assertEqual(self.phase(), 'voting')

    def test_vote_progress_counts_only_players_with_something_to_vote_for(self):
        self.start_drawing()
        a, b, c = self.players
        a.post('/api/drawing/submit', json={'round': 1, 'image': PNG})
        self.assertEqual(self.host.post('/api/drawing/advance', json={'round': 1, 'phase': 'drawing'}).status_code, 200)
        state = self.host.get('/api/drawing/current').get_json()
        # The only picture is A's, so A has nothing to vote for.
        self.assertEqual((state['votes_count'], state['voters_count']), (0, 2))
        work = state['drawings'][0]['id']
        self.assertEqual(b.post('/api/drawing/vote', json={'round': 1, 'drawing_id': work}).status_code, 200)
        self.assertEqual(b.get('/api/drawing/current').get_json()['voted_for'], work)
        self.assertIsNone(c.get('/api/drawing/current').get_json()['voted_for'])
        conn = server.get_db()
        stale = (datetime.now() - timedelta(seconds=drawing.PRESENCE_WINDOW_SECONDS + 5)).isoformat(timespec='seconds')
        conn.execute("UPDATE room_participants SET last_seen_at = ? WHERE display_name IN ('Player 1', 'Player 2')", (stale,))
        conn.commit(); conn.close()
        # B went offline after voting and still counts; C stops being waited for.
        state = self.host.get('/api/drawing/current').get_json()
        self.assertEqual((state['votes_count'], state['voters_count']), (1, 1))

    def save_draft(self, client, round_number=1, image=PNG, blank=False):
        return client.post('/api/drawing/draft', json={'round': round_number, 'image': image, 'blank': blank})

    def test_autosaved_drafts_become_entries_when_time_runs_out(self):
        self.start_drawing()
        a, b, c = self.players
        self.assertEqual(self.save_draft(a).status_code, 200)
        self.assertEqual(self.save_draft(a, image=white_png(2)).status_code, 200)
        self.assertEqual(self.save_draft(b, image=white_png(3), blank=True).status_code, 200)
        # A reload brings the latest autosave back; C never opened the canvas.
        self.assertEqual(a.get('/api/drawing/draft').get_json()['image'], white_png(2))
        self.assertIsNone(c.get('/api/drawing/draft').get_json()['image'])
        self.assertEqual(self.host.post('/api/drawing/draft', json={'round': 1, 'image': PNG}).status_code, 401)
        self.assertEqual(self.save_draft(a, round_number=2).status_code, 409)
        self.assertEqual(a.post('/api/drawing/draft', json={'round': 1, 'image': 'data:image/png;base64,AAAA'}).status_code, 400)
        self.set_round_deadline(-(drawing.SUBMIT_GRACE_SECONDS + 1))
        self.assertEqual(self.save_draft(a).status_code, 409)
        state = c.get('/api/drawing/current').get_json()
        self.assertEqual(state['phase'], 'voting')
        self.assertEqual(sorted(work['blank'] for work in state['drawings']), [False, True])
        # A blank canvas is an ordinary entry: it can be shown and voted for.
        blank = next(work for work in state['drawings'] if work['blank'])
        self.assertEqual(c.post('/api/drawing/vote', json={'round': 1, 'drawing_id': blank['id']}).status_code, 200)
        conn = server.get_db()
        images = {row['author']: row['image'] for row in conn.execute('SELECT author, image FROM drawings').fetchall()}
        drafts_left = conn.execute('SELECT COUNT(*) AS n FROM drawing_drafts').fetchone()['n']
        conn.close()
        self.assertEqual(images, {'Player 0': white_png(2), 'Player 1': white_png(3)})
        self.assertEqual(drafts_left, 0)

    def test_ending_early_enters_drafts_except_for_players_who_left(self):
        self.start_drawing()
        a, b, c = self.players
        for player in (a, b):
            self.save_draft(player)
        self.save_draft(c, blank=True)
        # A blank canvas can be submitted on purpose; the draft is then gone.
        self.assertEqual(a.post('/api/drawing/submit', json={'round': 1, 'image': PNG, 'blank': True}).status_code, 200)
        self.assertIsNone(a.get('/api/drawing/draft').get_json()['image'])
        self.assertTrue(self.save_draft(a).get_json()['submitted'])
        conn = server.get_db()
        conn.execute("UPDATE room_participants SET left_at = ? WHERE display_name = 'Player 1'", (datetime.now().isoformat(timespec='seconds'),))
        conn.commit(); conn.close()
        self.assertEqual(self.host.post('/api/drawing/advance', json={'round': 1, 'phase': 'drawing'}).status_code, 200)
        works = self.host.get('/api/drawing/current').get_json()['drawings']
        self.assertEqual([work['blank'] for work in works].count(True), 2)
        self.assertEqual(len(works), 2)

    def test_existing_drawings_table_gets_the_blank_column(self):
        path = Path(self.tmp.name, 'old.sqlite')
        old = sqlite3.connect(path)
        old.execute('''CREATE TABLE drawings (id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id BIGINT NOT NULL,
            room_id BIGINT NOT NULL, round_number INTEGER NOT NULL, participant_id BIGINT NOT NULL,
            author TEXT NOT NULL, prompt TEXT NOT NULL, image TEXT NOT NULL, share_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL, UNIQUE(activity_id, round_number, participant_id))''')
        old.execute("INSERT INTO drawings VALUES (1, 1, 1, 1, 1, 'a', 'p', 'img', 'tok', 'x', 'y')")
        old.commit(); old.close()
        initialize_database('sqlite:///' + path.as_posix(), path)
        migrated = sqlite3.connect(path)
        self.assertEqual(migrated.execute('SELECT is_blank FROM drawings').fetchone()[0], 0)
        migrated.close()

    def test_round_count_follows_the_prompt_list(self):
        host = self.host
        saved = host.post('/api/drawing/settings', json={'rounds': 1, 'prompts': [' one ', 'two', 'three']}).get_json()['settings']
        self.assertEqual(saved['rounds'], 3)
        self.assertEqual(saved['prompts'], ['one', 'two', 'three'])
        page = host.get('/admin/drawing').data.decode()
        self.assertNotIn('name="rounds"', page)
        self.assertIn('>3</output>', page)
        self.assertIn('Раундів · 3 /', host.get('/lobby/host').data.decode())
        too_many = [f'theme {n}' for n in range(drawing.MAX_ROUNDS + 1)]
        self.assertEqual(host.post('/api/drawing/settings', json={'prompts': too_many}).status_code, 400)

    def test_rooms_saved_with_a_stale_round_count_play_every_prompt(self):
        conn = server.get_db()
        conn.execute('UPDATE rooms SET settings_json = ? WHERE id = ?', (json.dumps({'drawing': {'rounds': 1, 'prompts': ['a', 'b']}}), self.room_id))
        conn.commit(); conn.close()
        self.assertEqual(self.host.post('/api/drawing/start').status_code, 200)
        self.assertEqual(self.players[0].get('/api/drawing/current').get_json()['rounds'], 2)

    def test_rooms_saved_without_time_limit_use_the_default(self):
        conn = server.get_db()
        conn.execute('UPDATE rooms SET settings_json = ? WHERE id = ?', (json.dumps({'drawing': {'prompts': ['old']}}), self.room_id))
        conn.commit(); conn.close()
        self.assertIn('Час · 1:30'.encode(), self.host.get('/lobby/host').data)
        self.assertEqual(self.host.post('/api/drawing/start').status_code, 200)
        self.assertEqual(self.players[0].get('/api/drawing/current').get_json()['time_limit'], drawing.DEFAULT_TIME_LIMIT)

    def test_duel_spectator_votes_directly_and_duelists_cannot_vote(self):
        self.host.post('/api/lobby/start', json={'mode':'self_paced'})
        self.assertEqual(self.host.post('/api/admin/roulette', json={'question':'Question?'}).status_code, 201)
        duelists = []
        for player in self.players:
            current = player.get('/api/roulette/current').get_json()['round']
            if current['can_answer']:
                duelists.append(player)
                player.post('/api/roulette/answer', json={'answer':'Answer'})
        spectator = next(player for player in self.players if player not in duelists)
        current = spectator.get('/api/roulette/current').get_json()['round']
        choice = current['participants'][0]['student_id']
        self.assertTrue(current['can_vote'])
        for duelist in duelists:
            self.assertFalse(duelist.get('/api/roulette/current').get_json()['round']['can_vote'])
            self.assertEqual(duelist.post('/api/roulette/vote', json={'choice_student_id':choice}).status_code, 403)
        self.assertEqual(spectator.post('/api/roulette/vote', json={'choice_student_id':choice}).status_code, 200)
        self.assertEqual(spectator.post('/api/roulette/vote', json={'choice_student_id':choice}).status_code, 409)

    def test_saved_room_mode_and_content_drive_lobby_start(self):
        host = self.host
        self.assertEqual(host.get('/api/lobby').get_json()['room_mode'], 'quiz')
        self.assertEqual(self.players[0].post('/api/lobby/room-mode', json={'room_mode':'drawing'}).status_code, 401)
        quiz = host.post('/api/admin/quizzes', json={
            'title':'Selected quiz',
            'questions':[{'question':'Question?', 'answers':['Yes', 'No'], 'correct':[0]}],
        }).get_json()
        self.assertEqual(host.post(f"/api/admin/quizzes/{quiz['id']}/activate").status_code, 200)
        self.assertEqual(host.post('/api/lobby/room-mode', json={'room_mode':'drawing'}).status_code, 200)
        self.assertEqual(host.get('/api/lobby').get_json()['room_mode'], 'drawing')
        self.assertIn(b'id="startRoom"', host.get('/lobby/host').data)
        self.assertEqual(host.get('/admin/drawing').status_code, 200)
        stale = host.post('/api/lobby/start', json={'expected_room_mode':'quiz'})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()['room_mode'], 'drawing')
        self.assertEqual(host.post('/api/lobby/start', json={'expected_room_mode':'drawing'}).status_code, 400)
        config = {'prompts':['First']}
        self.assertEqual(host.post('/api/drawing/settings', json=config).status_code, 200)
        for mode in ('quiz', 'drawing'):
            self.assertEqual(host.post('/api/lobby/room-mode', json={'room_mode':mode}).status_code, 200)
        self.assertEqual(host.get('/api/drawing/settings').get_json()['settings'], {**config, 'rounds': 1, 'time_limit': drawing.DEFAULT_TIME_LIMIT})
        self.assertEqual(host.get('/api/admin/quizzes').get_json()['active_quiz_id'], quiz['id'])

        with host.session_transaction() as credentials:
            host_session = dict(credentials)
        barrier = Barrier(2)

        def start_drawing():
            with server.app.test_client() as client:
                with client.session_transaction() as session:
                    session.update(host_session)
                barrier.wait(timeout=5)
                return client.post('/api/lobby/start', json={'expected_room_mode':'drawing'})

        with ThreadPoolExecutor(max_workers=2) as executor:
            launches = [executor.submit(start_drawing) for _ in range(2)]
            results = [launch.result() for launch in launches]
        self.assertEqual(sorted(response.status_code for response in results), [200, 409])
        launched = next(response for response in results if response.status_code == 200)
        self.assertEqual(launched.get_json()['redirect_url'], '/drawing')
        self.assertEqual(host.get('/api/drawing/current').get_json()['prompt'], 'First')
        self.assertEqual(host.post('/api/lobby/room-mode', json={'room_mode':'quiz'}).status_code, 409)
        self.assertEqual(host.post('/api/drawing/settings', json=config).status_code, 409)
        for phase in ('drawing', 'voting', 'results'):
            self.assertEqual(host.post('/api/drawing/advance', json={'round':1,'phase':phase}).status_code, 200)
        self.assertEqual(host.get('/api/lobby').get_json()['room_mode'], 'drawing')
        self.assertEqual(host.post('/api/lobby/room-mode', json={'room_mode':'quiz'}).status_code, 200)
        launched = host.post('/api/lobby/start', json={'expected_room_mode':'quiz'})
        self.assertEqual(launched.status_code, 200)
        self.assertEqual(launched.get_json()['redirect_url'], '/admin')
        self.assertIn(b'Question?', self.players[0].get('/quiz').data)

if __name__ == '__main__':
    unittest.main()
