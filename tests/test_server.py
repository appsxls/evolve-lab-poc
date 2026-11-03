"""HTTP regression tests using isolated state and an ephemeral loopback server."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server
from agents import AgentNotConfiguredError, CloudAgent


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in {'RUNTIME': root / 'runtime', 'STATE': root / 'runtime/state.json',
                            'APP': root / 'app', 'JOBS': {},
                            'STATE_DATA': copy.deepcopy(server.STATE_DATA), 'AGENT': CloudAgent()}.items():
            patcher = patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        server.APP.mkdir()
        server.init()
        self.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def request(self, method, path, payload=None):
        conn = http.client.HTTPConnection(*self.httpd.server_address, timeout=3)
        try:
            conn.request(method, path, body=json.dumps(payload) if payload is not None else None)
            response = conn.getresponse()
            data = response.read()
            return response.status, json.loads(data) if response.getheader('Content-Type', '').startswith('application/json') else data
        finally:
            conn.close()

    def test_crud_and_persistence(self):
        status, task = self.request('POST', '/api/tasks', {'title': ' New task '})
        self.assertEqual(status, 201)
        self.assertEqual(task['title'], 'New task')
        path = '/api/tasks/' + task['id']
        self.assertIn(task, self.request('GET', '/api/tasks')[1])
        status, updated = self.request('PATCH', path, {'title': 'Updated', 'done': True})
        self.assertEqual(status, 200)
        self.assertTrue(updated['done'])
        self.assertEqual(updated['title'], 'Updated')
        self.assertIn(updated, json.loads(server.STATE.read_text())['tasks'])
        server.STATE_DATA['tasks'] = []
        server.init()
        self.assertIn(updated, server.STATE_DATA['tasks'])
        self.assertEqual(self.request('DELETE', path), (200, {'ok': True}))
        self.assertEqual(self.request('PATCH', path, {'done': False})[0], 404)
        self.assertEqual(self.request('DELETE', path)[0], 404)
        self.assertEqual(self.request('POST', '/api/tasks', {'title': ' '})[0], 400)

    def test_init_needs_no_git_and_preserves_source(self):
        source = server.APP / 'index.html'
        source.write_text('existing source')
        with patch.dict('os.environ', {'PATH': ''}):
            server.init()
            status, data = self.request('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertFalse(data['agent']['configured'])
        self.assertFalse(data['codexEnabled'])
        self.assertFalse((server.APP / '.git').exists())
        self.assertEqual(source.read_text(), 'existing source')
        self.assertEqual(self.request('GET', '/app/index.html'), (200, b'existing source'))
        self.assertEqual(self.request('GET', '/')[0], 200)

    def test_unconfigured_job_fails_and_cannot_be_approved(self):
        with patch.dict('os.environ', {'POC_ALLOW_CODEX': '1'}):
            status, job = self.request('POST', '/api/jobs', {'request': 'Add a dark mode switch'})
        self.assertEqual(status, 202)
        for _ in range(100):
            status, job = self.request('GET', '/api/jobs/' + job['id'])
            if job['status'] == 'failed':
                break
            time.sleep(.01)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('not configured', job['error'])
        self.assertEqual(job['events'][-1]['kind'], 'error')
        self.assertEqual(job['diff'], '')
        self.assertNotIn('workspace', job)
        self.assertEqual(self.request('GET', '/api/jobs')[1], [job])
        self.assertEqual(self.request('POST', '/api/jobs/' + job['id'] + '/approve', {})[0], 409)
        self.assertEqual(self.request('GET', '/preview/' + job['id'] + '/index.html')[0], 404)
        self.assertEqual(self.request('GET', '/api/jobs/missing')[0], 404)
        self.assertEqual(self.request('POST', '/api/jobs', {'request': 'short'})[0], 400)

    def test_server_delegates_request_and_reports_adapter_errors(self):
        class FailingAgent:
            def execute(self, request):
                self.request = request
                raise RuntimeError('worker unavailable')
        adapter = FailingAgent()
        server.AGENT = adapter
        server.JOBS['test'] = {'request': 'Change the frontend', 'events': []}
        server.run_job('test')
        self.assertEqual(adapter.request, 'Change the frontend')
        self.assertEqual(server.JOBS['test']['status'], 'failed')
        self.assertEqual(server.JOBS['test']['error'], 'worker unavailable')

    def test_cloud_adapter_explicitly_refuses_execution(self):
        with self.assertRaisesRegex(AgentNotConfiguredError, 'not configured'):
            CloudAgent().execute('Build a feature')


if __name__ == '__main__':
    unittest.main()
