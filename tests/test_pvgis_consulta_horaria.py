import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from api36 import SolicitudConsultaPvgis
from PVGIS_consulta_horaria_v03 import (
    DEFAULT_PARAMS,
    construir_url_pvgis,
    generar_pvgis_horario,
)


class PvgisConsultaHorariaTests(unittest.TestCase):
    def test_defaults_to_2018_and_queries_only_requested_year(self):
        self.assertEqual(DEFAULT_PARAMS["year"], 2018)
        self.assertEqual(SolicitudConsultaPvgis().year, 2018)
        self.assertIn("year", SolicitudConsultaPvgis.model_fields)
        self.assertNotIn("startyear", SolicitudConsultaPvgis.model_fields)
        self.assertNotIn("endyear", SolicitudConsultaPvgis.model_fields)
        url = construir_url_pvgis({**DEFAULT_PARAMS, "year": 2023})
        self.assertIn("startyear=2023&endyear=2023", url)

    def test_leap_year_output_has_8760_local_hours_and_zero_year_boundary(self):
        year = 2024
        start = datetime(year, 1, 1, 0, 10, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, 0, 10, tzinfo=timezone.utc)
        hourly = []
        timestamp = start
        while timestamp < end:
            hourly.append(
                {
                    "time": timestamp.strftime("%Y%m%d:%H%M"),
                    "P": len(hourly),
                }
            )
            timestamp += timedelta(hours=1)

        response = Mock(status_code=200)
        response.json.return_value = {"outputs": {"hourly": hourly}}
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pvgis_indextime_spain.txt"
            with patch(
                "PVGIS_consulta_horaria_v03.requests.get", return_value=response
            ) as get:
                result = generar_pvgis_horario(
                    {"year": year}, output_path=str(output_path)
                )
            get.assert_called_once()
            self.assertIn("startyear=2024&endyear=2024", get.call_args.args[0])
            self.assertEqual(result["hours"], 8760)
            self.assertEqual(result["parameters"]["year"], year)
            rows = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 8760)
            self.assertEqual(rows[0], "0001;0.0")
            self.assertEqual(rows[1], "0002;0.0")

            index_february_28_last_hour = 59 * 24 - 1
            value_february_28_last_hour = float(
                rows[index_february_28_last_hour].split(";")[1]
            )
            value_march_1_first_hour = float(
                rows[index_february_28_last_hour + 1].split(";")[1]
            )
            self.assertAlmostEqual(value_march_1_first_hour - value_february_28_last_hour, 0.025)

    def test_rejects_a_pvgis_series_that_does_not_cover_8760_hours(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "outputs": {"hourly": [{"time": "20180101:0010", "P": 0}]}
        }
        with patch("PVGIS_consulta_horaria_v03.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "se esperaban 8759"):
                generar_pvgis_horario({"year": 2018})


if __name__ == "__main__":
    unittest.main()
