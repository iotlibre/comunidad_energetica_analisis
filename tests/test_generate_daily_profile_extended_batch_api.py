import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from fastapi import HTTPException

import api36


class GenerateDailyProfileExtendedBatchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.responses_dir = self.project_root / "responses"
        self.responses_dir.mkdir()
        self.cups_list_path = self.responses_dir / "cups_list.csv"
        self.write_cups(["CUPS-AAAAA", "CUPS-BBBBB", "CUPS-CCCCC"])
        self.root_patch = patch.object(api36, "API_PROJECT_ROOT", self.project_root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_cups(self, cups):
        with self.cups_list_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["cups", "cif"])
            writer.writerows((cups_value, "CIF") for cups_value in cups)

    def test_batch_uses_existing_generator_only_for_available_cups(self):
        input_names = [
            "CUPS-AAAAA_2025_01_2025_12.json",
            "CUPS-CCCCC_2025_01_2025_12.json",
        ]
        for name in input_names:
            (self.responses_dir / name).write_text("[]", encoding="utf-8")
        generated = [
            {"output_file": "AAAAA_day_profile_extended.json"},
            {"output_file": "CCCCC_day_profile_extended.json"},
        ]

        with patch.object(
            api36,
            "generate_daily_profile_extended",
            side_effect=generated,
        ) as generator:
            result = api36.generate_extended_profile_batch_endpoint(
                "api-user"
            )

        self.assertEqual(
            generator.call_args_list,
            [
                call(input_names[0], responses_dir=self.responses_dir),
                call(input_names[1], responses_dir=self.responses_dir),
            ],
        )
        self.assertEqual(
            result["summary"],
            {"total": 3, "generated": 2, "missing_input": 1, "errors": 0},
        )
        self.assertEqual(
            [item["status"] for item in result["results"]],
            ["generated", "missing_input", "generated"],
        )

    def test_generator_error_is_reported_and_processing_continues(self):
        (self.responses_dir / "CUPS-AAAAA_2025_01_2025_12.json").write_text(
            "[]", encoding="utf-8"
        )
        (self.responses_dir / "CUPS-CCCCC_2025_01_2025_12.json").write_text(
            "[]", encoding="utf-8"
        )

        with patch.object(
            api36,
            "generate_daily_profile_extended",
            side_effect=[ValueError("JSON de entrada no válido"), {"output_file": "CCCCC_day_profile_extended.json"}],
        ) as generator:
            result = api36.generate_extended_profile_batch_endpoint(
                "api-user"
            )

        self.assertEqual(generator.call_count, 2)
        self.assertEqual(
            [item["status"] for item in result["results"]],
            ["error", "missing_input", "generated"],
        )
        self.assertEqual(result["summary"]["errors"], 1)

    def test_duplicate_cups_in_csv_rejects_batch_before_generation(self):
        self.write_cups(["CUPS-AAAAA", "CUPS-AAAAA"])
        with patch.object(api36, "generate_daily_profile_extended") as generator:
            with self.assertRaises(HTTPException) as raised:
                api36.generate_extended_profile_batch_endpoint(
                    "api-user"
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("duplicado", raised.exception.detail)
        generator.assert_not_called()

    def test_multiple_filename_variants_are_rejected_as_ambiguous(self):
        for filename in (
            "CUPS-AAAAA_2025_1_2025_12.json",
            "CUPS-AAAAA_2025_01_2025_12.json",
        ):
            (self.responses_dir / filename).write_text("[]", encoding="utf-8")

        with patch.object(api36, "generate_daily_profile_extended") as generator:
            result = api36.generate_extended_profile_batch_endpoint(
                "api-user"
            )

        generator.assert_not_called()
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertIn("varios archivos", result["results"][0]["error"])
        self.assertEqual(result["summary"]["errors"], 1)

    def test_source_filename_determines_period_without_request_parameters(self):
        matching = "CUPS-AAAAA_2024_3_2024_8.json"
        (self.responses_dir / matching).write_text("[]", encoding="utf-8")

        with patch.object(
            api36,
            "generate_daily_profile_extended",
            return_value={"output_file": "AAAAA_day_profile_extended.json"},
        ) as generator:
            result = api36.generate_extended_profile_batch_endpoint(
                "api-user"
            )

        generator.assert_called_once_with(matching, responses_dir=self.responses_dir)
        self.assertEqual(result["results"][0]["input_file"], matching)

    def test_output_suffix_collision_does_not_run_generator(self):
        cups = ["USER-AAAAA", "OTHER-AAAAA"]
        self.write_cups(cups)
        for cups_value in cups:
            (self.responses_dir / f"{cups_value}_2025_01_2025_12.json").write_text(
                "[]", encoding="utf-8"
            )

        with patch.object(api36, "generate_daily_profile_extended") as generator:
            result = api36.generate_extended_profile_batch_endpoint(
                "api-user"
            )

        generator.assert_not_called()
        self.assertEqual(result["summary"]["errors"], 2)
        self.assertTrue(
            all(item["status"] == "error" for item in result["results"])
        )

    def test_csv_without_cups_column_is_rejected(self):
        self.cups_list_path.write_text("cif\nCIF-A\n", encoding="utf-8")
        with patch.object(api36, "generate_daily_profile_extended") as generator:
            with self.assertRaises(HTTPException) as raised:
                api36.generate_extended_profile_batch_endpoint(
                    "api-user"
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("columna 'cups'", raised.exception.detail)
        generator.assert_not_called()

    def test_openapi_documents_batch_endpoint_without_request_body(self):
        openapi = api36.app.openapi()
        operation = openapi["paths"]["/generate_daily_profile_extended_batch"]["post"]
        self.assertNotIn("requestBody", operation)


if __name__ == "__main__":
    unittest.main()
