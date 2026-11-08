import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dashboard.utils.hourly_profile_chart import (
	apply_shared_seasonal_y_scale,
	build_day_type_profile_figure,
	build_community_seasonal_profile_figure,
	build_community_seasonal_day_type_profile_figure,
	build_seasonal_profile_figure,
	resolve_pvgis_profile_path,
)


SEASON_MONTHS = {10, 11, 12, 1, 2, 3}


def _write_community_profiles(responses_dir, weekday_value, weekend_value):
	hours = [str(hour) for hour in range(24)]
	for filename, values in (
		("perfil_comunitario_weekday.csv", weekday_value),
		("perfil_comunitario_weekend.csv", weekend_value),
	):
		pd.DataFrame(
			[
				{
					"month": month,
					**{
						hour: values(month, int(hour))
						if callable(values)
						else values
						for hour in hours
					},
				}
				for month in range(1, 13)
			]
		).to_csv(responses_dir / filename, index=False)


def _write_extended_profile(
	path,
	self_weekday,
	self_weekend,
	generation_weekday,
	generation_weekend,
):
	profile = {}
	for day_type, self_values, generation_values in (
		("weekday", self_weekday, generation_weekday),
		("weekend", self_weekend, generation_weekend),
	):
		profile[f"{day_type}_consumption"] = [
			{
				"month": month,
				**{
					str(hour): {
						"self_consumption_kWh": self_values(hour),
						"total_generation": generation_values(hour),
					}
					for hour in range(24)
				},
			}
			for month in range(1, 13)
		]
	path.write_text(json.dumps(profile), encoding="utf-8")


def _build_community_figure(responses_dir, months, pvgis_path=None):
	return build_community_seasonal_profile_figure(
		responses_dir / "perfil_comunitario_weekday.csv",
		responses_dir / "perfil_comunitario_weekend.csv",
		months,
		SEASON_MONTHS,
		"Perfil horario de consumo en invierno",
		responses_dir,
		pvgis_path,
	)


class HourlyProfileChartTests(unittest.TestCase):
	def setUp(self):
		self.temp_dir = tempfile.TemporaryDirectory()
		self.responses_dir = Path(self.temp_dir.name)
		_write_community_profiles(
			self.responses_dir,
			lambda month, hour: month,
			lambda month, hour: month * 10,
		)

	def tearDown(self):
		self.temp_dir.cleanup()

	def test_pvgis_profile_path_uses_latest_represented_year(self):
		for season in ("winter", "summer"):
			path = resolve_pvgis_profile_path(
				self.responses_dir,
				season,
				["2025-12", "2026-01", "2026-09"],
			)
			self.assertEqual(
				path,
				self.responses_dir / f"pvgis_spain_profile_{season}_2026.json",
			)

	def test_missing_pvgis_profile_path_keeps_other_series_available(self):
		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 0,
			lambda hour: 0,
			lambda hour: 0,
			lambda hour: 0,
		)
		pvgis_path = resolve_pvgis_profile_path(
			self.responses_dir, "summer", ["2026-04", "2026-09"]
		)
		self.assertFalse(pvgis_path.is_file())

		figure = build_community_seasonal_profile_figure(
			self.responses_dir / "perfil_comunitario_weekday.csv",
			self.responses_dir / "perfil_comunitario_weekend.csv",
			["2026-04"],
			{4, 5, 6, 7, 8, 9},
			"Perfil horario de consumo en verano",
			self.responses_dir,
		)

		traces = {trace.name for trace in figure.data}
		self.assertEqual(
			traces,
			{
				"Consumo medio de los usuarios",
				"Autoconsumida media de los usuarios",
				"Energía generada media de los usuarios",
			},
		)

	def test_community_season_selects_months_and_weights_national_holidays(self):
		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 0,
			lambda hour: 0,
			lambda hour: 0,
			lambda hour: 0,
		)
		figure = _build_community_figure(
			self.responses_dir, ["2025-01", "2025-02", "2025-04"]
		)

		community = figure.data[0]
		self.assertEqual(community.name, "Consumo medio de los usuarios")
		self.assertEqual(list(community.x), list(range(24)))
		self.assertAlmostEqual(community.y[0], 321 / 59)
		self.assertEqual(community.line.color, "#ef9a9a")
		self.assertEqual(community.line.dash, "solid")
		self.assertEqual(community.marker.symbol, "square")

	def test_community_chart_accepts_api_blanks_outside_period_and_rejects_invalid_values(self):
		hour_columns = [str(hour) for hour in range(24)]
		for filename, multiplier in (
			("perfil_comunitario_weekday.csv", 1),
			("perfil_comunitario_weekend.csv", 2),
		):
			rows = []
			for month in range(1, 13):
				row = {"month": month}
				for hour in range(24):
					row[str(hour)] = (
						month * multiplier
						if month <= 9
						else 10 * multiplier
						if month == 10 and hour == 0
						else None
					)
				rows.append(row)
			pd.DataFrame(rows, columns=["month", *hour_columns]).to_csv(
				self.responses_dir / filename, index=False
			)

		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
		)
		figure = build_community_seasonal_profile_figure(
			self.responses_dir / "perfil_comunitario_weekday.csv",
			self.responses_dir / "perfil_comunitario_weekend.csv",
			[f"2026-{month:02d}" for month in range(1, 10)],
			SEASON_MONTHS,
			"Perfil horario de consumo en invierno",
			self.responses_dir,
		)
		community_trace = next(
			trace
			for trace in figure.data
			if trace.name == "Consumo medio de los usuarios"
		)
		self.assertEqual(len(community_trace.y), 24)
		self.assertTrue(all(pd.notna(value) for value in community_trace.y))

		weekday_path = self.responses_dir / "perfil_comunitario_weekday.csv"
		weekday = pd.read_csv(weekday_path, keep_default_na=False)
		weekday.loc[weekday["month"] == 1, "0"] = ""
		weekday.to_csv(weekday_path, index=False)
		with self.assertRaisesRegex(ValueError, "valores horarios válidos"):
			build_community_seasonal_profile_figure(
				weekday_path,
				self.responses_dir / "perfil_comunitario_weekend.csv",
				[f"2026-{month:02d}" for month in range(1, 10)],
				SEASON_MONTHS,
				"Perfil horario de consumo en invierno",
				self.responses_dir,
			)

		weekday.loc[weekday["month"] == 1, "0"] = "dato-inválido"
		weekday.to_csv(weekday_path, index=False)
		with self.assertRaisesRegex(ValueError, "valores no numéricos"):
			build_community_seasonal_profile_figure(
				weekday_path,
				self.responses_dir / "perfil_comunitario_weekend.csv",
				[f"2026-{month:02d}" for month in range(1, 10)],
				SEASON_MONTHS,
				"Perfil horario de consumo en invierno",
				self.responses_dir,
			)

	def test_community_day_type_chart_accepts_api_blanks_outside_selected_season(self):
		hour_columns = [str(hour) for hour in range(24)]
		for filename, multiplier in (
			("perfil_comunitario_weekday.csv", 1),
			("perfil_comunitario_weekend.csv", 2),
		):
			rows = [
				{
				"month": month,
				**{
					str(hour): month * multiplier if month <= 9 else None
					for hour in range(24)
				},
				}
				for month in range(1, 13)
			]
			pd.DataFrame(rows, columns=["month", *hour_columns]).to_csv(
				self.responses_dir / filename, index=False
			)

		figure = build_community_seasonal_day_type_profile_figure(
			self.responses_dir / "perfil_comunitario_weekend.csv",
			self.responses_dir / "perfil_comunitario_weekday.csv",
			[f"2026-{month:02d}" for month in range(1, 10)],
			SEASON_MONTHS,
			"Perfil horario de consumo en invierno: festivo y laborable",
		)
		self.assertEqual(
			{trace.name for trace in figure.data},
			{"Día festivo", "Día laborable"},
		)
		self.assertTrue(all(len(trace.y) == 24 for trace in figure.data))
		self.assertTrue(
			all(pd.notna(value) for trace in figure.data for value in trace.y)
		)

	def test_extended_profiles_ignore_null_and_weight_each_cups_equally(self):
		_write_extended_profile(
			self.responses_dir / "a_day_profile_extended.json",
			lambda hour: 1,
			lambda hour: 3,
			lambda hour: 2,
			lambda hour: 4,
		)
		_write_extended_profile(
			self.responses_dir / "b_day_profile_extended.json",
			lambda hour: 5,
			lambda hour: None,
			lambda hour: 7,
			lambda hour: None,
		)
		figure = _build_community_figure(self.responses_dir, ["2025-01"])
		traces = {trace.name: trace for trace in figure.data}

		self.assertEqual(len(traces), 3)
		self.assertAlmostEqual(
			traces["Autoconsumida media de los usuarios"].y[0],
			((51 / 31) + 5) / 2,
		)
		self.assertAlmostEqual(
			traces["Energía generada media de los usuarios"].y[0],
			((82 / 31) + 7) / 2,
		)
		self.assertEqual(len(traces["Autoconsumida media de los usuarios"].x), 24)

	def test_community_chart_validates_pvgis_and_applies_required_styles(self):
		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 1,
			lambda hour: 3,
			lambda hour: 2,
			lambda hour: 4,
		)
		pvgis_path = self.responses_dir / "pvgis.json"
		pvgis_path.write_text(
			json.dumps(
				{
					"unidad": "kWh/usuario/hora",
					"valores": [
						{
							"hora": f"{hour:02d}:00",
							"generacion_media": hour / 10,
							"muestras": 1,
						}
						for hour in range(24)
					],
				}
			),
			encoding="utf-8",
		)
		figure = _build_community_figure(
			self.responses_dir, ["2025-01"], pvgis_path
		)
		traces = {trace.name: trace for trace in figure.data}
		self.assertEqual(
			set(traces),
			{
				"Consumo medio de los usuarios",
				"Generación PVGIS proporcional",
				"Autoconsumida media de los usuarios",
				"Energía generada media de los usuarios",
			},
		)
		for trace in traces.values():
			self.assertEqual(list(trace.x), list(range(24)))
			self.assertEqual(trace.mode, "lines+markers")
		self.assertEqual(traces["Generación PVGIS proporcional"].marker.symbol, "circle")
		self.assertEqual(
			traces["Generación PVGIS proporcional"].visible, "legendonly"
		)
		self.assertIsNone(traces["Consumo medio de los usuarios"].visible)
		self.assertIsNone(
			traces["Autoconsumida media de los usuarios"].visible
		)
		self.assertEqual(traces["Generación PVGIS proporcional"].fill, "tozeroy")
		self.assertEqual(traces["Autoconsumida media de los usuarios"].line.dash, "dash")
		self.assertEqual(traces["Autoconsumida media de los usuarios"].marker.symbol, "diamond")
		self.assertEqual(traces["Energía generada media de los usuarios"].line.dash, "dot")
		self.assertEqual(traces["Energía generada media de los usuarios"].marker.symbol, "triangle-up")
		self.assertEqual(figure.layout.xaxis.dtick, 1)
		self.assertEqual(figure.layout.yaxis.title.text, "Energía media (kWh/usuario/hora)")
		self.assertEqual(figure.layout.legend.orientation, "h")
		self.assertLess(figure.layout.legend.y, 0)

	def test_seasonal_figures_share_y_scale(self):
		_write_community_profiles(
			self.responses_dir,
			lambda month, hour: 2,
			lambda month, hour: 2,
		)
		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 2,
			lambda hour: 2,
			lambda hour: 2,
			lambda hour: 2,
		)
		winter = _build_community_figure(self.responses_dir, ["2025-01"])
		summer = build_community_seasonal_profile_figure(
			self.responses_dir / "perfil_comunitario_weekday.csv",
			self.responses_dir / "perfil_comunitario_weekend.csv",
			["2025-04"],
			{4, 5, 6, 7, 8, 9},
			"Perfil horario de consumo en verano",
			self.responses_dir,
		)

		y_max = apply_shared_seasonal_y_scale([winter, summer])
		self.assertAlmostEqual(y_max, 2.1)
		self.assertEqual(tuple(winter.layout.yaxis.range), (0, y_max))
		self.assertEqual(tuple(summer.layout.yaxis.range), (0, y_max))

	def test_community_holiday_weekday_figures_are_seasonal_and_share_scale(self):
		winter = build_community_seasonal_day_type_profile_figure(
			self.responses_dir / "perfil_comunitario_weekend.csv",
			self.responses_dir / "perfil_comunitario_weekday.csv",
			["2025-01", "2025-04"],
			SEASON_MONTHS,
			"Invierno",
		)
		summer = build_community_seasonal_day_type_profile_figure(
			self.responses_dir / "perfil_comunitario_weekend.csv",
			self.responses_dir / "perfil_comunitario_weekday.csv",
			["2025-01", "2025-04"],
			{4, 5, 6, 7, 8, 9},
			"Verano",
		)
		traces = {trace.name: trace for trace in winter.data}

		self.assertEqual(set(traces), {"Día festivo", "Día laborable"})
		self.assertAlmostEqual(traces["Día festivo"].y[0], 10)
		self.assertAlmostEqual(traces["Día laborable"].y[0], 1)
		for figure in (winter, summer):
			for trace in figure.data:
				self.assertEqual(list(trace.x), list(range(24)))
				self.assertEqual(trace.mode, "lines+markers")
			self.assertEqual(figure.layout.xaxis.dtick, 1)

		y_max = apply_shared_seasonal_y_scale([winter, summer])
		self.assertAlmostEqual(y_max, 42)
		self.assertEqual(tuple(winter.layout.yaxis.range), (0, y_max))
		self.assertEqual(tuple(summer.layout.yaxis.range), (0, y_max))

	def test_user_holiday_weekday_figures_are_seasonal_and_share_scale(self):
		user_weekday_path = self.responses_dir / "user_weekday.csv"
		user_weekend_path = self.responses_dir / "user_weekend.csv"
		_write_community_profiles(self.responses_dir, lambda month, hour: month,
			lambda month, hour: month * 10)
		pd.read_csv(
			self.responses_dir / "perfil_comunitario_weekday.csv"
		).to_csv(user_weekday_path, index=False)
		pd.read_csv(
			self.responses_dir / "perfil_comunitario_weekend.csv"
		).to_csv(user_weekend_path, index=False)

		def build_user_figure(months, season_months, title):
			return build_day_type_profile_figure(
				user_weekday_path,
				user_weekend_path,
				self.responses_dir / "perfil_comunitario_weekday.csv",
				self.responses_dir / "perfil_comunitario_weekend.csv",
				months,
				"CUPS12345",
				title,
				season_months,
			)

		winter = build_user_figure(
			["2025-01", "2025-04"],
			SEASON_MONTHS,
			"Invierno",
		)
		summer = build_user_figure(
			["2025-01", "2025-04"],
			{4, 5, 6, 7, 8, 9},
			"Verano",
		)
		winter_traces = {trace.name: trace for trace in winter.data}
		summer_traces = {trace.name: trace for trace in summer.data}
		self.assertEqual(len(winter_traces), 4)
		self.assertAlmostEqual(
			winter_traces["Usuario CUPS12345 — día festivo"].y[0], 10
		)
		self.assertAlmostEqual(
			winter_traces["Usuario CUPS12345 — día laborable"].y[0], 1
		)
		self.assertAlmostEqual(
			summer_traces["Usuario CUPS12345 — día festivo"].y[0], 40
		)
		self.assertAlmostEqual(
			summer_traces["Usuario CUPS12345 — día laborable"].y[0], 4
		)
		for figure in (winter, summer):
			figure_traces = {trace.name: trace for trace in figure.data}
			for trace in figure.data:
				self.assertEqual(list(trace.x), list(range(24)))
			self.assertIsNone(
				figure_traces["Usuario CUPS12345 — día festivo"].visible
			)
			self.assertIsNone(
				figure_traces["Usuario CUPS12345 — día laborable"].visible
			)
			self.assertEqual(
				figure_traces["Toda la comunidad — día festivo"].visible,
				"legendonly",
			)
			self.assertEqual(
				figure_traces["Toda la comunidad — día laborable"].visible,
				"legendonly",
			)
			self.assertEqual(
				figure.data[0].marker.symbol,
				"circle",
			)
			self.assertEqual(
				figure.data[2].marker.symbol,
				"square",
			)
		y_max = apply_shared_seasonal_y_scale([winter, summer])
		self.assertAlmostEqual(y_max, 42)
		self.assertEqual(tuple(winter.layout.yaxis.range), (0, y_max))
		self.assertEqual(tuple(summer.layout.yaxis.range), (0, y_max))

	def test_missing_or_invalid_sources_raise_clear_errors(self):
		with self.assertRaisesRegex(ValueError, "No existe el directorio"):
			build_community_seasonal_profile_figure(
				self.responses_dir / "perfil_comunitario_weekday.csv",
				self.responses_dir / "perfil_comunitario_weekend.csv",
				["2025-01"],
				SEASON_MONTHS,
				"Invierno",
				self.responses_dir / "missing",
			)

		with self.assertRaisesRegex(ValueError, "No hay archivos"):
			_build_community_figure(self.responses_dir, ["2025-01"])
		_write_extended_profile(
			self.responses_dir / "bad_day_profile_extended.json",
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
		)
		(self.responses_dir / "bad_day_profile_extended.json").write_text(
			"{invalid", encoding="utf-8"
		)
		with self.assertRaisesRegex(ValueError, "bad_day_profile_extended.json"):
			_build_community_figure(self.responses_dir, ["2025-01"])

	def test_missing_community_month_and_invalid_pvgis_are_rejected(self):
		_write_extended_profile(
			self.responses_dir / "cups_day_profile_extended.json",
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
			lambda hour: 1,
		)
		community_path = self.responses_dir / "perfil_comunitario_weekday.csv"
		profile = pd.read_csv(community_path)
		profile = profile[profile["month"] != 2]
		profile.to_csv(community_path, index=False)
		with self.assertRaisesRegex(ValueError, "meses necesarios"):
			_build_community_figure(
				self.responses_dir, ["2025-01", "2025-02"]
			)

		_write_community_profiles(
			self.responses_dir, lambda month, hour: 1, lambda month, hour: 1
		)
		pvgis_path = self.responses_dir / "pvgis.json"
		pvgis_path.write_text(
			json.dumps(
				{
					"unidad": "Wh/usuario/hora",
					"valores": [],
				}
			),
			encoding="utf-8",
		)
		with self.assertRaisesRegex(ValueError, "kWh/usuario/hora"):
			_build_community_figure(
				self.responses_dir, ["2025-01"], pvgis_path
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
		self.assertIsNone(traces["Usuario CUPS12345"].visible)
		self.assertEqual(traces["Toda la comunidad"].visible, "legendonly")
		self.assertEqual(
			traces["Generación PVGIS por usuario"].visible, "legendonly"
		)
		self_consumption = traces["Autoconsumida media por usuario"]
		self.assertEqual(len(self_consumption.x), 24)
		self.assertAlmostEqual(self_consumption.y[0], (23 * 1 + 8 * 3) / 31)
		self.assertEqual(self_consumption.line.color, "#1b5e20")
		self.assertEqual(self_consumption.line.dash, "dash")
		self.assertEqual(self_consumption.marker.symbol, "diamond")
		self.assertEqual(self_consumption.fill, "tozeroy")
		self.assertEqual(self_consumption.fillcolor, "rgba(27, 94, 32, 0.16)")
		generation = traces["Energía generada media por usuario"]
		self.assertAlmostEqual(generation.y[0], (23 * 2 + 8 * 4) / 31)
		self.assertEqual(generation.line.color, "#ba68c8")
		self.assertEqual(generation.line.dash, "dot")
		self.assertEqual(generation.marker.symbol, "triangle-up")
		self.assertEqual(generation.fill, "tozeroy")
		self.assertEqual(generation.fillcolor, "rgba(186, 104, 200, 0.16)")
		self.assertEqual(len(traces), 5)

		summer_self_consumption = {
			trace.name: trace for trace in summer_figure.data
		}["Autoconsumida media por usuario"]
		summer_traces = {trace.name: trace for trace in summer_figure.data}
		self.assertEqual(summer_traces["Toda la comunidad"].visible, "legendonly")
		self.assertEqual(
			summer_traces["Generación PVGIS por usuario"].visible, "legendonly"
		)
		self.assertAlmostEqual(
			summer_self_consumption.y[0], (22 * 4 + 8 * 6) / 30
		)
		summer_generation = {
			trace.name: trace for trace in summer_figure.data
		}["Energía generada media por usuario"]
		self.assertAlmostEqual(summer_generation.y[0], (22 * 8 + 8 * 10) / 30)


if __name__ == "__main__":
	unittest.main()