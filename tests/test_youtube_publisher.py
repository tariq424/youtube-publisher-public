import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import youtube_publisher as pub


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        log_patch = patch.object(pub.logging, 'basicConfig')
        log_patch.start()
        self.addCleanup(log_patch.stop)
        self.jobs = Path(self.temp.name)
        self.root = self.jobs / 'publisher'
        self.root.mkdir()
        root_patch = patch.object(pub, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        config = self.root / 'channel_configs'
        config.mkdir()
        profile = self.root / 'profiles' / 'main'
        profile.mkdir(parents=True)
        (profile / 'Local State').write_text('{}')
        pub.write_json(self.root / 'config.json', dict(chrome_profile=str(profile),
            playwright_headless=False, upload_timeout_seconds=600))
        pub.write_json(config / 'moonspots.json', dict(youtube_channel_name='Moonspots', title_prefix='',
            description_template='', default_tags=[], default_category='Science & Technology',
            made_for_kids=False, visibility='private'))
        self.generated = self.root / 'uploads' / 'moonspots' / 'job'
        self.generated.mkdir(parents=True)
        self.out = self.jobs / 'job' / 'output'
        self.out.mkdir(parents=True)
        for name in ['story_explainer_1080p.mp4', 'story_short.mp4', 'thumbnail_9_16.png']:
            (self.out / name).touch()
        self.original = 'Original credit.\r\n\r\n0:00 Intro\r\n0:15 Evidence\r\n0:30 Conclusion\r\nPhoto: Author, CC BY 2.0\r\n'
        (self.out / 'youtube_description.txt').write_bytes(self.original.encode())
        (self.out / 'youtube_short_description.txt').write_text('Short credit.', encoding='utf-8')
        self.meta = dict(title='Accurate title', hook='First line\nSecond line', tags=[f'tag{i}' for i in range(15)],
                         category='Education', visibility='Private', made_for_kids=False,
                         chapters=pub.chapters(self.original), description='First line\nSecond line\n\n' + self.original)

    def test_selection(self):
        self.assertIn('_explainer_', pub.discover(self.jobs, 'job', 'long')[2].name)
        self.assertIn('_short', pub.discover(self.jobs, 'job', 'short')[2].name)
        with self.assertRaises(ValueError):
            pub.discover(self.jobs, '../job', 'long')
        (self.out / 'another_explainer_1080p.mp4').touch()
        with self.assertRaises(ValueError):
            pub.discover(self.jobs, 'job', 'long')

    def test_credits_and_settings(self):
        pub.validate(self.meta, self.original, 'long')
        for key, value in [('description', self.meta['description'].replace('CC BY', 'CC0')),
                           ('visibility', 'Public'), ('made_for_kids', True), ('tags', ['same'] * 15)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                pub.validate(dict(self.meta, **{key: value}), self.original, 'long')

    def test_chapters(self):
        self.assertEqual(pub.chapters(self.original)[1]['seconds'], 15)
        for text in ['0:01 A\n0:15 B\n0:30 C', '0:00 A\n0:05 B\n0:30 C', '0:00 A']:
            with self.assertRaises(ValueError):
                pub.chapters(text)

    def test_duplicate_stops_before_generation_or_browser(self):
        pub.write_json(self.generated / 'youtube_long_upload.json', {'status': 'saving'})
        with patch.object(sys, 'argv', ['publisher', 'job', '--channel', 'Moonspots', '--jobs-dir', str(self.jobs), '--upload']), \
             patch.object(pub, 'generate') as generate, patch.object(pub, 'upload') as upload:
            with self.assertRaises(RuntimeError):
                pub.main()
            generate.assert_not_called()
            upload.assert_not_called()
        self.assertFalse((self.generated / '.youtube_long.lock').exists())

    def test_metadata_only_never_uploads(self):
        with patch.object(sys, 'argv', ['publisher', 'job', '--channel', 'Moonspots', '--jobs-dir', str(self.jobs)]), \
             patch.object(pub, 'generate', return_value=self.meta), patch.object(pub, 'upload') as upload:
            pub.main()
            upload.assert_not_called()
        saved = pub.read_json(self.generated / 'youtube_long_metadata.json')
        self.assertTrue(saved['description'].endswith(self.original))

    def test_missing_channel_and_profile(self):
        with self.assertRaisesRegex(ValueError, 'No config found for channel Future'):
            pub.load_channel('Future')
        (self.root / 'profiles' / 'main' / 'Local State').unlink()
        with self.assertRaisesRegex(ValueError, 'Shared Chrome profile not found'):
            pub.load_global(require_profile=True)

    def test_channel_defaults(self):
        channel, cfg = pub.load_channel('Moonspots')
        cfg.update(title_prefix='Moonspots: ', default_tags=['space'], description_template='{hook}')
        result = pub.apply_defaults(dict(self.meta), self.original, cfg)
        pub.validate(result, self.original, 'long')
        self.assertEqual(result['category'], 'Science & Technology')
        self.assertEqual(result['tags'][0], 'space')
        self.assertEqual(channel, 'moonspots')

    def test_codex_discovery_without_terminal_path(self):
        local = self.root / 'localappdata'
        executable = local / 'OpenAI' / 'Codex' / 'bin' / 'version' / 'codex.exe'
        executable.parent.mkdir(parents=True)
        executable.touch()
        with patch.object(pub.shutil, 'which', return_value=None), \
             patch.dict(pub.os.environ, {'LOCALAPPDATA': str(local)}):
            self.assertEqual(pub.resolve_codex(), str(executable))
            with self.assertRaisesRegex(ValueError, 'Codex executable not found'):
                pub.resolve_codex('missing-codex.exe')


if __name__ == '__main__':
    unittest.main()
