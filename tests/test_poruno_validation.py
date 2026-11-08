import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from perfil_diario_v9 import (
    corregir_y_combinar_poruno_8760,
    generate_poruno_8760_batch,
    generate_poruno_profiles_batch,
    validar_suma_poruno_8760,
)


class PorunoValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_monthly_profile(self, filename, value):
        profile = pd.DataFrame(
            [[month, *([value] * 24)] for month in range(1, 13)],
            columns=["month", *[str(hour) for hour in range(24)]],
        )
        profile.to_csv(self.directory / filename, index=False)

    def write_yearly_profile(self, filename, cups, value):
        (self.directory / filename).write_text(
            "".join(
                f"{cups};{hour:04d};{value:.6f}\n"
                for hour in range(1, 8761)
            ),
            encoding="utf-8",
        )

    def test_batch_generates_community_profiles_and_validation_counts_missing_users(self):
        self.write_monthly_profile("perfil_comunitario_weekday.csv", 100)
        self.write_monthly_profile("perfil_comunitario_weekend.csv", 100)
        self.write_monthly_profile("USER1_weekday_profile.csv", 123.45)
        self.write_monthly_profile("USER1_weekend_profile.csv", 123.45)
        with (self.directory / "cups_list.csv").open(
            "w", encoding="utf-8", newline=""
        ) as cups_file:
            csv.writer(cups_file).writerow(["CUPS-USER1", "CIF"])

        monthly_result = generate_poruno_profiles_batch(self.directory, 2)

        self.assertIn(
            "perfil_comunitario_weekday_poruno.csv",
            [Path(path).name for path in monthly_result["community_profiles"]],
        )
        community_monthly = pd.read_csv(
            self.directory / "perfil_comunitario_weekday_poruno.csv"
        )
        self.assertAlmostEqual(community_monthly.loc[0, "0"], 100 / 223.45)
        user_monthly = pd.read_csv(
            self.directory / "USER1_weekday_poruno.csv"
        )
        self.assertAlmostEqual(user_monthly.loc[0, "0"], 123.45 / 223.45)

        yearly_result = generate_poruno_8760_batch(self.directory, 2025)
        self.assertEqual(yearly_result["errors"], [])
        self.assertIn(
            str(self.directory / "perfil_comunitario_8760_poruno_2025.txt"),
            yearly_result["generated_files"],
        )

        result = validar_suma_poruno_8760(self.directory, 2025, 2)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["num_users"], 2)
        self.assertEqual(result["average_profiles_added"], 1)
        self.assertEqual(result["stats"]["hours_with_exact_sum"], 8760)
        self.assertLess(result["stats"]["max_deviation"], 1e-6)

    def test_validation_excludes_a_previous_combined_file(self):
        self.write_yearly_profile(
            "CUPS-USER1_8760_poruno_2025.txt", "CUPS-USER1", 0.5
        )
        self.write_yearly_profile(
            "perfil_comunitario_8760_poruno_2025.txt",
            "perfil_comunitario",
            0.5,
        )
        self.write_yearly_profile(
            "todos_usuarios_8760_poruno_2025.txt",
            "todos_usuarios",
            0.5,
        )

        result = validar_suma_poruno_8760(self.directory, 2025, 2)

        self.assertEqual(result["users_processed"], ["CUPS-USER1"])
        self.assertEqual(result["average_profiles_added"], 1)
        self.assertEqual(result["stats"]["hours_with_exact_sum"], 8760)

    def test_incomplete_user_profile_is_reported_and_replaced_with_average(self):
        user_file = self.directory / "CUPS-USER1_8760_poruno_2025.txt"
        user_file.write_text(
            "".join(
                f"CUPS-USER1;{hour:04d};0.500000\n"
                for hour in range(1, 8760)
            ),
            encoding="utf-8",
        )
        community_file = self.directory / "perfil_comunitario_8760_poruno_2025.txt"
        community_file.write_text(
            "".join(
                f"perfil_comunitario;{hour:04d};0.500000\n"
                for hour in range(1, 8761)
            ),
            encoding="utf-8",
        )

        result = validar_suma_poruno_8760(self.directory, 2025, 2)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["users_processed"], [])
        self.assertEqual(result["average_profiles_added"], 2)
        self.assertEqual(result["stats"]["hours_with_exact_sum"], 8760)
        self.assertIn("8760 horas únicas", result["errors"][0]["errors"][-1])

    def test_validation_can_use_community_profile_for_all_users(self):
        self.write_monthly_profile("perfil_comunitario_weekday.csv", 100)
        self.write_monthly_profile("perfil_comunitario_weekend.csv", 100)
        with (self.directory / "cups_list.csv").open(
            "w", encoding="utf-8", newline=""
        ) as cups_file:
            csv.writer(cups_file).writerow(["CUPS-USER1", "CIF"])

        monthly_result = generate_poruno_profiles_batch(self.directory, 2)
        yearly_result = generate_poruno_8760_batch(self.directory, 2025)

        self.assertEqual(monthly_result["users_processed"], [])
        self.assertEqual(yearly_result["errors"], [])
        self.assertEqual(
            yearly_result["generated_files"],
            [str(self.directory / "perfil_comunitario_8760_poruno_2025.txt")],
        )

        result = validar_suma_poruno_8760(self.directory, 2025, 2)

        self.assertEqual(result["average_profiles_added"], 2)
        self.assertEqual(result["stats"]["hours_with_exact_sum"], 8760)

    def test_missing_community_profile_is_reported_when_users_are_missing(self):
        user_file = self.directory / "CUPS-USER1_8760_poruno_2025.txt"
        user_file.write_text(
            "".join(
                f"CUPS-USER1;{hour:04d};0.500000\n"
                for hour in range(1, 8761)
            ),
            encoding="utf-8",
        )

        with self.assertRaises(FileNotFoundError):
            validar_suma_poruno_8760(self.directory, 2025, 2)

    def test_correction_ignores_community_and_existing_combined_profiles(self):
        self.write_yearly_profile(
            "CUPS-USER1_8760_poruno_2025.txt", "CUPS-USER1", 0.5
        )
        self.write_yearly_profile(
            "CUPS-USER2_8760_poruno_2025.txt", "CUPS-USER2", 0.5
        )
        self.write_yearly_profile(
            "perfil_comunitario_8760_poruno_2025.txt",
            "perfil_comunitario",
            0.5,
        )
        self.write_yearly_profile(
            "todos_usuarios_8760_poruno_2025.txt",
            "stale_combined",
            1.5,
        )

        result = corregir_y_combinar_poruno_8760(self.directory, 2025)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["num_users"], 2)
        self.assertEqual(result["verification_errors"], None)

        repeated_result = corregir_y_combinar_poruno_8760(self.directory, 2025)

        self.assertEqual(repeated_result["status"], "ok")
        self.assertEqual(repeated_result["num_users"], 2)

    def test_correction_still_rejects_large_real_user_deviation(self):
        self.write_yearly_profile(
            "CUPS-USER1_8760_poruno_2025.txt", "CUPS-USER1", 0.25
        )
        last_user_file = self.directory / "CUPS-USER2_8760_poruno_2025.txt"
        self.write_yearly_profile(
            last_user_file.name, "CUPS-USER2", 0.25
        )
        self.write_yearly_profile(
            "perfil_comunitario_8760_poruno_2025.txt",
            "perfil_comunitario",
            0.25,
        )
        original_content = last_user_file.read_text(encoding="utf-8")

        result = corregir_y_combinar_poruno_8760(self.directory, 2025)

        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result["message"],
            "Corrección rechazada: 8760 horas con ajuste fuera de rango",
        )
        self.assertEqual(last_user_file.read_text(encoding="utf-8"), original_content)


if __name__ == "__main__":
    unittest.main()
