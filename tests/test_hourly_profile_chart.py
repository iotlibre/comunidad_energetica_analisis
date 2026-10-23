import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dashboard.utils.hourly_profile_chart import (
	_season_day_weights,
	build_community_seasonal_profile_figure,
	build_seasonal_profile_figure,
)


class HourlyProfileChartTests(unittest.TestCase):
	def test_community_seasonal_figure_averages_available_user_profiles(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			responses_dir = Path(temp_dir)
			hours = [str(hour) for hour in range(24)]
			for filename in ("weekday.csv", "weekend.csv"):
				pd.DataFrame(
					[{"month": month, **{hour: 1 for hour in hours}}
					 for month in range(1, 13)]
				).to_csv(responses_dir / filename, index=False)

			for cups_suffix, offset in (("11111", 0), ("22222", 10)):
				profile = {
					f"{day_type}_consumption": [
						{
							"month": month,
							**{
								hour: {
									"total_consumption_kWh": 1,
									"self_consumption_kWh": (
										None
										if cups_suffix == "22222" and hour == "1"
										else month + offset + day_offset
									),
									"total_generation": (
										None
										if cups_suffix == "22222" and hour == "1"
										else month * 2 + offset + day_offset
									),
								}
								for hour in hours
							},
						}
						for month in range(1, 13)
					]
					for day_type, day_offset in (("weekday", 0), ("weekend", 2))
				}
				(responses_dir / f"{cups_suffix}_day_profile_extended.json").write_text(
					json.dumps(profile), encoding="utf-8"
				)

			figure = build_community_seasonal_profile_figure(
				responses_dir / "weekday.csv",
				responses_dir / "weekend.csv",
				["2025-01"],
				{1, 2, 3, 10, 11, 12},
				"Invierno",
				profile_extended_directory=responses_dir,
			)

		self.assertEqual(
			_season_day_weights(["2025-04"], {4}),
			{"weekday": {4: 21}, "weekend": {4: 9}},
		)
		traces = {trace.name: trace for trace in figure.data}
		self.assertTrue(all(trace.yaxis in {None, "y"} for trace in figure.data))
		self.assertNotIn("yaxis2", figure.layout)
		self_consumption = traces["Autoconsumida media de los usuarios"]
		first_user_self_consumption = (21 * 1 + 10 * 3) / 31
		second_user_self_consumption = (21 * 11 + 10 * 13) / 31
		expected_self_consumption = (
			first_user_self_consumption + second_user_self_consumption
		) / 2
		self.assertAlmostEqual(self_consumption.y[0], expected_self_consumption)
		self.assertAlmostEqual(self_consumption.y[1], first_user_self_consumption)
		self.assertEqual(self_consumption.line.color, "#1b5e20")
		self.assertEqual(self_consumption.line.dash, "dash")
		self.assertEqual(
			self_consumption.fillcolor, "rgba(27, 94, 32, 0.16)"
		)

		generation = traces["Energía generada media de los usuarios"]
		first_user_generation = (21 * 2 + 10 * 4) / 31
		second_user_generation = (21 * 12 + 10 * 14) / 31
		expected_generation = (first_user_generation + second_user_generation) / 2
		self.assertAlmostEqual(generation.y[0], expected_generation)
		self.assertAlmostEqual(generation.y[1], first_user_generation)
		self.assertEqual(generation.line.color, "#ba68c8")
		self.assertEqual(generation.line.dash, "dot")
		self.assertEqual(
			generation.fillcolor, "rgba(186, 104, 200, 0.16)"
		)

	def test_community_seasonal_figure_rejects_invalid_extended_profile(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			responses_dir = Path(temp_dir)
			hours = [str(hour) for hour in range(24)]
			for filename in ("weekday.csv", "weekend.csv"):
				pd.DataFrame(
					[{"month": month, **{hour: 1 for hour in hours}}
					 for month in range(1, 13)]
				).to_csv(responses_dir / filename, index=False)
			(responses_dir / "invalid_day_profile_extended.json").write_text(
				"{}", encoding="utf-8"
			)

			with self.assertRaisesRegex(ValueError, "no contiene datos de weekday"):
				build_community_seasonal_profile_figure(
					responses_dir / "weekday.csv",
					responses_dir / "weekend.csv",
					["2025-01"],
					{1, 2, 3, 10, 11, 12},
					"Invierno",
					profile_extended_directory=responses_dir,
				)

	def test_seasonal_figure_includes_weighted_hourly_energy_means(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			responses_dir = Path(temp_dir)
			hours = [str(hour) for hour in range(24)]
			for filename in (
				"user_weekday.csv",
				"user_weekend.csv",
				"community_weekday.csv",
				"community_weekend.csv",
			):
				pd.DataFrame(
					[{"month": month, **{hour: 1 for hour in hours}}
					 for month in range(1, 13)]
				).to_csv(responses_dir / filename, index=False)

			profile = {
				f"{day_type}_consumption": [
					{
						"month": month,
						**{
							hour: {
								"total_consumption_kWh": 1,
								"self_consumption_kWh": month + offset,
								"total_generation": month * 2 + offset,
							}
							for hour in hours
						},
					}
					for month in range(1, 13)
				]
				for day_type, offset in (("weekday", 0), ("weekend", 2))
			}
			self_consumption_path = responses_dir / "12345_day_profile_extended.json"
			self_consumption_path.write_text(json.dumps(profile), encoding="utf-8")
			pvgis_path = responses_dir / "pvgis.json"
			pvgis_path.write_text(
				json.dumps(
					{
						"unidad": "kWh/usuario/hora",
						"valores": [
							{
								"hora": f"{hour:02d}:00",
								"generacion_media": 2,
								"muestras": 31,
							}
							for hour in range(24)
						],
					}
				),
				encoding="utf-8",
			)

			figure = build_seasonal_profile_figure(
				responses_dir / "user_weekday.csv",
				responses_dir / "user_weekend.csv",
				responses_dir / "community_weekday.csv",
				responses_dir / "community_weekend.csv",
				["2025-01"],
				"CUPS12345",
				{1, 2, 3, 10, 11, 12},
				"Invierno",
				pvgis_path,
				self_consumption_path,
			)
			summer_figure = build_seasonal_profile_figure(
				responses_dir / "user_weekday.csv",
				responses_dir / "user_weekend.csv",
				responses_dir / "community_weekday.csv",
				responses_dir / "community_weekend.csv",
				["2025-04"],
				"CUPS12345",
				{4, 5, 6, 7, 8, 9},
				"Verano",
				pvgis_path,
				self_consumption_path,
			)

		traces = {trace.name: trace for trace in figure.data}
		self_consumption = traces["Autoconsumida media por usuario"]
		self.assertEqual(len(self_consumption.x), 24)
		self.assertAlmostEqual(self_consumption.y[0], (21 * 1 + 10 * 3) / 31)
		self.assertEqual(self_consumption.line.color, "#1b5e20")
		self.assertEqual(self_consumption.line.dash, "dash")
		self.assertEqual(self_consumption.marker.symbol, "diamond")
		self.assertEqual(self_consumption.fill, "tozeroy")
		self.assertEqual(self_consumption.fillcolor, "rgba(27, 94, 32, 0.16)")
		generation = traces["Energía generada media por usuario"]
		self.assertAlmostEqual(generation.y[0], (21 * 2 + 10 * 4) / 31)
		self.assertEqual(generation.line.color, "#ba68c8")
		self.assertEqual(generation.line.dash, "dot")
		self.assertEqual(generation.marker.symbol, "triangle-up")
		self.assertEqual(generation.fill, "tozeroy")
		self.assertEqual(generation.fillcolor, "rgba(186, 104, 200, 0.16)")
		self.assertEqual(len(traces), 5)

		summer_self_consumption = {
			trace.name: trace for trace in summer_figure.data
		}["Autoconsumida media por usuario"]
		self.assertAlmostEqual(
			summer_self_consumption.y[0], (21 * 4 + 9 * 6) / 30
		)
		summer_generation = {
			trace.name: trace for trace in summer_figure.data
		}["Energía generada media por usuario"]
		self.assertAlmostEqual(summer_generation.y[0], (21 * 8 + 9 * 10) / 30)


if __name__ == "__main__":
	unittest.main()