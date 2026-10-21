import json
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from perfil_diario_v9 import generate_daily_profile, generate_daily_profile_extended


class GenerateDailyProfileExtendedTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        Path("responses").mkdir()

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp_dir.cleanup()

    def test_generates_monthly_hourly_means_without_profile_csv_files(self):
        input_path = Path("responses/CUPS12345_2025_01_2025_01.json")
        input_path.write_text(
            json.dumps(
                [
                    {
                        "date": "2025/01/06",
                        "time": "00:00",
                        "consumptionKWh": 2,
                        "selfConsumptionEnergyKWh": 0.5,
                        "surplusEnergyKWh": 1.25,
                    },
                    {
                        "date": "2025/01/05",
                        "time": "24:00",
                        "consumptionKWh": 1,
                    },
                    {
                        "date": "2025/01/07",
                        "time": "01:00",
                        "consumptionKWh": 0.4,
                        "selfConsumptionEnergyKWh": 0.1,
                    },
                    {
                        "date": "2025/01/08",
                        "time": "01:00",
                        "consumptionKWh": 1,
                        "selfConsumptionEnergyKWh": 0.5,
                    },
                ]
            ),
            encoding="utf-8",
        )

        result = generate_daily_profile_extended(input_path.name)

        self.assertEqual(result["output_file"], "12345_day_profile_extended.json")
        output_path = Path("responses") / result["output_file"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(
            list(output), ["weekday_consumption", "weekend_consumption"]
        )
        weekday_profile = output["weekday_consumption"]
        weekend_profile = output["weekend_consumption"]
        self.assertEqual(len(weekday_profile), 12)
        self.assertEqual(len(weekend_profile), 12)
        self.assertEqual(
            list(weekday_profile[0]), ["month", *[str(hour) for hour in range(24)]]
        )
        self.assertEqual(weekday_profile[0]["month"], 1)
        self.assertEqual(
            weekday_profile[0]["1"],
            {
                "total_consumption_kWh": 1.0,
                "self_consumption_kWh": 0.3,
                "total_generation": 0.3,
            },
        )
        self.assertEqual(
            weekday_profile[0]["0"],
            {
                "total_consumption_kWh": None,
                "self_consumption_kWh": None,
                "total_generation": None,
            },
        )
        self.assertEqual(
            weekend_profile[0]["0"],
            {
                "total_consumption_kWh": 1.75,
                "self_consumption_kWh": 0.25,
                "total_generation": 0.875,
            },
        )
        self.assertEqual(
            weekend_profile[0]["1"],
            {
                "total_consumption_kWh": None,
                "self_consumption_kWh": None,
                "total_generation": None,
            },
        )
        self.assertTrue(
            all(row["month"] == month for month, row in enumerate(weekday_profile, 1))
        )

    def test_rejects_paths_outside_responses(self):
        with self.assertRaises(ValueError):
            generate_daily_profile_extended("../outside.json")

    def test_existing_daily_profile_still_generates_monthly_csv_files(self):
        input_path = Path("responses/CUPS12345_2025_01_2025_01.json")
        input_path.write_text(
            json.dumps(
                [
                    {
                        "date": "2025/01/07",
                        "time": "01:00",
                        "consumptionKWh": 1,
                    },
                    {
                        "date": "2025/01/05",
                        "time": "01:00",
                        "consumptionKWh": 2,
                    },
                ]
            ),
            encoding="utf-8",
        )

        result = generate_daily_profile(input_path.name)

        self.assertEqual(
            result,
            {
                "weekday_file": "12345_weekday_profile.csv",
                "weekend_file": "12345_weekend_profile.csv",
            },
        )
        weekday_profile = pd.read_csv(Path("responses") / result["weekday_file"])
        weekend_profile = pd.read_csv(Path("responses") / result["weekend_file"])
        self.assertEqual(weekday_profile.loc[0, "1"], 1)
        self.assertEqual(weekend_profile.loc[0, "1"], 2)

    def test_invalid_json_does_not_create_output_file(self):
        Path("responses/CUPS12345_2025_01_2025_01.json").write_text(
            "{invalid", encoding="utf-8"
        )

        with self.assertRaises(json.JSONDecodeError):
            generate_daily_profile_extended("CUPS12345_2025_01_2025_01.json")

        self.assertFalse(
            Path("responses/12345_day_profile_extended.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
