import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio_automation import last_fifteen_start

class EndScreenTimecodes(unittest.TestCase):
    def test_preserves_frames_and_borrows_minutes(self):
        self.assertEqual(last_fifteen_start('13:48:02'), '13:33:02')
        self.assertEqual(last_fifteen_start('01:05:24'), '00:50:24')
        self.assertEqual(last_fifteen_start('00:25:00'), '00:10:00')

    def test_rejects_invalid_or_ineligible_timecodes(self):
        for value in ('00:24:00', '13:69:02', '13:48.02', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                last_fifteen_start(value)
