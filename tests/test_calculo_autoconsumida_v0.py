import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from calculo_autoconsumida_v0 import _parse_date_time, _resolve_path, _load_proyeccion_json, calcular_proyeccion_autoconsumida


class ParseDateTimeTests(unittest.TestCase):
    def test_parse_time_2400_as_next_day_midnight(self):
        json_path = Path("responses/test.json")
        dt = _parse_date_time("2026/01/01", "24:00", json_path)
        self.assertEqual(dt, dt.replace(year=2026, month=1, day=2, hour=0, minute=0, second=0, microsecond=0))

    def test_resolve_path_prefers_workspace_relative_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pvgis_path = project_root / "responses" / "ce_Valdes3" / "pvgis_indextime_spain.txt"
            pvgis_path.parent.mkdir(parents=True, exist_ok=True)
            pvgis_path.write_text("0001;1.0\n", encoding="utf-8")

            json_dir = project_root / "responses" / "ce_Valdes3" / "consumos_2026"
            json_dir.mkdir(parents=True, exist_ok=True)

            previous_cwd = os.getcwd()
            os.chdir(project_root)
            try:
                with patch("calculo_autoconsumida_v0.PROJECT_ROOT", project_root):
                    resolved = _resolve_path("responses/ce_Valdes3/pvgis_indextime_spain.txt", json_dir)
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(resolved, pvgis_path)

    def test_load_proyeccion_json_handles_dst_repeat(self):
        from datetime import timezone
        from zoneinfo import ZoneInfo

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            json_path = temp_dir / "TESTCUPS_2026_10_2026_10.json"
            json_path.write_text(
                "[\n"
                "  {\"date\": \"2026/10/25\", \"time\": \"01:00\", \"consumptionKWh\": 1.0},\n"
                "  {\"date\": \"2026/10/25\", \"time\": \"02:00\", \"consumptionKWh\": 2.0},\n"
                "  {\"date\": \"2026/10/25\", \"time\": \"02:00\", \"consumptionKWh\": 3.0},\n"
                "  {\"date\": \"2026/10/25\", \"time\": \"03:00\", \"consumptionKWh\": 4.0}\n"
                "]",
                encoding="utf-8",
            )

            cups, year, consumption_by_index, datetime_by_index = _load_proyeccion_json(json_path)

            self.assertEqual(cups, "TESTCUPS")
            self.assertEqual(year, 2026)
            self.assertEqual(len(consumption_by_index), 4)

            tz = ZoneInfo("Europe/Madrid")
            year_start_utc = datetime(2026, 1, 1, tzinfo=tz).astimezone(timezone.utc)
            expected_indices = []
            for dt, fold in [
                (datetime(2026, 10, 25, 1, 0), 0),
                (datetime(2026, 10, 25, 2, 0), 0),
                (datetime(2026, 10, 25, 2, 0), 1),
                (datetime(2026, 10, 25, 3, 0), 0),
            ]:
                utc_dt = dt.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
                expected_indices.append(int((utc_dt - year_start_utc).total_seconds() // 3600) + 1)

            self.assertEqual(sorted(consumption_by_index.keys()), expected_indices)

    def test_load_proyeccion_json_maps_datadis_end_times_to_year_hours(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            json_path = temp_dir / "TESTCUPS_2025_12_2025_12.json"
            json_path.write_text(
                "["
                "{\"date\": \"2025/12/31\", \"time\": \"23:00\", \"consumptionKWh\": 1.0},"
                "{\"date\": \"2025/12/31\", \"time\": \"24:00\", \"consumptionKWh\": 2.0}"
                "]",
                encoding="utf-8",
            )

            _, year, consumption_by_index, _ = _load_proyeccion_json(json_path)

            self.assertEqual(year, 2025)
            self.assertEqual(sorted(consumption_by_index), [8759, 8760])

    def test_numeric_coef_file_is_applied_as_constant_across_hours(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            pvgis_path = temp_dir / "pvgis_indextime_spain.txt"
            pvgis_path.write_text("0001;10\n0002;10\n0003;10\n", encoding="utf-8")

            json_path = temp_dir / "TESTCUPS_2026_01_2026_01.json"
            json_path.write_text(
                """
                [
                  {"date": "2026/01/01", "time": "00:00", "consumptionKWh": 0.1},
                  {"date": "2026/01/01", "time": "01:00", "consumptionKWh": 0.1, "selfConsumptionEnergyKWh": 0.2},
                  {"date": "2026/01/01", "time": "02:00", "consumptionKWh": 0.1, "selfConsumptionEnergyKWh": 0.2}
                ]
                """,
                encoding="utf-8",
            )

            history_path = temp_dir / "historial.json"

            result = calcular_proyeccion_autoconsumida(
                str(json_path),
                pvgis_file=str(pvgis_path),
                coef_file="0.0232",
                historial_file=str(history_path),
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["horas_incluidas"], 3)
            self.assertEqual(result["missing_coef"], 0)
            self.assertAlmostEqual(result["energia_autoconsumida"], 0.564)
            self.assertAlmostEqual(result["energia_exportada"], 0.132)
            self.assertEqual(result["energia_importada"], 0.0)


if __name__ == "__main__":
    unittest.main()
