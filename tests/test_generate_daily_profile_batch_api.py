import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from fastapi import HTTPException

import api36


class GenerateDailyProfileBatchApiTests(unittest.TestCase):
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

    def test_batch_uses_existing_daily_generator_for_only_matching_cups(self):
        input_names = [
            "CUPS-AAAAA_2025_01_2025_12.json",
            "CUPS-CCCCC_2024_3_2024_8.json",
        ]
        for name in input_names:
            (self.responses_dir / name).write_text("[]", encoding="utf-8")
        generated = [
            {
                "weekday_file": "AAAAA_weekday_profile.csv",
                "weekend_file": "AAAAA_weekend_profile.csv",
            },
            {
                "weekday_file": "CCCCC_weekday_profile.csv",
                "weekend_file": "CCCCC_weekend_profile.csv",
            },
        ]

        with patch.object(
            api36, "generate_daily_profile", side_effect=generated
        ) as generator:
            result = api36.generate_daily_profile_batch_endpoint("api-user")

        self.assertEqual(
            generator.call_args_list,
            [
                call(input_names[0], responses_dir=self.responses_dir, overwrite=False),
                call(input_names[1], responses_dir=self.responses_dir, overwrite=False),
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

    def test_duplicate_cups_rejects_csv_before_generation(self):
        self.write_cups(["CUPS-AAAAA", "CUPS-AAAAA"])
        with patch.object(api36, "generate_daily_profile") as generator:
            with self.assertRaises(HTTPException) as raised:
                api36.generate_daily_profile_batch_endpoint("api-user")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("duplicado", raised.exception.detail)
        generator.assert_not_called()

    def test_missing_cups_column_rejects_csv(self):
        self.cups_list_path.write_text("cif\nCIF\n", encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            api36.generate_daily_profile_batch_endpoint("api-user")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("columna 'cups'", raised.exception.detail)

    def test_ambiguous_input_files_are_not_processed(self):
        for filename in (
            "CUPS-AAAAA_2025_1_2025_12.json",
            "CUPS-AAAAA_2025_01_2025_12.json",
        ):
            (self.responses_dir / filename).write_text("[]", encoding="utf-8")

        with patch.object(api36, "generate_daily_profile") as generator:
            result = api36.generate_daily_profile_batch_endpoint("api-user")

        generator.assert_not_called()
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertIn("varios archivos", result["results"][0]["error"])
        self.assertEqual(result["summary"]["errors"], 1)

    def test_output_suffix_collision_does_not_process_either_cups(self):
        cups = ["USER-AAAAA", "OTHER-AAAAA"]
        self.write_cups(cups)
        for cups_value in cups:
            (self.responses_dir / f"{cups_value}_2025_01_2025_12.json").write_text(
                "[]", encoding="utf-8"
            )

        with patch.object(api36, "generate_daily_profile") as generator:
            result = api36.generate_daily_profile_batch_endpoint("api-user")

        generator.assert_not_called()
        self.assertEqual(result["summary"]["errors"], 2)
        self.assertTrue(all(item["status"] == "error" for item in result["results"]))

    def test_existing_profile_csvs_are_not_overwritten(self):
        (self.responses_dir / "CUPS-AAAAA_2025_01_2025_12.json").write_text(
            "[]", encoding="utf-8"
        )
        existing_profile = self.responses_dir / "AAAAA_weekday_profile.csv"
        existing_profile.write_text("keep this content", encoding="utf-8")

        with patch.object(api36, "generate_daily_profile") as generator:
            result = api36.generate_daily_profile_batch_endpoint("api-user")

        generator.assert_not_called()
        self.assertEqual(existing_profile.read_text(encoding="utf-8"), "keep this content")
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertIn("No se sobrescribieron", result["results"][0]["error"])

    def test_generation_error_does_not_stop_later_cups(self):
        for cups in ("CUPS-AAAAA", "CUPS-CCCCC"):
            (self.responses_dir / f"{cups}_2025_01_2025_12.json").write_text(
                "[]", encoding="utf-8"
            )

        with patch.object(
            api36,
            "generate_daily_profile",
            side_effect=[
                ValueError("JSON de entrada inválido"),
                {
                    "weekday_file": "CCCCC_weekday_profile.csv",
                    "weekend_file": "CCCCC_weekend_profile.csv",
                },
            ],
        ) as generator:
            result = api36.generate_daily_profile_batch_endpoint("api-user")

        self.assertEqual(generator.call_count, 2)
        self.assertEqual(
            [item["status"] for item in result["results"]],
            ["error", "missing_input", "generated"],
        )
        self.assertEqual(result["summary"]["errors"], 1)

    def test_openapi_documents_post_without_request_body(self):
        operation = api36.app.openapi()["paths"]["/generate_daily_profile_batch"]["post"]
        self.assertNotIn("requestBody", operation)

    def test_single_user_endpoint_keeps_legacy_generator_call(self):
        with patch.object(
            api36,
            "generate_daily_profile",
            return_value={
                "weekday_file": "AAAAA_weekday_profile.csv",
                "weekend_file": "AAAAA_weekend_profile.csv",
            },
        ) as generator:
            result = api36.generate_profile_endpoint(
                "CUPS-AAAAA_2025_01_2025_12.json", "api-user"
            )

        generator.assert_called_once_with("CUPS-AAAAA_2025_01_2025_12.json")
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
