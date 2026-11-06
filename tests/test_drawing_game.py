import base64
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

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
        code = conn.execute('SELECT code FROM rooms WHERE id = ?', (self.room_id,)).fetchone()['code']
        conn.close()
        self.players = [server.app.test_client() for _ in range(3)]
        for i, player in enumerate(self.players):
            player.post('/join', data={'name': f'Player {i}', 'code': code})

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
        choice = state['drawings'][0]['id']
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':1,'drawing_id':choice}).status_code, 403)
        voter.post('/api/voting/join')
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':1,'drawing_id':choice}).status_code, 200)
        self.assertEqual(voter.post('/api/drawing/vote', json={'round':1,'drawing_id':choice}).status_code, 409)
        own = next(w for w in a.get('/api/drawing/current').get_json()['drawings'] if w['own'])
        a.post('/api/voting/join')
        self.assertEqual(a.post('/api/drawing/vote', json={'round':1,'drawing_id':own['id']}).status_code, 403)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':1,'phase':'voting'}).status_code, 200)
        self.assertEqual(host.post('/api/drawing/advance', json={'round':2,'phase':'drawing'}).status_code, 200)
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

    def test_duel_requires_explicit_voting_membership(self):
        self.host.post('/api/lobby/start', json={'mode':'self_paced'})
        self.assertEqual(self.host.post('/api/admin/roulette', json={'question':'Question?'}).status_code, 201)
        for player in self.players:
            current = player.get('/api/roulette/current').get_json()['round']
            if current['can_answer']:
                player.post('/api/roulette/answer', json={'answer':'Answer'})
        spectator = next(p for p in self.players if not any(x['student_id'] == p.get('/api/lobby').get_json()['viewer_id'] for x in p.get('/api/roulette/current').get_json()['round']['participants']))
        current = spectator.get('/api/roulette/current').get_json()['round']
        choice = current['participants'][0]['student_id']
        self.assertFalse(current['can_vote'])
        self.assertEqual(spectator.post('/api/roulette/vote', json={'choice_student_id':choice}).status_code, 403)
        spectator.post('/api/voting/join')
        self.assertTrue(spectator.get('/api/roulette/current').get_json()['round']['can_vote'])
        self.assertEqual(spectator.post('/api/roulette/vote', json={'choice_student_id':choice}).status_code, 200)

if __name__ == '__main__':
    unittest.main()
