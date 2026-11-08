import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import api36


class ConsultarConsumosPorGruposTests(unittest.TestCase):
	def setUp(self):
		self.temp_dir = tempfile.TemporaryDirectory()
		self.project_root = Path(self.temp_dir.name)
		self.responses_dir = self.project_root / "responses"
		self.responses_dir.mkdir()
		(self.responses_dir / "cups_list.csv").write_text(
			"cups,cif\nCUPS-A,CIF-A\nCUPS-B,CIF-B\n",
			encoding="utf-8",
		)
		self.root_patch = patch.object(api36, "API_PROJECT_ROOT", self.project_root)
		self.root_patch.start()
		self.addCleanup(self.root_patch.stop)

	def tearDown(self):
		self.temp_dir.cleanup()

	@staticmethod
	def consume_stream(response):
		async def collect():
			chunks = []
			async for chunk in response.body_iterator:
				chunks.append(
					chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
				)
			return chunks

		return asyncio.run(collect())

	def test_request_defaults_match_documented_period_and_codes(self):
		request = api36.SolicitudConsultarConsumosPorGrupos()

		self.assertEqual(request.distributor, 8)
		self.assertEqual(request.point_type, 5)
		self.assertEqual(request.ano_de_inicio, 2025)
		self.assertEqual(request.mes_inicio, 1)
		self.assertEqual(request.ano_final, 2025)
		self.assertEqual(request.mes_final, 12)
		self.assertEqual(request.threshold, 200)

	def test_openapi_documents_streaming_endpoint_and_configuration_fields(self):
		openapi = api36.app.openapi()
		operation = openapi["paths"]["/consultar_consumos_por_grupos"]["post"]
		self.assertIn(
			"application/x-ndjson",
			operation["responses"]["200"]["content"],
		)
		request_schema_ref = operation["requestBody"]["content"]["application/json"][
			"schema"
		]["$ref"]
		schema_name = request_schema_ref.rsplit("/", 1)[-1]
		schema = openapi["components"]["schemas"][schema_name]
		self.assertIn("CodepointType", schema["properties"])
		self.assertEqual(schema["properties"]["distributor"]["default"], 8)
		self.assertEqual(schema["properties"]["CodepointType"]["default"], 5)

	def test_custom_period_codes_and_streamed_progress(self):
		request = api36.SolicitudConsultarConsumosPorGrupos(
			distributor=9,
			CodepointType="4",
			ano_de_inicio=2024,
			mes_inicio=3,
			ano_final=2024,
			mes_final=8,
			threshold=1,
		)
		configured_lines = []
		current_cups = []

		def configure_register(line):
			configured_lines.append(line)
			current_cups[:] = [line.split(",", 1)[0]]
			return {"status": "ok"}

		def process_cups():
			cups = current_cups[0]
			result_path = (
				self.responses_dir / f"{cups}_2024_03_2024_08.json"
			)
			record_count = 2 if cups == "CUPS-A" else 1
			result_path.write_text(
				json.dumps([{"reading": index} for index in range(record_count)]),
				encoding="utf-8",
			)

		with (
			patch.object(api36, "generar_y_guardar_reading_register", configure_register),
			patch.object(api36, "procesar_consumos", process_cups),
		):
			response = api36.consultar_consumos_por_grupos(request, "api-user")
			events = [
				json.loads(line)
				for line in "".join(self.consume_stream(response)).splitlines()
			]

		self.assertEqual(
			configured_lines,
			[
				"CUPS-A,CIF-A,9,4,2024,3,2024,8",
				"CUPS-B,CIF-B,9,4,2024,3,2024,8",
			],
		)
		progress = [event for event in events if event["event"] == "progress"]
		self.assertEqual(
			[(event["state"], event["cups"], event["processed"]) for event in progress],
			[
				("processing", "CUPS-A", 0),
				("completed", "CUPS-A", 1),
				("processing", "CUPS-B", 1),
				("completed", "CUPS-B", 2),
			],
		)
		summary = events[-1]
		self.assertEqual(summary["event"], "summary")
		self.assertEqual(
			summary["summary"],
			{
				"processed": 2,
				"with_readings": 1,
				"insufficient_readings": 1,
				"errors": 0,
				"skipped_existing": 0,
			},
		)
		self.assertTrue((self.responses_dir / "cups_consultation_results.json").is_file())

	def test_existing_cups_response_is_skipped_without_consulting_or_overwriting(self):
		request = api36.SolicitudConsultarConsumosPorGrupos()
		existing_path = self.responses_dir / (
			"CUPS-A_2025_01_2025_12.json"
		)
		existing_content = '[{"original": true}]'
		existing_path.write_text(existing_content, encoding="utf-8")

		def configure_register(line):
			self.assertTrue(line.startswith("CUPS-B,"))
			return {"status": "ok"}

		def process_cups():
			(self.responses_dir / "CUPS-B_2025_01_2025_12.json").write_text(
				"[]",
				encoding="utf-8",
			)

		with (
			patch.object(api36, "generar_y_guardar_reading_register", configure_register),
			patch.object(api36, "procesar_consumos", process_cups),
		):
			response = api36.consultar_consumos_por_grupos(request, "api-user")
			events = [
				json.loads(line)
				for line in "".join(self.consume_stream(response)).splitlines()
			]

		cups_results = events[-1]["results"]
		self.assertEqual(cups_results[0]["status"], "skipped_existing")
		self.assertEqual(cups_results[0]["record_count"], None)
		self.assertIn("ni se modificó", cups_results[0]["message"])
		self.assertEqual(cups_results[1]["status"], "insufficient_readings")
		self.assertEqual(events[-1]["summary"]["skipped_existing"], 1)
		self.assertEqual(existing_path.read_text(encoding="utf-8"), existing_content)

	def test_existing_report_skips_csv_loading_and_all_consultations(self):
		output_path = self.responses_dir / "cups_consultation_results.json"
		output_path.write_text('{"existing": true}', encoding="utf-8")
		request = api36.SolicitudConsultarConsumosPorGrupos()

		with (
			patch.object(api36, "_load_group_cups", side_effect=AssertionError),
			patch.object(api36, "generar_y_guardar_reading_register", side_effect=AssertionError),
			patch.object(api36, "procesar_consumos", side_effect=AssertionError),
		):
			response = api36.consultar_consumos_por_grupos(request, "api-user")
			events = [
				json.loads(line)
				for line in "".join(self.consume_stream(response)).splitlines()
			]

		self.assertEqual(events[0]["event"], "already_exists")
		self.assertEqual(output_path.read_text(encoding="utf-8"), '{"existing": true}')

	def test_repeated_cif_is_allowed_and_consulted_for_each_cups(self):
		(self.responses_dir / "cups_list.csv").write_text(
			"cups,cif\nCUPS-A,CIF-REPEATED\nCUPS-B,CIF-REPEATED\n",
			encoding="utf-8",
		)
		configured_lines = []
		current_cups = []

		def configure_register(line):
			configured_lines.append(line)
			current_cups[:] = [line.split(",", 1)[0]]
			return {"status": "ok"}

		def process_cups():
			cups = current_cups[0]
			(self.responses_dir / f"{cups}_2025_01_2025_12.json").write_text(
				"[]",
				encoding="utf-8",
			)

		with (
			patch.object(api36, "generar_y_guardar_reading_register", configure_register),
			patch.object(api36, "procesar_consumos", process_cups),
		):
			response = api36.consultar_consumos_por_grupos(
				api36.SolicitudConsultarConsumosPorGrupos(), "api-user"
			)
			events = [
				json.loads(line)
				for line in "".join(self.consume_stream(response)).splitlines()
			]

		self.assertEqual(
			configured_lines,
			[
				"CUPS-A,CIF-REPEATED,8,5,2025,1,2025,12",
				"CUPS-B,CIF-REPEATED,8,5,2025,1,2025,12",
			],
		)
		self.assertEqual(events[-1]["summary"]["errors"], 0)

	def test_repeated_cups_is_rejected_before_consulting(self):
		(self.responses_dir / "cups_list.csv").write_text(
			"cups,cif\nCUPS-A,CIF-A\nCUPS-A,CIF-B\n",
			encoding="utf-8",
		)

		with patch.object(
			api36, "generar_y_guardar_reading_register", side_effect=AssertionError
		):
			with self.assertRaises(HTTPException) as raised:
				api36.consultar_consumos_por_grupos(
					api36.SolicitudConsultarConsumosPorGrupos(), "api-user"
				)

		self.assertEqual(raised.exception.status_code, 400)
		self.assertIn("CUPS duplicado", raised.exception.detail)

	def test_csv_columns_must_match_expected_order(self):
		(self.responses_dir / "cups_list.csv").write_text(
			"cif,cups\nCIF-A,CUPS-A\n",
			encoding="utf-8",
		)

		with patch.object(
			api36, "generar_y_guardar_reading_register", side_effect=AssertionError
		):
			with self.assertRaises(HTTPException) as raised:
				api36.consultar_consumos_por_grupos(
					api36.SolicitudConsultarConsumosPorGrupos(), "api-user"
				)

		self.assertEqual(raised.exception.status_code, 400)
		self.assertIn("en ese orden", raised.exception.detail)

	def test_datadis_recent_query_message_is_reported_as_a_clear_error(self):
		request = api36.SolicitudConsultarConsumosPorGrupos()
		result_path = self.responses_dir / (
			"CUPS-A_2025_01_2025_12.json"
		)

		def configure_register(line):
			return {"status": "ok"}

		def process_cups():
			result_path.write_text(
				"Consulta ya realizada en las últimas 24 horas.",
				encoding="utf-8",
			)

		with (
			patch.object(api36, "generar_y_guardar_reading_register", configure_register),
			patch.object(api36, "procesar_consumos", process_cups),
		):
			response = api36.consultar_consumos_por_grupos(request, "api-user")
			events = [
				json.loads(line)
				for line in "".join(self.consume_stream(response)).splitlines()
			]

		cups_result = events[-1]["results"][0]
		self.assertEqual(cups_result["status"], "error")
		self.assertEqual(cups_result["error"]["category"], "result_file")
		self.assertIn("ya se realizó en las últimas 24 horas", cups_result["error"]["message"])

	def test_invalid_period_is_rejected_before_streaming_or_consulting(self):
		request = api36.SolicitudConsultarConsumosPorGrupos(
			ano_de_inicio=2026,
			mes_inicio=1,
			ano_final=2025,
			mes_final=12,
		)

		with patch.object(
			api36, "generar_y_guardar_reading_register", side_effect=AssertionError
		):
			with self.assertRaises(HTTPException) as raised:
				api36.consultar_consumos_por_grupos(request, "api-user")

		self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
	unittest.main()
