import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import app as app_module


class DeleteRouteTest(unittest.TestCase):
    def setUp(self):
        app_module.tasks.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = app_module.app.test_client()
        self.path = Path(self.tmp.name) / 'published.json'
        self.record = {
            'channel': 'news',
            'job': 'job-1',
            'kind': 'short',
            'video_id': 'vid-123',
            'title': 'Test video',
            'timestamp': '2026-01-01T00:00:00+0000',
        }
        self.body = {
            'channel': 'news',
            'job': 'job-1',
            'kind': 'short',
            'video_id': 'vid-123',
        }

    def _base(self, find_result, delete_result=None, active=False):
        stack = ExitStack()
        mocks = {}
        mocks['find_record'] = stack.enter_context(patch('publisher_logic.find_record', return_value=find_result))
        mocks['config'] = stack.enter_context(patch('publisher_logic.config', return_value={}))
        mocks['destination'] = stack.enter_context(patch('publisher_logic.destination', return_value=Path(self.tmp.name) / 'dest'))
        mocks['load_global'] = stack.enter_context(patch('youtube_publisher.load_global'))
        mocks['load_channel'] = stack.enter_context(patch('youtube_publisher.load_channel', return_value=(None, {'youtube_channel_name': 'Test Channel'})))
        mocks['write_json'] = stack.enter_context(patch('youtube_publisher.write_json'))
        mocks['delete_video'] = stack.enter_context(patch('studio_automation.delete_video', return_value=delete_result or {'deleted': True, 'already_gone': False}))
        mocks['browser_lock'] = stack.enter_context(patch('app.browser_lock'))   # a real lock's methods cannot be patched
        mocks['browser_lock'].acquire.return_value = True
        mocks['os_open'] = stack.enter_context(patch('app.os.open', return_value=7))
        mocks['os_close'] = stack.enter_context(patch('app.os.close'))
        mocks['unlink'] = stack.enter_context(patch('pathlib.Path.unlink'))
        app_module.tasks.clear()
        if active:
            app_module.tasks['active-test'] = {'status': 'running'}
        return stack, mocks

    def test_happy_path_marks_record(self):
        stack, mocks = self._base((self.path, self.record), {'deleted': True, 'already_gone': False})
        with stack:
            response = self.client.post('/delete', json=self.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'deleted': True, 'video_id': 'vid-123'})
        mocks['delete_video'].assert_called_once()
        written_path, written_record = mocks['write_json'].call_args.args
        self.assertEqual(written_path, self.path)
        self.assertTrue(written_record['deleted'])
        self.assertEqual(written_record['video_id'], 'vid-123')
        self.assertIn('deleted_at', written_record)

    def test_already_deleted_is_idempotent(self):
        record = dict(self.record, deleted=True)
        stack, mocks = self._base((self.path, record))
        with stack:
            response = self.client.post('/delete', json=self.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'deleted': True, 'video_id': 'vid-123'})
        mocks['delete_video'].assert_not_called()
        mocks['write_json'].assert_not_called()

    def test_video_id_mismatch_is_400(self):
        record = dict(self.record, video_id='other-video')
        stack, mocks = self._base((self.path, record))
        with stack:
            response = self.client.post('/delete', json=self.body)

        self.assertEqual(response.status_code, 400)
        self.assertIn('video_id', response.json['error'])
        mocks['delete_video'].assert_not_called()
        mocks['write_json'].assert_not_called()

    def test_no_record_returns_404(self):
        stack, mocks = self._base((None, None))
        with stack:
            response = self.client.post('/delete', json=self.body)

        self.assertEqual(response.status_code, 404)
        mocks['delete_video'].assert_not_called()

    def test_dry_run_does_not_mark_record(self):
        stack, mocks = self._base((self.path, self.record), {'deleted': False, 'already_gone': False, 'dry_run': True})
        with stack:
            response = self.client.post('/delete?dry_run=1', json=self.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'deleted': False, 'dry_run': True, 'video_id': 'vid-123'})
        mocks['write_json'].assert_not_called()
        self.assertTrue(mocks['delete_video'].call_args.kwargs['dry_run'])

    def test_active_publish_task_is_refused(self):
        stack, mocks = self._base((self.path, self.record), {'deleted': True}, active=True)
        with stack:
            response = self.client.post('/delete', json=self.body)

        self.assertEqual(response.status_code, 400)
        self.assertIn('active', response.json['error'].lower())
        mocks['delete_video'].assert_not_called()
        mocks['write_json'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
