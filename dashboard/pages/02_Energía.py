import streamlit as st
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

dashboard_dir = Path(__file__).resolve().parents[1]
project_root = dashboard_dir.parent
if str(dashboard_dir) not in sys.path:
	sys.path.insert(0, str(dashboard_dir))
if str(project_root) not in sys.path:
	sys.path.insert(0, str(project_root))

from utils.autoconsumption_chart import (
	calculate_community_renewable_percentage,
	build_user_renewable_percentage_csv,
	build_user_energy_balance_figure,
	build_user_energy_distribution_figures,
	build_user_renewable_percentage_figure,
	find_autoconsumption_files,
	load_autoconsumption_data,
)
from utils.hourly_profile_chart import (
	apply_shared_seasonal_y_scale,
	build_community_seasonal_profile_figure,
	build_community_seasonal_day_type_profile_figure,
	build_day_type_profile_figure,
	resolve_pvgis_profile_path,
	build_seasonal_profile_figure,
)
from auth import require_dashboard_login
from utils.work_directory import select_work_directory

st.set_page_config(page_title="Energía", layout="wide")
require_dashboard_login()
st.title("Energía")


def build_annual_summary(entity_data, community_data):
	metrics = [
		("Consumo total [kWh/año]", "energia_consumida_kWh"),
		("Consumo FV [kWh/año]", "energia_autoconsumida_kWh"),
		("Generación correspondiente [kWh/año]", "energia_generada_kWh"),
	]
	rows = []
	for label, column in metrics:
		value = entity_data[column].sum()
		community_total = community_data[column].sum()
		percentage = value / community_total * 100 if community_total else None
		rows.append(
			{
				"Medida": label,
				"Valores": f"{value:,.0f}".replace(",", "."),
				"Porcentual": (
					f"{percentage:.1f}%".replace(".", ",")
					if percentage is not None
					else "—"
				),
			}
		)
	return pd.DataFrame(rows)


def build_monthly_energy_figure(data, title):
	figure = go.Figure()
	figure.add_bar(
		name="Autoconsumida",
		x=data["mes"],
		y=data["energia_autoconsumida_kWh"],
		offsetgroup="importada",
		marker_color=metric_colors["Autoconsumida"],
	)
	figure.add_bar(
		name="Importada",
		x=data["mes"],
		y=data["energia_importada_kWh"],
		offsetgroup="importada",
		marker_color=metric_colors["Importada"],
	)
	figure.add_bar(
		name="Autoconsumida",
		x=data["mes"],
		y=data["energia_autoconsumida_kWh"],
		offsetgroup="exportada",
		marker_color=metric_colors["Autoconsumida"],
		showlegend=False,
	)
	figure.add_bar(
		name="Exportada",
		x=data["mes"],
		y=data["energia_exportada_kWh"],
		offsetgroup="exportada",
		marker_color=metric_colors["Exportada"],
	)
	figure.update_layout(
		barmode="stack",
		bargroupgap=0.1,
		title=title,
		xaxis_title="Mes",
		yaxis_title="Energía (kWh)",
		legend_title_text="Magnitud",
	)
	return figure


responses_root = Path(__file__).resolve().parents[2] / "responses"
responses_dir = (
	select_work_directory(responses_root, "work_directory_energy")
	or responses_root
)
if not responses_dir.is_dir():
	st.warning(f"No se encontró el directorio: {responses_dir}")


metric_columns = {
	"Importada": "energia_importada_kWh",
	"Autoconsumida": "energia_autoconsumida_kWh",
	"Exportada": "energia_exportada_kWh",
	"Generada": "energia_generada_kWh",
}
metric_colors = {
	"Importada": "#c62828",
	"Autoconsumida": "#66bb6a",
	"Exportada": "#1976d2",
	"Generada": "#2e7d32",
	"Consumida": "#ef5350",
}
community_tab, user_tab = st.tabs(["Comunidad", "Usuario"])

with community_tab:
	st.subheader("Estado de la comunidad")

	autoconsumption_files = find_autoconsumption_files(responses_dir)
	autoconsumption_data = None
	selected_autoconsumption_path = None
	if not autoconsumption_files:
		st.warning(
			"No se encontraron ficheros de energía autoconsumida con el formato "
			"energia_autoconsumida_<fecha_inicio>_<fecha_final>.csv."
		)
	else:
		selected_autoconsumption_path = st.selectbox(
			"Fichero de energía autoconsumida",
			autoconsumption_files,
			format_func=lambda path: path.name,
			key=f"autoconsumption_file_{responses_dir.name}",
		)
		try:
			autoconsumption_data = load_autoconsumption_data(
				selected_autoconsumption_path
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(f"No se pudo preparar la energía autoconsumida: {error}")

	if autoconsumption_data is not None:
		community_data = (
			autoconsumption_data.groupby("mes", as_index=False)[
				[
					"energia_importada_kWh",
					"energia_autoconsumida_kWh",
					"energia_exportada_kWh",
					"energia_generada_kWh",
				]
			].sum()
		)
		community_data["energia_consumida_kWh"] = (
			community_data["energia_importada_kWh"]
			+ community_data["energia_autoconsumida_kWh"]
		)
		community_profile_paths = {
			"weekday": responses_dir / "perfil_comunitario_weekday.csv",
			"weekend": responses_dir / "perfil_comunitario_weekend.csv",
		}
		missing_community_profiles = [
			path.name for path in community_profile_paths.values() if not path.is_file()
		]
		community_months = community_data["mes"].astype(str).unique().tolist()

		st.caption(
			f"Fichero: {selected_autoconsumption_path.name} | Unidad: kWh"
		)
		st.subheader("Total de la comunidad energética")
		community_cards = st.columns(len(metric_columns))
		for card, (label, column) in zip(community_cards, metric_columns.items()):
			card.metric(label, f"{community_data[column].sum():,.2f} kWh")

		community_figure = build_monthly_energy_figure(
			community_data,
			title="Evolución mensual de la comunidad energética",
		)
		community_chart_column, community_summary_column = st.columns(
			[18, 7], gap="medium"
		)
		with community_chart_column:
			st.plotly_chart(community_figure, use_container_width=True)
		with community_summary_column:
			st.caption("Porcentaje respecto al total comunitario de cada medida.")
			st.dataframe(
				build_annual_summary(community_data, community_data),
				hide_index=True,
				width="stretch",
			)

		season_columns = st.columns(2)
		community_season_figures = []
		if not responses_dir.is_dir():
			st.error(f"No existe el directorio de perfiles: {responses_dir}.")
		elif missing_community_profiles:
			st.error(
				"No se encontraron los perfiles horarios comunitarios necesarios: "
				+ ", ".join(missing_community_profiles)
			)
		else:
			for column, title, season_months, season_name in (
				(
					season_columns[0],
					"Perfil horario de consumo en invierno",
					{10, 11, 12, 1, 2, 3},
					"invierno",
				),
				(
					season_columns[1],
					"Perfil horario de consumo en verano",
					{4, 5, 6, 7, 8, 9},
					"verano",
				),
			):
				with column:
					st.subheader(title)
					pvgis_season = "winter" if season_name == "invierno" else "summer"
					pvgis_path = resolve_pvgis_profile_path(
						responses_dir, pvgis_season, community_months
					)
					if not pvgis_path.is_file():
						st.warning(
							f"No se encontró el perfil PVGIS: {pvgis_path.name}. "
							"Se mostrarán las demás series disponibles."
						)
						pvgis_path = None
					try:
						figure = build_community_seasonal_profile_figure(
							community_profile_paths["weekday"],
							community_profile_paths["weekend"],
							community_months,
							season_months,
							title,
							responses_dir,
							pvgis_path,
						)
					except (OSError, ValueError, TypeError) as error:
						st.error(
							f"No se pudo preparar el perfil comunitario de {season_name}: {error}"
						)
					else:
						community_season_figures.append((column, figure))
		if community_season_figures:
			apply_shared_seasonal_y_scale(
				[figure for _, figure in community_season_figures]
			)
			for column, figure in community_season_figures:
				with column:
					st.plotly_chart(figure, use_container_width=True)

		if missing_community_profiles:
			st.error(
				"No se pueden preparar los perfiles estacionales de festivo y "
				"laborable; faltan: " + ", ".join(missing_community_profiles)
			)
		else:
			community_day_type_columns = st.columns(2)
			community_day_type_figures = []
			try:
				for column, season_name, season_months in (
					(
						community_day_type_columns[0],
						"invierno",
						{10, 11, 12, 1, 2, 3},
					),
					(
						community_day_type_columns[1],
						"verano",
						{4, 5, 6, 7, 8, 9},
					),
				):
					title = (
						f"Perfil horario de consumo en {season_name}: "
						"día festivo y día laborable"
					)
					figure = build_community_seasonal_day_type_profile_figure(
						community_profile_paths["weekend"],
						community_profile_paths["weekday"],
						community_months,
						season_months,
						title,
					)
					community_day_type_figures.append((column, title, figure))
			except (OSError, ValueError, TypeError) as error:
				community_day_type_figures = []
				st.error(
					"No se pudieron preparar las gráficas estacionales de festivo "
					f"y laborable: {error}"
				)
			if community_day_type_figures:
				apply_shared_seasonal_y_scale(
					[figure for _, _, figure in community_day_type_figures]
				)
				for column, title, figure in community_day_type_figures:
					with column:
						st.subheader(title)
						st.plotly_chart(figure, use_container_width=True)

	if selected_autoconsumption_path is not None and autoconsumption_data is not None:
		st.subheader("Porcentaje de energía renovable por usuario")
		st.caption(
			"(Autoconsumida + exportada) / (Autoconsumida + importada) × 100"
		)
		try:
			community_reference_percentage = calculate_community_renewable_percentage(
				community_data
			)
			renewable_percentage_figure = build_user_renewable_percentage_figure(
				autoconsumption_data,
				community_reference_percentage,
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(
				f"No se pudo preparar el porcentaje de energía renovable por usuario: {error}"
			)
		else:
			st.plotly_chart(
				renewable_percentage_figure, use_container_width=True
			)
			st.download_button(
				"Descargar datos del porcentaje de energía renovable",
				data=build_user_renewable_percentage_csv(
					autoconsumption_data,
					community_reference_percentage,
				),
				file_name="porcentaje_energia_renovable_por_usuario.csv",
				mime="text/csv",
			)

	st.subheader("Balance energético por usuario")
	if selected_autoconsumption_path is None:
		st.warning(
			"Selecciona un fichero de energía autoconsumida para generar el balance."
		)
	elif autoconsumption_data is None:
		st.warning(
			"No se puede generar el balance porque el fichero seleccionado no se "
			"pudo procesar."
		)
	else:
		st.caption(
			"Por usuario: consumo (autoconsumida + importada) y "
			"autoconsumida + exportada."
		)
		try:
			st.caption(
				f"Fichero: {selected_autoconsumption_path.name} | Unidad: kWh"
			)
			balance_figure = build_user_energy_balance_figure(
				autoconsumption_data,
				metric_colors,
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(f"No se pudo preparar el balance energético por usuario: {error}")
		else:
			st.plotly_chart(balance_figure, use_container_width=True)

		try:
			consumption_pie, renewable_pie = (
				build_user_energy_distribution_figures(autoconsumption_data)
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(f"No se pudieron preparar los gráficos de distribución: {error}")
		else:
			pie_columns = st.columns(2)
			for column, title, figure in (
				(pie_columns[0], "Consumo por usuario", consumption_pie),
				(
					pie_columns[1],
					"Energía renovable por usuario",
					renewable_pie,
				),
			):
				with column:
					st.subheader(title)
					if figure is None:
						st.info(
							f"No hay energía total para mostrar el gráfico «{title}»."
						)
					else:
						st.plotly_chart(figure, use_container_width=True)

with user_tab:
	st.subheader("Estado de un usuario")

	if autoconsumption_data is None:
		st.warning(
			"Selecciona un fichero de energía autoconsumida válido en el apartado Comunidad."
		)
	else:
		cups_options = sorted(autoconsumption_data["cups"].unique())
		if not cups_options:
			st.warning("El fichero seleccionado no contiene usuarios.")
			st.stop()
		selected_cups = st.selectbox(
			"Selecciona un CUPS",
			cups_options,
			key=(
				f"user_cups_{responses_dir.name}_"
				f"{selected_autoconsumption_path.name}"
			),
		)
		user_data = autoconsumption_data[
			autoconsumption_data["cups"] == selected_cups
		].copy()
		user_data["energia_consumida_kWh"] = (
			user_data["energia_importada_kWh"]
			+ user_data["energia_autoconsumida_kWh"]
		)
		st.caption(
			f"Fichero: {selected_autoconsumption_path.name} | "
			f"CUPS seleccionado: {selected_cups} | Unidad: kWh"
		)

		user_cards = st.columns(len(metric_columns))
		for card, (label, column) in zip(user_cards, metric_columns.items()):
			card.metric(label, f"{user_data[column].sum():,.2f} kWh")

		user_figure = build_monthly_energy_figure(
			user_data,
			title=f"Evolución mensual del usuario {selected_cups}",
		)
		user_chart_column, user_summary_column = st.columns([18, 7], gap="medium")
		with user_chart_column:
			st.plotly_chart(user_figure, use_container_width=True)
		with user_summary_column:
			st.caption("Porcentaje respecto al total comunitario de cada medida.")
			st.dataframe(
				build_annual_summary(user_data, community_data),
				hide_index=True,
				width="stretch",
			)
			selected_consumption = user_data["energia_consumida_kWh"].sum()
			community_consumption = community_data["energia_consumida_kWh"].sum()
			consumption_composition = pd.DataFrame(
				{
					"Parte": ["CUPS seleccionado", "Resto de la comunidad"],
					"Consumo_kWh": [
						selected_consumption,
						community_consumption - selected_consumption,
					],
				}
			)
			composition_figure = px.pie(
				consumption_composition,
				names="Parte",
				values="Consumo_kWh",
				color="Parte",
				color_discrete_map={
					"CUPS seleccionado": metric_colors["Consumida"],
					"Resto de la comunidad": "#b0bec5",
				},
			)
			composition_figure.update_traces(
				textposition="inside",
				textinfo="percent",
				showlegend=False,
				domain={"x": [0.125, 0.875], "y": [0.125, 0.875]},
				hovertemplate="%{percent}<br>%{value:.2f} kWh<extra></extra>",
			)
			composition_figure.update_layout(
				height=225,
				margin={"t": 10, "b": 10, "l": 5, "r": 5},
				showlegend=False,
			)
			selected_generation = user_data["energia_generada_kWh"].sum()
			community_generation = community_data["energia_generada_kWh"].sum()
			generation_composition = pd.DataFrame(
				{
					"Parte": ["CUPS seleccionado", "Resto de la comunidad"],
					"Generacion_kWh": [
						selected_generation,
						community_generation - selected_generation,
					],
				}
			)
			generation_figure = px.pie(
				generation_composition,
				names="Parte",
				values="Generacion_kWh",
				color="Parte",
				color_discrete_map={
					"CUPS seleccionado": metric_colors["Generada"],
					"Resto de la comunidad": "#b0bec5",
				},
			)
			generation_figure.update_traces(
				textposition="inside",
				textinfo="percent",
				showlegend=False,
				domain={"x": [0.125, 0.875], "y": [0.125, 0.875]},
				hovertemplate="%{percent}<br>%{value:.2f} kWh<extra></extra>",
			)
			generation_figure.update_layout(
				height=225,
				margin={"t": 10, "b": 10, "l": 5, "r": 5},
				showlegend=False,
			)
			composition_columns = st.columns(2, gap="small")
			composition_columns[0].plotly_chart(
				composition_figure, use_container_width=True
			)
			composition_columns[1].plotly_chart(
				generation_figure, use_container_width=True
			)

		user_profile_prefix = str(selected_cups)[-5:]
		user_profile_paths = {
			"weekday": responses_dir / f"{user_profile_prefix}_weekday_profile.csv",
			"weekend": responses_dir / f"{user_profile_prefix}_weekend_profile.csv",
		}
		self_consumption_profile_path = (
			responses_dir / f"{user_profile_prefix}_day_profile_extended.json"
		)
		profile_paths = {
			**{f"usuario_{key}": value for key, value in user_profile_paths.items()},
			**{f"comunidad_{key}": value for key, value in community_profile_paths.items()},
		}
		missing_user_profiles = [
			path.name for path in profile_paths.values() if not path.is_file()
		]
		user_months = user_data["mes"].astype(str).unique().tolist()

		user_season_columns = st.columns(2)
		user_season_figures = []
		if not self_consumption_profile_path.is_file():
			st.warning(
				f"No se encontró el perfil de energía autoconsumida: "
				f"{self_consumption_profile_path.name}. Se mostrarán los perfiles "
				"sin la media de autoconsumo."
			)
		if missing_user_profiles:
			st.warning(
				"No se encontraron los perfiles horarios necesarios: "
				+ ", ".join(missing_user_profiles)
			)
		else:
			for column, title, season_months, season_name in (
				(
					user_season_columns[0],
					"Perfil horario de consumo en invierno",
					{10, 11, 12, 1, 2, 3},
					"invierno",
				),
				(
					user_season_columns[1],
					"Perfil horario de consumo en verano",
					{4, 5, 6, 7, 8, 9},
					"verano",
				),
			):
				with column:
					st.subheader(title)
					pvgis_season = "winter" if season_name == "invierno" else "summer"
					pvgis_path = resolve_pvgis_profile_path(
						responses_dir, pvgis_season, user_months
					)
					if not pvgis_path.is_file():
						st.warning(
							f"No se encontró el perfil PVGIS: {pvgis_path.name}. "
							"Se mostrarán los perfiles de consumo."
						)
						pvgis_path = None
					try:
						figure = build_seasonal_profile_figure(
							user_profile_paths["weekday"],
							user_profile_paths["weekend"],
							community_profile_paths["weekday"],
							community_profile_paths["weekend"],
							user_months,
							str(selected_cups),
							season_months,
							title,
							pvgis_path,
							self_consumption_profile_path
							if self_consumption_profile_path.is_file()
							else None,
						)
					except (OSError, ValueError, TypeError) as error:
						st.error(
							f"No se pudo preparar el perfil horario de {season_name}: {error}"
						)
					else:
						user_season_figures.append((column, figure))
		if user_season_figures:
			user_season_y_max = max(
				float(max(trace.y))
				for _, figure in user_season_figures
				for trace in figure.data
				if trace.y is not None
			)
			user_season_y_max = user_season_y_max * 1.05 if user_season_y_max > 0 else 1.0
			for column, figure in user_season_figures:
				figure.update_yaxes(range=[0, user_season_y_max])
				with column:
					st.plotly_chart(figure, use_container_width=True)

		if not missing_user_profiles:
			user_day_type_columns = st.columns(2)
			user_day_type_figures = []
			try:
				for column, season_name, season_months in (
					(
						user_day_type_columns[0],
						"invierno",
						{10, 11, 12, 1, 2, 3},
					),
					(
						user_day_type_columns[1],
						"verano",
						{4, 5, 6, 7, 8, 9},
					),
				):
					title = (
						f"Perfil horario de consumo en {season_name}: "
						"día festivo y día laborable"
					)
					figure = build_day_type_profile_figure(
						user_profile_paths["weekday"],
						user_profile_paths["weekend"],
						community_profile_paths["weekday"],
						community_profile_paths["weekend"],
						user_months,
						str(selected_cups),
						title,
						season_months,
					)
					user_day_type_figures.append((column, title, figure))
			except (OSError, ValueError, TypeError) as error:
				user_day_type_figures = []
				st.error(
					f"No se pudieron preparar los perfiles horarios del usuario: {error}"
				)
			if user_day_type_figures:
				apply_shared_seasonal_y_scale(
					[figure for _, _, figure in user_day_type_figures]
				)
				for column, title, figure in user_day_type_figures:
					with column:
						st.subheader(title)
						st.plotly_chart(figure, use_container_width=True)
