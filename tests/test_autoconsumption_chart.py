import unittest
from io import StringIO

import pandas as pd

from dashboard.utils.autoconsumption_chart import (
	calculate_community_renewable_percentage,
	build_user_renewable_percentage_csv,
	build_user_renewable_percentage_data,
	build_user_energy_balance_figure,
	build_user_energy_distribution_figures,
	build_user_renewable_percentage_figure,
)


class UserEnergyBalanceChartTests(unittest.TestCase):
	def test_builds_two_stacked_bars_sorted_by_consumption(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-B",
					"energia_importada_kWh": 7,
					"energia_autoconsumida_kWh": 1,
					"energia_generada_kWh": 3,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 4,
					"energia_autoconsumida_kWh": 2,
					"energia_generada_kWh": 6,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 6,
					"energia_autoconsumida_kWh": 3,
					"energia_generada_kWh": 8,
				},
			]
		)
		colors = {
			"Autoconsumida": "#66bb6a",
			"Importada": "#c62828",
			"Exportada": "#1976d2",
		}

		figure = build_user_energy_balance_figure(data, colors)

		self.assertEqual(
			figure.layout.yaxis.categoryarray, ("USER-A", "USER-B")
		)
		self.assertEqual(figure.layout.yaxis.autorange, "reversed")
		self.assertEqual(figure.layout.barmode, "stack")
		self.assertEqual(
			[trace.offsetgroup for trace in figure.data],
			[
				"consumo",
				"consumo",
				"autoconsumida_exportada",
				"autoconsumida_exportada",
			],
		)
		self.assertEqual(list(figure.data[0].x), [5, 1])
		self.assertEqual(list(figure.data[1].x), [10, 7])
		self.assertEqual(list(figure.data[2].x), [5, 1])
		self.assertEqual(list(figure.data[3].x), [9, 2])
		self.assertEqual(
			[trace.marker.color for trace in figure.data],
			[
				colors["Autoconsumida"],
				colors["Importada"],
				colors["Autoconsumida"],
				colors["Exportada"],
			],
		)
		self.assertEqual(figure.data[0].legendgroup, "autoconsumida")
		self.assertEqual(figure.data[2].legendgroup, "autoconsumida")
		self.assertTrue(figure.data[0].showlegend)
		self.assertFalse(figure.data[2].showlegend)
		self.assertEqual(figure.data[1].legendgroup, "importada")
		self.assertEqual(figure.data[3].legendgroup, "exportada")
		self.assertIsNone(figure.data[3].visible)
		self.assertEqual(figure.layout.legend.groupclick, "togglegroup")
		self.assertGreaterEqual(figure.layout.height, 400)
		self.assertTrue(figure.layout.yaxis.automargin)
		self.assertIn("%{y}", figure.data[0].hovertemplate)

	def test_balance_chart_grows_to_show_all_cups_without_a_fixed_height_cap(self):
		user_count = 30
		cups = [f"CUPS-{index:05d}" for index in range(user_count)]
		data = pd.DataFrame(
			[
				{
					"cups": cups[index],
					"energia_importada_kWh": index + 1,
					"energia_autoconsumida_kWh": 1,
					"energia_generada_kWh": index + 2,
				}
				for index in range(user_count)
			]
		)
		colors = {
			"Autoconsumida": "#66bb6a",
			"Importada": "#c62828",
			"Exportada": "#1976d2",
		}

		figure = build_user_energy_balance_figure(data, colors)

		self.assertEqual(figure.layout.height, 21 * user_count + 120)
		self.assertEqual(set(figure.layout.yaxis.categoryarray), set(cups))
		self.assertEqual(set(figure.data[0].y), set(cups))
		self.assertEqual(set(figure.data[1].y), set(cups))
		self.assertEqual(set(figure.data[2].y), set(cups))
		self.assertEqual(set(figure.data[3].y), set(cups))
		self.assertEqual(figure.layout.yaxis.title.text, "Usuario")


class UserRenewablePercentageChartTests(unittest.TestCase):
	def test_calculates_community_reference_as_generation_over_consumption(self):
		data = pd.DataFrame(
			[
				{
					"energia_generada_kWh": 40,
					"energia_consumida_kWh": 100,
				},
				{
					"energia_generada_kWh": 20,
					"energia_consumida_kWh": 50,
				},
			]
		)

		percentage = calculate_community_renewable_percentage(data)

		self.assertAlmostEqual(percentage, 40)

	def test_community_reference_is_undefined_when_community_has_no_consumption(self):
		data = pd.DataFrame(
			[
				{
					"energia_generada_kWh": 20,
					"energia_consumida_kWh": 0,
				}
			]
		)

		self.assertIsNone(calculate_community_renewable_percentage(data))

	def test_download_data_has_one_row_per_cups_and_expected_energy_values(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-A",
					"energia_importada_kWh": 4,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 6,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 6,
					"energia_autoconsumida_kWh": 3,
					"energia_exportada_kWh": 8,
				},
				{
					"cups": "NO-CONSUMPTION",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 2,
				},
			]
		)

		download_data = build_user_renewable_percentage_data(data, 40)
		csv_data = pd.read_csv(StringIO(download_data.to_csv(index=False)))

		self.assertEqual(
			list(csv_data.columns),
			[
				"CUPS",
				"Generada [kWh]",
				"Consumida [kWh]",
				"Porcentaje de energía renovable",
				"Porcentaje comunitario de referencia",
			],
		)
		self.assertEqual(len(csv_data), 2)
		self.assertEqual(csv_data["CUPS"].tolist(), ["USER-A", "NO-CONSUMPTION"])
		user_a = csv_data.iloc[0]
		self.assertEqual(user_a["Generada [kWh]"], 19)
		self.assertEqual(user_a["Consumida [kWh]"], 15)
		self.assertAlmostEqual(
			user_a["Porcentaje de energía renovable"], 19 / 15 * 100
		)
		self.assertEqual(user_a["Porcentaje comunitario de referencia"], 40)
		no_consumption = csv_data.iloc[1]
		self.assertEqual(no_consumption["Generada [kWh]"], 2)
		self.assertEqual(no_consumption["Consumida [kWh]"], 0)
		self.assertTrue(pd.isna(no_consumption["Porcentaje de energía renovable"]))
		self.assertEqual(no_consumption["Porcentaje comunitario de referencia"], 40)

	def test_download_data_leaves_undefined_percentages_blank(self):
		data = pd.DataFrame(
			[
				{
					"cups": "NO-CONSUMPTION",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 2,
				}
			]
		)

		csv_data = build_user_renewable_percentage_data(data).to_csv(index=False)
		downloaded = pd.read_csv(StringIO(csv_data))

		self.assertTrue(pd.isna(downloaded.loc[0, "Porcentaje de energía renovable"]))
		self.assertTrue(pd.isna(downloaded.loc[0, "Porcentaje comunitario de referencia"]))

	def test_download_csv_rounds_numeric_values_to_two_decimal_places(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-A",
					"energia_importada_kWh": 1.234,
					"energia_autoconsumida_kWh": 2.345,
					"energia_exportada_kWh": 3.456,
				}
			]
		)

		csv_data = build_user_renewable_percentage_csv(data, 12.346)
		downloaded = pd.read_csv(StringIO(csv_data))
		user = downloaded.iloc[0]

		self.assertEqual(user["Generada [kWh]"], 5.8)
		self.assertEqual(user["Consumida [kWh]"], 3.58)
		self.assertEqual(user["Porcentaje de energía renovable"], 162.08)
		self.assertEqual(user["Porcentaje comunitario de referencia"], 12.35)

	def test_calculates_renewable_percentage_per_user_as_horizontal_blue_bars(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-B",
					"energia_importada_kWh": 7,
					"energia_autoconsumida_kWh": 1,
					"energia_exportada_kWh": 25,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 4,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 6,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 6,
					"energia_autoconsumida_kWh": 3,
					"energia_exportada_kWh": 8,
				},
			]
		)

		figure = build_user_renewable_percentage_figure(data)

		self.assertEqual(figure.data[0].orientation, "h")
		self.assertEqual(
			list(figure.data[0].marker.color), ["#1976d2", "#1976d2"]
		)
		self.assertEqual(list(figure.data[0].y), ["USER-A", "USER-B"])
		self.assertAlmostEqual(figure.data[0].x[0], 19 / 15 * 100)
		self.assertAlmostEqual(figure.data[0].x[1], 26 / 8 * 100)
		self.assertEqual(list(figure.data[0].text), ["126,7%", "325,0%"])
		self.assertIn("(%)", figure.layout.xaxis.title.text)

	def test_colors_bars_by_community_and_hundred_percent_thresholds(self):
		data = pd.DataFrame(
			[
				{
					"cups": f"USER-{percentage}",
					"energia_importada_kWh": 100,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": percentage,
				}
				for percentage in (40, 80, 120)
			]
			+ [
				{
					"cups": "NO-CONSUMPTION",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 5,
				}
			]
		)

		figure = build_user_renewable_percentage_figure(data, 60)

		colors_by_cups = dict(zip(figure.data[0].y, figure.data[0].marker.color))
		self.assertEqual(colors_by_cups["USER-40"], "#2e7d32")
		self.assertEqual(colors_by_cups["USER-80"], "#7b1fa2")
		self.assertEqual(colors_by_cups["USER-120"], "#1976d2")
		self.assertEqual(colors_by_cups["NO-CONSUMPTION"], "#2e7d32")

	def test_colors_bars_coherently_without_reference_or_above_100_reference(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-80",
					"energia_importada_kWh": 100,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 80,
				},
				{
					"cups": "USER-120",
					"energia_importada_kWh": 100,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 120,
				},
			]
		)

		figure_without_reference = build_user_renewable_percentage_figure(data)
		figure_with_high_reference = build_user_renewable_percentage_figure(
			data, 110
		)

		colors_without_reference = dict(
			zip(
				figure_without_reference.data[0].y,
				figure_without_reference.data[0].marker.color,
			)
		)
		colors_with_high_reference = dict(
			zip(
				figure_with_high_reference.data[0].y,
				figure_with_high_reference.data[0].marker.color,
			)
		)
		self.assertEqual(colors_without_reference["USER-80"], "#7b1fa2")
		self.assertEqual(colors_without_reference["USER-120"], "#1976d2")
		self.assertEqual(colors_with_high_reference["USER-80"], "#2e7d32")
		self.assertEqual(colors_with_high_reference["USER-120"], "#1976d2")

	def test_adds_green_community_and_purple_hundred_percent_reference_lines(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-A",
					"energia_importada_kWh": 10,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 1,
				}
			]
		)

		figure = build_user_renewable_percentage_figure(data, 42.5)

		self.assertEqual(len(figure.layout.shapes), 2)
		self.assertEqual(
			[shape.x0 for shape in figure.layout.shapes], [42.5, 100]
		)
		self.assertEqual(
			[shape.line.color for shape in figure.layout.shapes],
			["#2e7d32", "#7b1fa2"],
		)
		self.assertEqual(
			[annotation.text for annotation in figure.layout.annotations],
			["Comunidad (42.5%)", "100 %"],
		)
		self.assertEqual(
			[annotation.yanchor for annotation in figure.layout.annotations],
			["bottom", "bottom"],
		)
		self.assertGreaterEqual(figure.layout.xaxis.range[1], 100)
		self.assertGreaterEqual(figure.layout.xaxis.range[1], 42.5)

	def test_labels_users_with_zero_consumption_without_dividing_by_zero(self):
		data = pd.DataFrame(
			[
				{
					"cups": "NO-CONSUMPTION",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 2,
				},
				{
					"cups": "WITH-CONSUMPTION",
					"energia_importada_kWh": 1,
					"energia_autoconsumida_kWh": 1,
					"energia_exportada_kWh": 0,
				},
			]
		)

		figure = build_user_renewable_percentage_figure(data)

		self.assertEqual(
			list(figure.data[0].y), ["WITH-CONSUMPTION", "NO-CONSUMPTION"]
		)
		self.assertEqual(list(figure.data[0].text), ["50,0%", "Sin consumo"])
		self.assertEqual(list(figure.data[0].x), [50, 0])

	def test_chart_reduces_height_by_about_twenty_percent_and_shows_every_cups(self):
		user_count = 30
		cups = [f"ES00000000000{index:05d}" for index in range(user_count)]
		data = pd.DataFrame(
			[
				{
					"cups": cup,
					"energia_importada_kWh": 10,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 1,
				}
				for cup in cups
			]
		)

		figure = build_user_renewable_percentage_figure(data)

		previous_height = 14 * user_count + 60
		self.assertAlmostEqual(
			1 - figure.layout.height / previous_height, 0.2, delta=0.02
		)
		self.assertTrue(figure.layout.yaxis.automargin)
		self.assertEqual(figure.layout.yaxis.showticklabels, False)
		self.assertIn("%{y}", figure.data[0].hovertemplate)
		self.assertEqual(set(figure.layout.yaxis.categoryarray), set(cups))
		self.assertEqual(set(figure.data[0].y), set(cups))
		self.assertEqual(len(figure.data[0].y), user_count)
		self.assertEqual(len(figure.data[0].text), user_count)

	def test_chart_minimum_height_is_reduced_for_few_users(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-A",
					"energia_importada_kWh": 10,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 1,
				},
				{
					"cups": "USER-B",
					"energia_importada_kWh": 10,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 1,
				},
			]
		)

		figure = build_user_renewable_percentage_figure(data)

		self.assertEqual(figure.layout.height, 160)
		self.assertEqual(len(figure.data[0].y), 2)


class UserEnergyDistributionChartTests(unittest.TestCase):
	def test_builds_pies_from_period_totals_and_keeps_zero_value_users(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-B",
					"energia_importada_kWh": 7,
					"energia_autoconsumida_kWh": 1,
					"energia_exportada_kWh": 25,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 4,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 6,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 6,
					"energia_autoconsumida_kWh": 3,
					"energia_exportada_kWh": 8,
				},
				{
					"cups": "USER-ZERO",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 0,
				},
			]
		)

		consumption_figure, renewable_figure = (
			build_user_energy_distribution_figures(data)
		)

		self.assertEqual(
			list(consumption_figure.data[0].labels),
			["USER-A", "USER-B", "USER-ZERO"],
		)
		self.assertEqual(list(consumption_figure.data[0].values), [15, 8, 0])
		self.assertEqual(
			list(renewable_figure.data[0].labels),
			["USER-A", "USER-B", "USER-ZERO"],
		)
		self.assertEqual(list(renewable_figure.data[0].values), [19, 26, 0])
		self.assertEqual(
			renewable_figure.data[0].marker.colors,
			("#263238", "#cfd8dc", "#263238"),
		)
		self.assertEqual(renewable_figure.data[0].textinfo, "none")
		self.assertEqual(renewable_figure.data[0].direction, "clockwise")
		self.assertEqual(
			consumption_figure.data[0].marker.colors,
			("#263238", "#cfd8dc", "#263238"),
		)
		self.assertEqual(consumption_figure.data[0].textinfo, "none")
		self.assertEqual(consumption_figure.data[0].direction, "clockwise")
		self.assertEqual(
			renewable_figure.data[0].hovertemplate,
			"%{customdata}<br>%{percent}<br>%{value:.2f} kWh<extra></extra>",
		)
		self.assertEqual(
			list(renewable_figure.data[0].customdata),
			["USER-A", "USER-B", "USER-ZERO"],
		)
		self.assertEqual(
			consumption_figure.data[0].hovertemplate,
			"%{customdata}<br>%{percent}<br>%{value:.2f} kWh<extra></extra>",
		)
		self.assertEqual(
			list(consumption_figure.data[0].customdata),
			["USER-A", "USER-B", "USER-ZERO"],
		)
		self.assertEqual(
			renewable_figure.data[0].hovertemplate,
			consumption_figure.data[0].hovertemplate,
		)
		self.assertFalse(consumption_figure.data[0].showlegend)

	def test_both_pies_use_descending_consumption_order(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-C",
					"energia_importada_kWh": 1,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 0,
				},
				{
					"cups": "USER-A",
					"energia_importada_kWh": 9,
					"energia_autoconsumida_kWh": 1,
					"energia_exportada_kWh": 0,
				},
				{
					"cups": "USER-B",
					"energia_importada_kWh": 3,
					"energia_autoconsumida_kWh": 2,
					"energia_exportada_kWh": 0,
				},
			]
		)

		consumption_figure, renewable_figure = (
			build_user_energy_distribution_figures(data)
		)

		self.assertEqual(
			list(consumption_figure.data[0].labels),
			["USER-A", "USER-B", "USER-C"],
		)
		self.assertEqual(list(consumption_figure.data[0].values), [10, 5, 1])
		self.assertEqual(
			consumption_figure.data[0].marker.colors,
			("#263238", "#cfd8dc", "#263238"),
		)
		self.assertEqual(
			list(renewable_figure.data[0].labels),
			["USER-A", "USER-B", "USER-C"],
		)
		self.assertEqual(list(renewable_figure.data[0].values), [1, 2, 0])
		self.assertEqual(
			renewable_figure.data[0].marker.colors,
			("#263238", "#cfd8dc", "#263238"),
		)

	def test_returns_no_pie_when_a_magnitude_has_zero_total(self):
		data = pd.DataFrame(
			[
				{
					"cups": "USER-A",
					"energia_importada_kWh": 0,
					"energia_autoconsumida_kWh": 0,
					"energia_exportada_kWh": 5,
				},
			]
		)

		consumption_figure, renewable_figure = (
			build_user_energy_distribution_figures(data)
		)

		self.assertIsNone(consumption_figure)
		self.assertIsNotNone(renewable_figure)


if __name__ == "__main__":
	unittest.main()
