import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as web
import publisher_logic as logic
import youtube_publisher as backend
from PIL import Image

class GuiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for module in (logic, backend, web):
            replacement = patch.object(module, 'ROOT', self.root)
            replacement.start()
            self.addCleanup(replacement.stop)
        jobs = self.root / 'jobs'
        for job, kinds in [('both', ['short', 'long']), ('shortonly', ['short']), ('longonly', ['long'])]:
            out = jobs / job / 'output'
            out.mkdir(parents=True)
            for kind in kinds:
                (out / ('story_short.mp4' if kind == 'short' else 'story_explainer_1080p.mp4')).write_bytes(b'X' * 100)
                (out / ('youtube_short_description.txt' if kind == 'short' else 'youtube_description.txt')).write_text(
                    'Hook. Credit: Alice.\n\n0:00 Intro\n0:15 Story\n0:30 End\n\nSource: Alice\nhttps://example.com\nPhoto: Bob, CC BY 2.0\n')
            Image.new('RGB', (20, 20)).save(out / 'thumbnail_9_16.png')
        (jobs / 'shortonly' / 'output' / '_edit_story_short.mp4').touch()
        (self.root / 'channel_configs').mkdir()
        backend.write_json(self.root / 'config.json', dict(port=42030, chrome_profile=str(self.root / 'profiles/main'),
                           log_dir=str(self.root / 'logs'), video_studio_jobs=str(jobs), playwright_headless=False,
                           upload_timeout_seconds=600))
        (self.root / 'profiles/main').mkdir(parents=True)
        (self.root / 'profiles/main/Local State').write_text('{}')
        backend.write_json(self.root / 'channel_configs/moonspots.json', dict(youtube_channel_name='Moonspots',
            title_prefix='', description_template='', default_tags=[], default_category='Science & Technology',
            made_for_kids=False, visibility='private'))
        probe = patch.object(logic, 'probe', return_value=dict(duration=60, width=1920, height=1080, fps='30/1'))
        probe.start()
        self.addCleanup(probe.stop)
        self.client = web.app.test_client()
        self.data = logic.defaults('both', 'long', 'moonspots')

    def test_jobs_types_and_edit_backups(self):
        jobs = {j['id']: j['types'] for j in self.client.get('/api/jobs').json}
        self.assertEqual(set(jobs['both']), {'short', 'long'})
        self.assertEqual(set(jobs['shortonly']), {'short'})
        self.assertEqual(set(jobs['longonly']), {'long'})

    def test_video_range_and_traversal(self):
        result = self.client.get('/api/video/both/long', headers={'Range': 'bytes=0-9'})
        self.assertEqual(result.status_code, 206)
        self.assertEqual(len(result.data), 10)
        result.close()
        self.assertEqual(self.client.get('/api/defaults/../long/moonspots').status_code, 400)
        with self.assertRaises(ValueError):
            logic.job_path('../secret')

    def test_defaults_and_credit_protection(self):
        self.assertEqual(len(logic.finalize(self.data)['chapters']), 3)
        bad = dict(self.data, description=self.data['description'].replace('Photo: Bob, CC BY 2.0', ''))
        self.assertEqual(self.client.post('/publish', json=bad).status_code, 400)
        bad = dict(self.data, description=self.data['description'].replace('Credit: Alice.', ''))
        with self.assertRaises(ValueError):
            logic.finalize(bad)

    def test_gui_visibility_and_kids_options(self):
        for visibility in ('Private', 'Unlisted', 'Public'):
            data = dict(self.data, visibility=visibility, made_for_kids=True)
            self.assertEqual(logic.finalize(data)['visibility'], visibility)

    def test_chapter_order_and_duration(self):
        for chapters in [[{'seconds': 1, 'title': 'Intro'}],
                         [{'seconds': 0, 'title': 'A'}, {'seconds': 40, 'title': 'B'}, {'seconds': 30, 'title': 'C'}],
                         [{'seconds': 0, 'title': 'A'}, {'seconds': 30, 'title': 'B'}, {'seconds': 59, 'title': 'C'}]]:
            with self.assertRaises(ValueError):
                logic.finalize(dict(self.data, chapters=chapters))

    def test_draft_isolation_and_cross_origin(self):
        self.assertEqual(self.client.post('/api/draft', json=self.data).status_code, 200)
        self.assertTrue((self.root / 'uploads/moonspots/both/draft.json').exists())
        self.assertFalse((self.root / 'jobs/both/output/draft.json').exists())
        self.assertEqual(self.client.post('/publish', json=self.data, headers={'Origin': 'https://evil.example'}).status_code, 403)

    def test_records_deduplicate_deleted_and_self_link(self):
        out = self.root / 'uploads/moonspots/both'
        out.mkdir(parents=True)
        record = dict(channel='moonspots', job='both', kind='long', video_id='ABCDEFGHIJK', title='Story')
        backend.write_json(out / 'published.json', record)
        backend.write_json(out / 'published_short.json', record)
        backend.write_json(out / 'published_deleted.json', dict(record, video_id='XXXXXXXXXXX', deleted=True))
        self.assertEqual(len(self.client.get('/api/published').json), 1)
        with self.assertRaises(ValueError):
            logic.finalize(dict(self.data, link_target='ABCDEFGHIJK'))

    def test_custom_thumbnail_is_local_and_landscape(self):
        raw = io.BytesIO()
        Image.new('RGB', (30, 50)).save(raw, format='PNG')
        raw.seek(0)
        response = self.client.post('/api/thumbnail', data=dict(job='both', channel='moonspots', kind='long', file=(raw, 'photo.png')))
        self.assertEqual(response.status_code, 200)
        path = logic.thumbnail_path(dict(self.data, thumbnail=response.json['thumbnail']))
        with Image.open(path) as image:
            self.assertEqual(image.size, (1280, 720))

    def test_link_failure_preserves_success_and_published_record(self):
        folder = self.root / 'uploads/moonspots/both/tasks/test-task'
        folder.mkdir(parents=True)
        task = dict(id='test-task', status='queued', events=[], folder=folder)
        result = dict(video_id='ABCDEFGHIJK', url='https://www.youtube.com/watch?v=ABCDEFGHIJK',
                      related_video_id=None, link_error='Automatic linking failed. Set it manually in Studio.')
        with patch.object(backend, 'upload_from_form', return_value=result):
            web.worker(task, logic.finalize(self.data), 'new')
        self.assertEqual(task['status'], 'complete')
        record = backend.read_json(self.root / 'uploads/moonspots/both/published.json')
        self.assertEqual(record['video_id'], 'ABCDEFGHIJK')
        self.assertIn('Automatic linking failed', record['link_error'])
        self.assertFalse((self.root / 'profiles/.main-upload.lock').exists())

if __name__ == '__main__':
    unittest.main()
