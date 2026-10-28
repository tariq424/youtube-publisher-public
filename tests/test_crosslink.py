import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as web
import publisher_logic as logic
import youtube_publisher as backend
from PIL import Image

SHORT_DESC = ('Title\n\nHook line.\n\nFull breakdown: <PASTE LONG VIDEO LINK HERE>\n\n'
              'Summarized from: Episode - Channel\nhttps://www.youtube.com/watch?v=src\n\n#Shorts')


class CrossLinkTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for module in (logic, backend, web):
            p = patch.object(module, 'ROOT', self.root); p.start(); self.addCleanup(p.stop)
        jobs = self.root / 'jobs'
        for job, kinds in [('both', ['short', 'long']), ('shortonly', ['short'])]:
            out = jobs / job / 'output'; out.mkdir(parents=True)
            for kind in kinds:
                (out / ('story_short.mp4' if kind == 'short' else 'story_explainer_1080p.mp4')).write_bytes(b'X' * 100)
                (out / ('youtube_short_description.txt' if kind == 'short' else 'youtube_description.txt')).write_text(
                    SHORT_DESC if kind == 'short' else 'Long hook.\n\nSource: Alice\nhttps://example.com\n')
            Image.new('RGB', (20, 20)).save(out / 'thumbnail_9_16.png')
        (self.root / 'channel_configs').mkdir()
        backend.write_json(self.root / 'config.json', dict(port=42030, chrome_profile=str(self.root / 'profiles/main'),
                           log_dir=str(self.root / 'logs'), video_studio_jobs=str(jobs), playwright_headless=False, upload_timeout_seconds=600))
        (self.root / 'profiles/main').mkdir(parents=True); (self.root / 'profiles/main/Local State').write_text('{}')
        backend.write_json(self.root / 'channel_configs/yousocial.json', dict(youtube_channel_name='YouSocial', title_prefix='',
            description_template='', default_tags=[], default_category='Science & Technology', made_for_kids=False, visibility='private'))
        p = patch.object(logic, 'probe', return_value=dict(duration=60, width=1920, height=1080, fps='30/1')); p.start(); self.addCleanup(p.stop)
        web.tasks.clear()
        self.client = web.app.test_client()

    def test_short_only_drops_the_promise(self):
        d = logic.defaults('shortonly', 'short', 'yousocial')
        self.assertEqual(d['long_link'], 'no_long')
        self.assertNotIn('PASTE', d['description']); self.assertNotIn('Full breakdown', d['description'])
        self.assertIn('Summarized from', d['description'])
        logic.finalize(d)   # publishable as is

    def test_unpublished_explainer_blocks_single_short_publish(self):
        d = logic.defaults('both', 'short', 'yousocial')
        self.assertEqual(d['long_link'], 'needs_long')
        with self.assertRaisesRegex(ValueError, 'Publish the explainer first'):
            logic.finalize(d)

    def test_published_explainer_is_injected(self):
        dest = logic.destination('yousocial', 'both'); dest.mkdir(parents=True)
        backend.write_json(dest / 'published.json', dict(channel='yousocial', job='both', kind='long', video_id='LONG1234567',
                                                         url='https://www.youtube.com/watch?v=LONG1234567'))
        d = logic.defaults('both', 'short', 'yousocial')
        self.assertEqual(d['long_link'], 'linked')
        self.assertIn('Full breakdown: https://www.youtube.com/watch?v=LONG1234567', d['description'])

    def test_pair_publishes_long_first_then_short_with_its_url(self):
        calls = []
        def fake_upload(data, video, thumb, cfg, channel, folder, emit, cancelled, mode):
            calls.append((data['kind'], data['description']))
            vid = 'LONG1234567' if data['kind'] == 'long' else 'SHORT123456'
            return dict(video_id=vid, url='https://www.youtube.com/watch?v=' + vid)
        long_d = logic.defaults('both', 'long', 'yousocial'); short_d = logic.defaults('both', 'short', 'yousocial')
        with patch.object(backend, 'upload_from_form', side_effect=fake_upload), patch.object(backend, 'load_global'):
            r = self.client.post('/publish/pair', json=dict(long=long_d, short=short_d))
            self.assertEqual(r.status_code, 202, r.json)
            for _ in range(100):
                if web.tasks[r.json['short_task']]['status'] in ('complete', 'error'): break
                time.sleep(0.05)
        self.assertEqual([c[0] for c in calls], ['long', 'short'])
        self.assertIn('Full breakdown: https://www.youtube.com/watch?v=LONG1234567', calls[1][1])
        self.assertEqual(web.tasks[r.json['short_task']]['status'], 'complete')

    def test_pair_stops_short_when_explainer_fails(self):
        def fail(data, *a, **k):
            raise RuntimeError('Studio broke')
        long_d = logic.defaults('both', 'long', 'yousocial'); short_d = logic.defaults('both', 'short', 'yousocial')
        with patch.object(backend, 'upload_from_form', side_effect=fail), patch.object(backend, 'load_global'):
            r = self.client.post('/publish/pair', json=dict(long=long_d, short=short_d))
            for _ in range(100):
                if web.tasks[r.json['short_task']]['status'] == 'error': break
                time.sleep(0.05)
        self.assertEqual(web.tasks[r.json['short_task']]['status'], 'error')
        self.assertIn('Explainer did not finish', web.tasks[r.json['short_task']]['error'])


if __name__ == '__main__':
    unittest.main()
