import csv
import tempfile
import unittest
from pathlib import Path

from perfil_diario_v9 import calcular_reparto_kwh_poruno


class CalcularRepartoKwhPorunoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        with (self.directory / "cups_list.csv").open(
            "w", encoding="utf-8", newline=""
        ) as cups_file:
            writer = csv.writer(cups_file)
            writer.writerow(["cups", "cif"])
            writer.writerow(["CUPS-1", "CIF-1"])
        (self.directory / "CUPS-1_8760_poruno_2026.txt").write_text(
            "CUPS-1;0001;0.250000\nCUPS-1;0002;0.250000\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_pvgis(self, path, values):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(f"{hour};{energy}\n" for hour, energy in values),
            encoding="utf-8",
        )

    def test_uses_custom_pvgis_file_relative_to_directory(self):
        self.write_pvgis(
            self.directory / "alternative" / "solar.txt",
            [(1, 100), (2, 200)],
        )

        result = calcular_reparto_kwh_poruno(
            self.directory,
            year=2026,
            pvgis_file="alternative/solar.txt",
        )

        self.assertEqual(result["total_available_kwh"], 300)
        with (self.directory / "cups_list_reparto.csv").open(
            encoding="utf-8", newline=""
        ) as output_file:
            rows = list(csv.DictReader(output_file))
        self.assertEqual(rows[0]["kwh_asignado"], "75.000000")
        self.assertEqual(rows[0]["pct_kwh_total"], "25.000000")

    def test_defaults_to_existing_pvgis_filename(self):
        self.write_pvgis(
            self.directory / "pvgis_indextime_spain.txt",
            [(1, 40), (2, 60)],
        )

        result = calcular_reparto_kwh_poruno(self.directory)

        self.assertEqual(result["total_available_kwh"], 100)

    def test_null_pvgis_file_uses_existing_default(self):
        self.write_pvgis(
            self.directory / "pvgis_indextime_spain.txt",
            [(1, 40), (2, 60)],
        )

        result = calcular_reparto_kwh_poruno(self.directory, pvgis_file=None)

        self.assertEqual(result["total_available_kwh"], 100)

    def test_missing_custom_pvgis_file_is_reported(self):
        with self.assertRaisesRegex(FileNotFoundError, "custom.txt"):
            calcular_reparto_kwh_poruno(
                self.directory,
                pvgis_file="custom.txt",
            )

    def test_pvgis_path_cannot_escape_directory(self):
        with self.assertRaisesRegex(ValueError, "permanecer dentro"):
            calcular_reparto_kwh_poruno(
                self.directory,
                pvgis_file="../outside.txt",
            )


if __name__ == "__main__":
    unittest.main()
