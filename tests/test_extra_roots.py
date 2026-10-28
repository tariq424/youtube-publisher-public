import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher_logic as logic


class ExtraJobRoots(unittest.TestCase):
    def test_staged_newsroom_jobs_are_found(self):
        with tempfile.TemporaryDirectory() as t:
            main, staging = Path(t) / 'main', Path(t) / 'staging'
            (main / '20261020_100000' / 'output').mkdir(parents=True)
            (main / '20261020_100000' / 'output' / 'A_short.mp4').write_bytes(b'x')
            (staging / '20261021_120000' / 'output').mkdir(parents=True)
            (staging / '20261021_120000' / 'output' / 'B_short.mp4').write_bytes(b'x')
            cfg = {'video_studio_jobs': str(main), 'extra_job_roots': [str(staging)]}
            with patch.object(logic, 'config', return_value=cfg):
                self.assertEqual([j['id'] for j in logic.jobs()], ['20261021_120000', '20261020_100000'])
                self.assertEqual(logic.assets('20261021_120000', 'short')[0].name, 'B_short.mp4')
                self.assertEqual(logic.job_path('nope'), main / 'nope')


if __name__ == '__main__':
    unittest.main()


class AlteredContent(unittest.TestCase):
    def test_detected_from_marker_or_timeline_tags(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            a = root / 'A' / 'short' / 'public'; a.mkdir(parents=True)
            (a / 'teaser.json').write_text(json.dumps({'beats': [{'bgs': [{'tag': 'SOURCE · Desire'}, {'tag': 'GENERATED · GEMINI'}]}]}))
            b = root / 'B' / 'short' / 'public'; b.mkdir(parents=True)
            (b / 'teaser.json').write_text(json.dumps({'beats': [{'bgs': [{'tag': 'ILLUSTRATIVE'}]}]}))
            (root / 'C').mkdir(); (root / 'C' / 'ai_content.json').write_text(json.dumps({'altered': True, 'why': ['GENERATED · FLOW']}))
            with patch.object(logic, 'config', return_value={'video_studio_jobs': str(root)}):
                self.assertEqual(logic.ai_content('A'), (True, ['GENERATED · GEMINI']))
                self.assertEqual(logic.ai_content('B'), (False, []))
                self.assertEqual(logic.ai_content('C'), (True, ['GENERATED · FLOW']))
