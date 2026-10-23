from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import plotly.express as px

from perfil_diario_v9 import _spanish_national_holidays


HOUR_COLUMNS = [str(hour) for hour in range(24)]


def _load_monthly_profile(path: Path) -> pd.DataFrame:
	profile = pd.read_csv(path)
	columns = list(profile.columns)

	if len(columns) == 26 and columns[0] in {"", "Unnamed: 0"} and columns[1] == "month":
		profile = profile.iloc[:, 1:]
		columns = list(profile.columns)
	if "month" not in columns and len(columns) == 25:
		profile = profile.rename(columns={columns[0]: "month"})

	if "month" not in profile.columns or not set(HOUR_COLUMNS).issubset(profile.columns):
		raise ValueError(
			f"El perfil {path.name} debe incluir month y las horas 0-23."
		)

	profile = profile[["month", *HOUR_COLUMNS]].copy()
	profile["month"] = pd.to_numeric(profile["month"], errors="coerce")
	profile[HOUR_COLUMNS] = profile[HOUR_COLUMNS].apply(
		pd.to_numeric, errors="coerce"
	)
	if profile.isna().any().any():
		raise ValueError(f"El perfil {path.name} contiene valores no numéricos.")
	return profile


def _season_day_weights(
	represented_months: list[str], season_months: set[int]
) -> dict[str, dict[int, int]]:
	weights = {
		"weekday": {month: 0 for month in season_months},
		"weekend": {month: 0 for month in season_months},
	}
	for value in represented_months:
		period = pd.Period(str(value), freq="M")
		if period.month not in season_months:
			continue
		days = pd.date_range(period.start_time, period.end_time, freq="D")
		holidays = _spanish_national_holidays(period.year)
		for day in days:
			if day.weekday() >= 5 or day.date() in holidays:
				weights["weekend"][period.month] += 1
			else:
				weights["weekday"][period.month] += 1
	return weights


def _weighted_season_mean(
	profile: pd.DataFrame, day_weights: dict[int, int], path: Path
) -> pd.Series:
	month_weights = pd.Series(day_weights, dtype="float64")
	month_weights = month_weights[month_weights > 0]
	profile = profile.set_index("month")
	profile.index = profile.index.astype(int)
	profile = profile.reindex(month_weights.index)
	if profile.empty or profile[HOUR_COLUMNS].isna().any().any():
		raise ValueError(f"El perfil {path.name} no contiene los meses necesarios.")
	return profile[HOUR_COLUMNS].mul(month_weights, axis=0).sum() / month_weights.sum()


def _load_pvgis_profile(path: Path) -> pd.DataFrame:
	data = json.loads(path.read_text(encoding="utf-8"))
	if data.get("unidad") != "kWh/usuario/hora":
		raise ValueError(
			f"El perfil PVGIS debe estar en kWh/usuario/hora: {path.name}."
		)
	rows = data.get("valores")
	if not isinstance(rows, list):
		raise ValueError(f"El perfil PVGIS no contiene valores horarios: {path.name}.")

	profile = []
	for row in rows:
		try:
			hour = int(str(row["hora"]).split(":")[0])
			value = float(row["generacion_media"])
			sample_count = int(row["muestras"])
		except (KeyError, TypeError, ValueError) as error:
			raise ValueError(f"El perfil PVGIS tiene un valor horario inválido: {path.name}.") from error
		if hour not in range(24) or pd.isna(value) or sample_count <= 0:
			raise ValueError(f"El perfil PVGIS tiene una hora o un valor inválido: {path.name}.")
		profile.append({"hora": hour, "consumo_kWh": value})

	result = pd.DataFrame(profile).sort_values("hora").reset_index(drop=True)
	if result["hora"].tolist() != list(range(24)):
		raise ValueError(f"El perfil PVGIS debe contener una muestra por hora: {path.name}.")
	return result


def _weighted_profile_metric_totals(
	path: Path, day_weights: dict[int, int], day_type: str, metric: str
) -> tuple[pd.Series, pd.Series]:
	data = json.loads(path.read_text(encoding="utf-8"))
	rows = data.get(f"{day_type}_consumption")
	if rows is None:
		rows = data.get(f"{day_type}_profile")
	if not isinstance(rows, list):
		raise ValueError(
			f"El perfil {path.name} no contiene datos de {day_type}."
		)

	profile_rows = []
	for row in rows:
		try:
			month = int(row["month"])
			hour_values = {
				str(hour): row[str(hour)][metric]
				for hour in range(24)
			}
		except (KeyError, TypeError, ValueError) as error:
			raise ValueError(
				f"El perfil {path.name} tiene un valor de {metric} inválido."
			) from error
		for hour, value in hour_values.items():
			if value is not None:
				try:
					numeric_value = float(value)
				except (TypeError, ValueError) as error:
					raise ValueError(
						f"El perfil {path.name} tiene un valor de {metric} inválido."
					) from error
				if not math.isfinite(numeric_value):
					raise ValueError(
						f"El perfil {path.name} tiene un valor de {metric} inválido."
					)
				hour_values[hour] = numeric_value
		profile_rows.append({"month": month, **hour_values})

	profile = pd.DataFrame(profile_rows).set_index("month")
	if profile.index.has_duplicates:
		raise ValueError(f"El perfil {path.name} contiene meses duplicados.")
	if set(profile.index) != set(range(1, 13)):
		raise ValueError(
			f"El perfil {path.name} debe contener los meses del 1 al 12."
		)
	month_weights = pd.Series(day_weights, dtype="float64")
	month_weights = month_weights[month_weights > 0]
	profile = profile.reindex(month_weights.index)
	if profile.empty:
		raise ValueError(f"El perfil {path.name} no contiene los meses necesarios.")
	profile = profile[HOUR_COLUMNS].apply(pd.to_numeric, errors="coerce")
	weights = profile.notna().mul(month_weights, axis=0)
	weighted_values = profile.fillna(0).mul(month_weights, axis=0).sum()
	available_days = weights.sum()
	return weighted_values, available_days


def _community_seasonal_metric_mean(
	profile_directory: Path,
	weights: dict[str, dict[int, int]],
	metric: str,
) -> pd.Series:
	if not profile_directory.is_dir():
		raise ValueError(
			f"No existe el directorio de perfiles ampliados: {profile_directory}."
		)
	profile_paths = sorted(profile_directory.glob("*_day_profile_extended.json"))
	if not profile_paths:
		raise ValueError(
			f"No se encontraron archivos *_day_profile_extended.json en "
			f"{profile_directory}."
		)

	user_values = []
	for profile_path in profile_paths:
		weekday_values, weekday_days = _weighted_profile_metric_totals(
			profile_path, weights["weekday"], "weekday", metric
		)
		weekend_values, weekend_days = _weighted_profile_metric_totals(
			profile_path, weights["weekend"], "weekend", metric
		)
		weekday_values.index = range(24)
		weekday_days.index = range(24)
		weekend_values.index = range(24)
		weekend_days.index = range(24)
		available_days = weekday_days + weekend_days
		user_available = available_days > 0
		user_mean = (weekday_values + weekend_values).div(
			available_days.where(user_available)
		)
		user_values.append(user_mean)

	profiles = pd.concat(user_values, axis=1)
	return profiles.mean(axis=1)


def build_seasonal_profile_figure(
	user_weekday_path: Path,
	user_weekend_path: Path,
	community_weekday_path: Path,
	community_weekend_path: Path,
	represented_months: list[str],
	selected_cups: str,
	season_months: set[int],
	title: str,
	pvgis_profile_path: Path | None = None,
	profile_extended_path: Path | None = None,
):
	weights = _season_day_weights(represented_months, season_months)
	if not any(weights["weekday"].values()) or not any(weights["weekend"].values()):
		raise ValueError("No hay meses de la estación seleccionada en los datos.")
	profiles = []
	for label, weekday_path, weekend_path in (
		(
			f"Usuario {selected_cups}",
			user_weekday_path,
			user_weekend_path,
		),
		("Toda la comunidad", community_weekday_path, community_weekend_path),
	):
		weekday = _weighted_season_mean(
			_load_monthly_profile(weekday_path), weights["weekday"], weekday_path
		)
		weekend = _weighted_season_mean(
			_load_monthly_profile(weekend_path), weights["weekend"], weekend_path
		)
		weekday_days = sum(weights["weekday"].values())
		weekend_days = sum(weights["weekend"].values())
		combined = (weekday * weekday_days + weekend * weekend_days) / (
			weekday_days + weekend_days
		)
		profiles.append(
			pd.DataFrame(
				{
					"hora": range(24),
					"consumo_kWh": combined.to_numpy(),
					"perfil": label,
				}
			)
		)

	if pvgis_profile_path is not None:
		pvgis_profile = _load_pvgis_profile(pvgis_profile_path)
		pvgis_profile["perfil"] = "Generación PVGIS por usuario"
		profiles.append(pvgis_profile)
	if profile_extended_path is not None:
		weekday_values, weekday_days = _weighted_profile_metric_totals(
			profile_extended_path,
			weights["weekday"],
			"weekday",
			"self_consumption_kWh",
		)
		weekend_values, weekend_days = _weighted_profile_metric_totals(
			profile_extended_path,
			weights["weekend"],
			"weekend",
			"self_consumption_kWh",
		)
		available_days = weekday_days + weekend_days
		if (available_days == 0).any():
			raise ValueError(
				f"El perfil {profile_extended_path.name} no contiene datos "
				"de autoconsumo para todas las horas de la estación."
			)
		self_consumption_profile = pd.DataFrame(
			{
				"hora": range(24),
				"consumo_kWh": (
					(weekday_values + weekend_values) / available_days
				).to_numpy(),
				"perfil": "Autoconsumida media por usuario",
			}
		)
		profiles.append(self_consumption_profile)

		generation_weekday_values, generation_weekday_days = (
			_weighted_profile_metric_totals(
				profile_extended_path,
				weights["weekday"],
				"weekday",
				"total_generation",
			)
		)
		generation_weekend_values, generation_weekend_days = (
			_weighted_profile_metric_totals(
				profile_extended_path,
				weights["weekend"],
				"weekend",
				"total_generation",
			)
		)
		generation_available_days = (
			generation_weekday_days + generation_weekend_days
		)
		if (generation_available_days == 0).any():
			raise ValueError(
				f"El perfil {profile_extended_path.name} no contiene datos de "
				"generación para todas las horas de la estación."
			)
		generation_profile = pd.DataFrame(
			{
				"hora": range(24),
				"consumo_kWh": (
					(generation_weekday_values + generation_weekend_values)
					/ generation_available_days
				).to_numpy(),
				"perfil": "Energía generada media por usuario",
			}
		)
		profiles.append(generation_profile)

	chart_data = pd.concat(profiles, ignore_index=True)
	figure = px.scatter(
		chart_data,
		x="hora",
		y="consumo_kWh",
		color="perfil",
		title=title,
		labels={
			"hora": "Hora del día",
			"consumo_kWh": "Energía media (kWh/usuario/hora)"
			if pvgis_profile_path is not None
			or profile_extended_path is not None
			else "Consumo medio (kWh)",
			"perfil": "Perfil",
		},
	)
	figure.update_traces(mode="lines+markers", marker={"size": 8})
	if pvgis_profile_path is not None:
		figure.update_traces(
			line={"color": "#2e7d32"},
			marker={"color": "#2e7d32", "size": 8},
			fill="tozeroy",
			fillcolor="rgba(46, 125, 50, 0.12)",
			selector={"name": "Generación PVGIS por usuario"},
		)
	if profile_extended_path is not None:
		figure.update_traces(
			line={"color": "#1b5e20", "dash": "dash"},
			marker={"color": "#1b5e20", "size": 8, "symbol": "diamond"},
			fill="tozeroy",
			fillcolor="rgba(27, 94, 32, 0.16)",
			selector={"name": "Autoconsumida media por usuario"},
		)
		figure.update_traces(
			line={"color": "#ba68c8", "dash": "dot"},
			marker={"color": "#ba68c8", "size": 8, "symbol": "triangle-up"},
			fill="tozeroy",
			fillcolor="rgba(186, 104, 200, 0.16)",
			selector={"name": "Energía generada media por usuario"},
		)
	figure.update_xaxes(dtick=1)
	figure.update_layout(
		height=520,
		margin={"b": 100},
		legend={
			"orientation": "h",
			"x": 0.5,
			"xanchor": "center",
			"y": -0.25,
			"yanchor": "top",
		},
	)
	return figure


def build_day_type_profile_figure(
	user_profile_path: Path,
	user_weekend_profile_path: Path,
	community_profile_path: Path,
	community_weekend_profile_path: Path,
	represented_months: list[str],
	selected_cups: str,
	title: str,
):
	profiles = []
	for label, path, day_type in (
		(
			f"Usuario {selected_cups} — día festivo",
			user_weekend_profile_path,
			"weekend",
		),
		(
			f"Usuario {selected_cups} — día laborable",
			user_profile_path,
			"weekday",
		),
		("Toda la comunidad — día festivo", community_weekend_profile_path, "weekend"),
		("Toda la comunidad — día laborable", community_profile_path, "weekday"),
	):
		weights = _season_day_weights(represented_months, set(range(1, 13)))[
			day_type
		]
		if not any(weights.values()):
			raise ValueError(
				f"No hay días representados para el tipo de día {day_type}."
			)
		mean_profile = _weighted_season_mean(
			_load_monthly_profile(path), weights, path
		)
		profiles.append(
			pd.DataFrame(
				{
					"hora": range(24),
					"consumo_kWh": mean_profile.to_numpy(),
					"perfil": label,
				}
			)
		)

	colors = {
		f"Usuario {selected_cups} — día festivo": "#ef5350",
		f"Usuario {selected_cups} — día laborable": "#b71c1c",
		"Toda la comunidad — día festivo": "#ef9a9a",
		"Toda la comunidad — día laborable": "#1a0000",
	}
	figure = px.scatter(
		pd.concat(profiles, ignore_index=True),
		x="hora",
		y="consumo_kWh",
		color="perfil",
		category_orders={"perfil": list(colors)},
		title=title,
		labels={
			"hora": "Hora del día",
			"consumo_kWh": "Consumo medio (kWh)",
			"perfil": "Perfil",
		},
	)
	figure.update_traces(mode="lines+markers", marker={"size": 8})
	for trace in figure.data:
		color = colors[trace.name]
		symbol = "circle" if trace.name.startswith("Usuario ") else "square"
		dash = "solid" if "festivo" in trace.name else "dash"
		trace.update(
			line={"color": color, "dash": dash},
			marker={"color": color, "size": 8, "symbol": symbol},
		)
	figure.update_xaxes(dtick=1)
	figure.update_layout(
		height=520,
		margin={"b": 100},
		legend={
			"orientation": "h",
			"x": 0.5,
			"xanchor": "center",
			"y": -0.25,
			"yanchor": "top",
		},
	)
	return figure


def build_community_seasonal_profile_figure(
	community_weekday_path: Path,
	community_weekend_path: Path,
	represented_months: list[str],
	season_months: set[int],
	title: str,
	pvgis_profile_path: Path | None = None,
	profile_extended_directory: Path = Path("responses"),
):
	weights = _season_day_weights(represented_months, season_months)
	weekday_days = sum(weights["weekday"].values())
	weekend_days = sum(weights["weekend"].values())
	if not weekday_days or not weekend_days:
		raise ValueError("No hay días laborables y fines de semana en los meses seleccionados.")

	weekday = _weighted_season_mean(
		_load_monthly_profile(community_weekday_path),
		weights["weekday"],
		community_weekday_path,
	)
	weekend = _weighted_season_mean(
		_load_monthly_profile(community_weekend_path),
		weights["weekend"],
		community_weekend_path,
	)
	community_mean = (weekday * weekday_days + weekend * weekend_days) / (
		weekday_days + weekend_days
	)
	community_profile = pd.DataFrame(
		{
			"hora": range(24),
			"consumo_kWh": community_mean.to_numpy(),
			"perfil": "Consumo medio de los usuarios",
		}
	)
	profiles = [community_profile]
	if pvgis_profile_path is not None:
		pvgis_profile = _load_pvgis_profile(pvgis_profile_path)
		pvgis_profile["perfil"] = "Generación PVGIS proporcional"
		profiles.append(pvgis_profile)

	extended_weights = _season_day_weights(represented_months, season_months)
	for metric, label in (
		("self_consumption_kWh", "Autoconsumida media de los usuarios"),
		("total_generation", "Energía generada media de los usuarios"),
	):
		community_values = _community_seasonal_metric_mean(
			profile_extended_directory,
			extended_weights,
			metric,
		)
		profiles.append(
			pd.DataFrame(
				{
					"hora": range(24),
					"consumo_kWh": community_values.to_numpy(),
					"perfil": label,
				}
			)
		)

	figure = px.scatter(
		pd.concat(profiles, ignore_index=True),
		x="hora",
		y="consumo_kWh",
		color="perfil",
		title=title,
		labels={
			"hora": "Hora del día",
			"consumo_kWh": "Energía media por usuario (kWh/usuario/hora)",
			"perfil": "Perfil",
		},
	)
	figure.update_traces(mode="lines+markers", marker={"size": 8})
	figure.update_traces(
		line={"color": "#ef9a9a"},
		marker={"color": "#ef9a9a", "size": 8, "symbol": "square"},
		selector={"name": "Consumo medio de los usuarios"},
	)
	if pvgis_profile_path is not None:
		figure.update_traces(
			line={"color": "#2e7d32"},
			marker={"color": "#2e7d32", "size": 8},
			fill="tozeroy",
			fillcolor="rgba(46, 125, 50, 0.12)",
			selector={"name": "Generación PVGIS proporcional"},
		)
	figure.update_traces(
		line={"color": "#1b5e20", "dash": "dash"},
		marker={"color": "#1b5e20", "size": 8, "symbol": "diamond"},
		fill="tozeroy",
		fillcolor="rgba(27, 94, 32, 0.16)",
		selector={"name": "Autoconsumida media de los usuarios"},
	)
	figure.update_traces(
		line={"color": "#ba68c8", "dash": "dot"},
		marker={"color": "#ba68c8", "size": 8, "symbol": "triangle-up"},
		fill="tozeroy",
		fillcolor="rgba(186, 104, 200, 0.16)",
		selector={"name": "Energía generada media de los usuarios"},
	)
	figure.update_xaxes(dtick=1)
	figure.update_layout(
		height=520,
		margin={"b": 100},
		legend={
			"orientation": "h",
			"x": 0.5,
			"xanchor": "center",
			"y": -0.25,
			"yanchor": "top",
		},
	)
	return figure


def build_community_day_type_profile_figure(
	community_weekend_profile_path: Path,
	community_weekday_profile_path: Path,
	represented_months: list[str],
	title: str,
):
	profiles = []
	for label, path, day_type in (
		("Día festivo", community_weekend_profile_path, "weekend"),
		("Día laborable", community_weekday_profile_path, "weekday"),
	):
		weights = _season_day_weights(represented_months, set(range(1, 13)))[
			day_type
		]
		if not any(weights.values()):
			raise ValueError(
				f"No hay días representados para el tipo de día {day_type}."
			)
		community_mean = _weighted_season_mean(
			_load_monthly_profile(path),
			weights,
			path,
		)
		profiles.append(
			pd.DataFrame(
				{
					"hora": range(24),
					"consumo_kWh": community_mean.to_numpy(),
					"perfil": label,
				}
			)
		)

	colors = {"Día festivo": "#ef9a9a", "Día laborable": "#1a0000"}
	figure = px.scatter(
		pd.concat(profiles, ignore_index=True),
		x="hora",
		y="consumo_kWh",
		color="perfil",
		category_orders={"perfil": list(colors)},
		title=title,
		labels={
			"hora": "Hora del día",
			"consumo_kWh": "Consumo medio (kWh)",
			"perfil": "Perfil",
		},
	)
	figure.update_traces(mode="lines+markers", marker={"size": 8})
	for trace in figure.data:
		color = colors[trace.name]
		dash = "solid" if trace.name == "Día festivo" else "dash"
		trace.update(
			line={"color": color, "dash": dash},
			marker={"color": color, "size": 8, "symbol": "square"},
		)
	figure.update_xaxes(dtick=1)
	figure.update_layout(
		height=520,
		margin={"b": 100},
		legend={
			"orientation": "h",
			"x": 0.5,
			"xanchor": "center",
			"y": -0.25,
			"yanchor": "top",
		},
	)
	return figure