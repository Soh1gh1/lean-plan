"""Journals must survive the lifetime of a one-file EXE's temporary resources."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from app import default_data_dir


class DataDirectoryTests(unittest.TestCase):
    def test_source_keeps_existing_portable_journal_location(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(default_data_dir(Path('portable')), Path('portable/data'))

    def test_frozen_build_keeps_data_outside_temporary_resources(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': 'local-profile'}, clear=True), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(default_data_dir(Path('_MEI-first')), Path('local-profile/Lean Plan/data'))
            self.assertEqual(default_data_dir(Path('_MEI-second')), Path('local-profile/Lean Plan/data'))

    def test_explicit_environment_override_works_for_both_builds(self):
        for frozen in (False, True):
            with self.subTest(frozen=frozen), patch.dict(os.environ, {'LEANPLAN_DATA_DIR': 'isolated'}, clear=True), patch.object(sys, 'frozen', frozen, create=True):
                self.assertEqual(default_data_dir(Path('resources')), Path('isolated'))

    def test_missing_local_appdata_falls_back_to_user_profile(self):
        with patch.dict(os.environ, {'USERPROFILE': 'user-profile'}, clear=True), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(default_data_dir(Path('resources')), Path('user-profile/AppData/Local/Lean Plan/data'))
