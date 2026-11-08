import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pvgis_perfiles_medios import (
    _local_timestamp_for_hour_offset,
    calcular_perfiles_medios_por_usuario,
)


class PvgisProfilesTests(unittest.TestCase):
    def test_returns_seasonal_hourly_means_per_user_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pvgis_path = Path(temp_dir) / "pvgis_indextime_spain.txt"
            timezone_spain = ZoneInfo("Europe/Madrid")
            year_start_utc = datetime(
                2023, 1, 1, tzinfo=timezone_spain
            ).astimezone(timezone.utc)
            rows = []
            for offset in range(8760):
                timestamp = (year_start_utc + timedelta(hours=offset)).astimezone(
                    timezone_spain
                )
                value = 12 if 4 <= timestamp.month <= 9 else 24
                rows.append(f"{offset + 1:04d};{value}\n")
            source_content = "".join(rows)
            pvgis_path.write_text(source_content, encoding="utf-8")

            result = calcular_perfiles_medios_por_usuario(str(pvgis_path), 4)

            self.assertEqual(result["num_usuarios"], 4)
            self.assertEqual(
                Path(result["ficheros_generados"]["verano"]).name,
                "pvgis_spain_profile_summer_2023.json",
            )
            self.assertEqual(
                Path(result["ficheros_generados"]["invierno"]).name,
                "pvgis_spain_profile_winter_2023.json",
            )
            summer_profile = json.loads(
                Path(result["ficheros_generados"]["verano"]).read_text(
                    encoding="utf-8"
                )
            )
            winter_profile = json.loads(
                Path(result["ficheros_generados"]["invierno"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(summer_profile["valores"]), 24)
            self.assertEqual(len(winter_profile["valores"]), 24)
            self.assertEqual(summer_profile["unidad"], "kWh/usuario/hora")
            self.assertTrue(
                all(
                    point["muestras"] == 183
                    and
                    point["generacion_media"] == 3
                    for point in summer_profile["valores"]
                )
            )
            self.assertTrue(
                all(
                    point["muestras"] == 182
                    and
                    point["generacion_media"] == 6
                    for point in winter_profile["valores"]
                )
            )
            self.assertEqual(pvgis_path.read_text(encoding="utf-8"), source_content)

    def test_hour_offsets_follow_spanish_spring_and_autumn_transitions(self):
        before_spring_change = _local_timestamp_for_hour_offset(2017)
        after_spring_change = _local_timestamp_for_hour_offset(2018)
        first_autumn_two_am = _local_timestamp_for_hour_offset(7225)
        second_autumn_two_am = _local_timestamp_for_hour_offset(7226)

        self.assertEqual(before_spring_change, datetime(2023, 3, 26, 1, tzinfo=ZoneInfo("Europe/Madrid")))
        self.assertEqual(after_spring_change, datetime(2023, 3, 26, 3, tzinfo=ZoneInfo("Europe/Madrid")))
        self.assertEqual(first_autumn_two_am.hour, 2)
        self.assertEqual(first_autumn_two_am.fold, 0)
        self.assertEqual(second_autumn_two_am.hour, 2)
        self.assertEqual(second_autumn_two_am.fold, 1)

    def test_configured_leap_year_uses_its_calendar_and_hour_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pvgis_path = Path(temp_dir) / "pvgis_indextime_spain.txt"
            pvgis_path.write_text(
                "".join(f"{index:04d};1\n" for index in range(1, 8785)),
                encoding="utf-8",
            )

            result = calcular_perfiles_medios_por_usuario(
                str(pvgis_path), 1, year=2024
            )

            self.assertEqual(result["year"], 2024)
            self.assertTrue(
                all(
                    point["muestras"] == 183
                    for season in ("verano", "invierno")
                    for point in json.loads(
                        Path(result["ficheros_generados"][season]).read_text(
                            encoding="utf-8"
                        )
                    )["valores"]
                )
            )

    def test_rejects_incomplete_source_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pvgis_path = Path(temp_dir) / "pvgis_indextime_spain.txt"
            pvgis_path.write_text("0001;1.0\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "8760"):
                calcular_perfiles_medios_por_usuario(str(pvgis_path), 1)


if __name__ == "__main__":
    unittest.main()