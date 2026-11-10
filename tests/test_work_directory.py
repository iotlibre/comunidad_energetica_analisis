import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.utils import work_directory
from dashboard.utils.work_directory import find_work_directories


class FindWorkDirectoriesTests(unittest.TestCase):
	def test_returns_responses_and_matching_immediate_subdirectories(self):
		with tempfile.TemporaryDirectory() as temporary_directory:
			responses_dir = Path(temporary_directory) / "responses"
			responses_dir.mkdir()
			matching_dir = responses_dir / "responses_2025"
			matching_dir.mkdir()
			(responses_dir / "responses_notes.txt").write_text("not a directory")
			(responses_dir / "other").mkdir()
			(matching_dir / "responses_nested").mkdir()

			self.assertEqual(
				find_work_directories(responses_dir),
				[responses_dir, matching_dir],
			)

	def test_returns_empty_when_responses_directory_does_not_exist(self):
		with tempfile.TemporaryDirectory() as temporary_directory:
			responses_dir = Path(temporary_directory) / "responses"

			self.assertEqual(find_work_directories(responses_dir), [])


class SelectWorkDirectoryTests(unittest.TestCase):
	def test_preserves_selection_on_rerun(self):
		with tempfile.TemporaryDirectory() as temporary_directory:
			responses_dir = Path(temporary_directory) / "responses"
			responses_dir.mkdir()
			selected_dir = responses_dir / "responses_kemendi_el_lago_0"
			selected_dir.mkdir()
			session_state = {
				work_directory.WORK_DIRECTORY_SESSION_KEY: responses_dir.name,
			}

			def select_directory(label, options, key, on_change, args):
				session_state[key] = selected_dir.name
				on_change(*args)
				return session_state[key]

			with (
				patch.object(work_directory.st, "session_state", session_state),
				patch.object(
					work_directory.st, "selectbox", side_effect=select_directory
				),
			):
				first_selection = work_directory.select_work_directory(
					responses_dir, "work_directory_test"
				)
				second_selection = work_directory.select_work_directory(
					responses_dir, "work_directory_test"
				)

			self.assertEqual(first_selection, selected_dir)
			self.assertEqual(second_selection, selected_dir)


if __name__ == "__main__":
	unittest.main()
