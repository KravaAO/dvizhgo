import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier

from quiz_app import routes as server
from quiz_app import drawing

PNG = 'data:image/png;base64,' + base64.b64encode(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aS8AAAAASUVORK5CYII=')).decode()

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
        self.assertEqual(host.post('/api/drawing/settings', json={'rounds':3,'prompts':['one']}).status_code, 400)
        self.assertEqual(host.post('/api/drawing/settings', json={'rounds':2,'prompts':['one','two']}).status_code, 200)
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
        config = {'rounds':1, 'prompts':['First', 'Extra']}
        self.assertEqual(host.post('/api/drawing/settings', json=config).status_code, 200)
        for mode in ('quiz', 'drawing'):
            self.assertEqual(host.post('/api/lobby/room-mode', json={'room_mode':mode}).status_code, 200)
        self.assertEqual(host.get('/api/drawing/settings').get_json()['settings'], config)
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
