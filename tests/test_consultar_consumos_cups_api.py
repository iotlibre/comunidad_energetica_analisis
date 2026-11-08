import csv
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from consultar_consumos_cups_api import Period, load_cups, run_batch


class FakeResponse:
	def __init__(self, payload, status_code=200):
		self._payload = payload
		self.status_code = status_code
		self.ok = status_code < 400

	def json(self):
		return self._payload


class FakeSession:
	def __init__(self, responses_dir, period, record_counts=None, failures=None):
		self.responses_dir = responses_dir
		self.period = period
		self.record_counts = record_counts or {}
		self.failures = failures or {}
		self.calls = []
		self.current_cups = None

	def get(self, url, auth, timeout):
		self.calls.append((url, auth, timeout))
		endpoint = url.split("localhost:8000", 1)[1]
		if endpoint.startswith("/reading_register/"):
			line = unquote(endpoint.split("/reading_register/", 1)[1])
			self.current_cups = line.split(",", 1)[0]
			if self.failures.get((self.current_cups, "reading_register")) == 401:
				return FakeResponse({"detail": "Unauthorized"}, status_code=401)
			return FakeResponse({"status": "ok"})
		if endpoint == "/ejecutar":
			if self.failures.get((self.current_cups, "ejecutar")) == "no_write":
				return FakeResponse({"status": "ok"})
			count = self.record_counts.get(self.current_cups, 0)
			output_path = (
				self.responses_dir
				/ f"{self.current_cups}_{self.period.filename_suffix()}.json"
			)
			output_path.write_text(
				json.dumps([{"reading": index} for index in range(count)]),
				encoding="utf-8",
			)
			return FakeResponse({"status": "ok"})
		raise AssertionError(f"Unexpected endpoint: {endpoint}")


class ConsultCupsApiTests(unittest.TestCase):
	def setUp(self):
		self.temp_dir = tempfile.TemporaryDirectory()
		self.root = Path(self.temp_dir.name)
		self.responses_dir = self.root / "responses"
		self.responses_dir.mkdir()
		self.input_path = self.responses_dir / "cups_list.csv"
		self.config_path = self.root / "config_datadis.ini"
		self.config_path.write_text(
			"[api_auth]\nusername = api-user\npassword = api-password\n",
			encoding="utf-8",
		)
		self.period = Period(2025, 1, 2025, 12)

	def tearDown(self):
		self.temp_dir.cleanup()

	def write_cups(self, rows):
		with self.input_path.open("w", encoding="utf-8", newline="") as cups_file:
			writer = csv.writer(cups_file)
			writer.writerow(["cups", "cif"])
			writer.writerows(rows)

	def run_with_session(self, session, output_name="result.json"):
		return run_batch(
			input_path=self.input_path,
			responses_dir=self.responses_dir,
			output_path=self.responses_dir / output_name,
			config_path=self.config_path,
			period=self.period,
			session=session,
		)

	def test_processes_cups_sequentially_and_uses_strict_record_threshold(self):
		self.write_cups([("CUPS-A", "CIF-A"), ("CUPS-B", "CIF-B")])
		session = FakeSession(
			self.responses_dir,
			self.period,
			record_counts={"CUPS-A": 201, "CUPS-B": 200},
		)

		report, skipped = self.run_with_session(session)

		self.assertFalse(skipped)
		self.assertEqual(
			[result["status"] for result in report["results"]],
			["with_readings", "insufficient_readings"],
		)
		self.assertEqual(
			[result["record_count"] for result in report["results"]], [201, 200]
		)
		self.assertEqual(
			report["summary"],
			{
				"processed": 2,
				"with_readings": 1,
				"insufficient_readings": 1,
				"errors": 0,
			},
		)
		self.assertTrue(
			all("cif" not in result for result in report["results"])
		)
		saved_report = json.loads(
			(self.responses_dir / "result.json").read_text(encoding="utf-8")
		)
		self.assertEqual(saved_report, report)
		self.assertEqual(
			[call[0].split("localhost:8000", 1)[1].split("/", 2)[1]
			 for call in session.calls],
			[
				"reading_register",
				"ejecutar",
				"reading_register",
				"ejecutar",
			],
		)
		self.assertTrue(all(call[1] == ("api-user", "api-password") for call in session.calls))

	def test_existing_report_skips_input_config_and_api(self):
		output_path = self.responses_dir / "result.json"
		output_path.write_text("already exists", encoding="utf-8")
		session = FakeSession(self.responses_dir, self.period)

		report, skipped = run_batch(
			input_path=self.responses_dir / "missing.csv",
			responses_dir=self.responses_dir,
			output_path=output_path,
			config_path=self.root / "missing.ini",
			period=self.period,
			session=session,
		)

		self.assertTrue(skipped)
		self.assertIsNone(report)
		self.assertEqual(session.calls, [])
		self.assertEqual(output_path.read_text(encoding="utf-8"), "already exists")

	def test_authentication_errors_are_separate_from_no_readings(self):
		self.write_cups([("CUPS-A", "CIF-A")])
		session = FakeSession(
			self.responses_dir,
			self.period,
			failures={("CUPS-A", "reading_register"): 401},
		)

		report, _ = self.run_with_session(session)

		self.assertEqual(report["results"][0]["status"], "error")
		self.assertEqual(
			report["results"][0]["error"]["category"], "authentication"
		)
		self.assertEqual(len(session.calls), 1)

	def test_stale_result_file_is_not_counted(self):
		self.write_cups([("CUPS-A", "CIF-A")])
		response_path = (
			self.responses_dir / f"CUPS-A_{self.period.filename_suffix()}.json"
		)
		response_path.write_text('[{"old": true}]', encoding="utf-8")
		session = FakeSession(
			self.responses_dir,
			self.period,
			failures={("CUPS-A", "ejecutar"): "no_write"},
		)

		report, _ = self.run_with_session(session)

		self.assertEqual(report["results"][0]["status"], "error")
		self.assertEqual(report["results"][0]["error"]["category"], "result_file")
		self.assertIsNone(report["results"][0]["record_count"])

	def test_load_cups_rejects_duplicate_and_blank_fields(self):
		self.write_cups([("CUPS-A", "CIF-A"), ("CUPS-A", "CIF-B")])
		with self.assertRaisesRegex(ValueError, "duplicado"):
			load_cups(self.input_path)
		self.write_cups([("CUPS-A", "")])
		with self.assertRaisesRegex(ValueError, "vacío"):
			load_cups(self.input_path)


if __name__ == "__main__":
	unittest.main()
