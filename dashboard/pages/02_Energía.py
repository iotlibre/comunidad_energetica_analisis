import streamlit as st
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

dashboard_dir = Path(__file__).resolve().parents[1]
if str(dashboard_dir) not in sys.path:
	sys.path.insert(0, str(dashboard_dir))

from utils.autoconsumption_chart import (
	find_autoconsumption_files,
	load_autoconsumption_data,
)
from utils.hourly_profile_chart import (
	build_community_day_type_profile_figure,
	build_community_seasonal_profile_figure,
	build_day_type_profile_figure,
	build_seasonal_profile_figure,
)

st.set_page_config(page_title="Energía", layout="wide")
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


responses_dir = Path(__file__).resolve().parents[2] / "responses"


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
st.divider()
st.header("Comunidad")

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
		"Selecciona un fichero de energía autoconsumida",
		autoconsumption_files,
		format_func=lambda path: path.name,
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
	if missing_community_profiles:
		st.warning(
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
				pvgis_path = responses_dir / f"pvgis_spain_profile_{pvgis_season}_2025.json"
				if not pvgis_path.is_file():
					st.warning(
						f"No se encontró el perfil PVGIS: {pvgis_path.name}. "
						"Se mostrará el perfil comunitario."
					)
					pvgis_path = None
				try:
					figure = build_community_seasonal_profile_figure(
						community_profile_paths["weekday"],
						community_profile_paths["weekend"],
						community_months,
						season_months,
						title,
						pvgis_path,
					)
				except (OSError, ValueError, TypeError) as error:
					st.error(
						f"No se pudo preparar el perfil comunitario de {season_name}: {error}"
					)
				else:
					community_season_figures.append((column, figure))
	if community_season_figures:
		community_season_y_max = max(
			float(max(trace.y))
			for _, figure in community_season_figures
			for trace in figure.data
			if trace.y is not None
		)
		community_season_y_max = (
			community_season_y_max * 1.05 if community_season_y_max > 0 else 1.0
		)
		for column, figure in community_season_figures:
			figure.update_yaxes(range=[0, community_season_y_max])
			with column:
				st.plotly_chart(figure, use_container_width=True)

	if not missing_community_profiles:
		title = "Perfil horario de consumo: día festivo y día laborable"
		st.subheader(title)
		try:
			community_day_type_figure = build_community_day_type_profile_figure(
				community_profile_paths["weekend"],
				community_profile_paths["weekday"],
				community_months,
				title,
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(
				f"No se pudo preparar el perfil horario comunitario: {error}"
			)
		else:
			community_day_type_y_max = max(
				float(max(trace.y))
				for trace in community_day_type_figure.data
				if trace.y is not None
			)
			community_day_type_y_max = (
				community_day_type_y_max * 1.05
				if community_day_type_y_max > 0
				else 1.0
			)
			community_day_type_figure.update_yaxes(
				range=[0, community_day_type_y_max]
			)
			st.plotly_chart(
				community_day_type_figure, use_container_width=True
			)

st.divider()
st.header("Energía autoconsumida")

if autoconsumption_data is None:
	st.warning(
		"Selecciona un fichero de energía autoconsumida válido en el apartado Comunidad."
	)
else:
	cups_options = sorted(autoconsumption_data["cups"].unique())
	selected_cups = st.selectbox("Selecciona un CUPS", cups_options)
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
				pvgis_path = responses_dir / f"pvgis_spain_profile_{pvgis_season}_2025.json"
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
		title = "Perfil horario de consumo: día festivo y día laborable"
		st.subheader(title)
		try:
			user_day_type_figure = build_day_type_profile_figure(
				user_profile_paths["weekday"],
				user_profile_paths["weekend"],
				community_profile_paths["weekday"],
				community_profile_paths["weekend"],
				user_months,
				str(selected_cups),
				title,
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(f"No se pudo preparar el perfil horario del usuario: {error}")
		else:
			user_day_type_y_max = max(
				float(max(trace.y))
				for trace in user_day_type_figure.data
				if trace.y is not None
			)
			user_day_type_y_max = (
				user_day_type_y_max * 1.05
				if user_day_type_y_max > 0
				else 1.0
			)
			user_day_type_figure.update_yaxes(range=[0, user_day_type_y_max])
			st.plotly_chart(user_day_type_figure, use_container_width=True)
