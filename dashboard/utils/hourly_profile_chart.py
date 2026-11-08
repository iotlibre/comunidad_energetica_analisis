from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from perfil_diario_v9 import _spanish_national_holidays


HOUR_COLUMNS = [str(hour) for hour in range(24)]


def resolve_pvgis_profile_path(
	responses_dir: Path, season: str, represented_months: list[str]
) -> Path:
	if season not in {"winter", "summer"}:
		raise ValueError(f"Estación PVGIS no válida: {season}.")
	if not represented_months:
		raise ValueError("No hay meses representados para determinar el año PVGIS.")

	try:
		year = max(
			pd.Period(str(month), freq="M").year for month in represented_months
		)
	except (TypeError, ValueError) as error:
		raise ValueError("Hay un mes representado no válido para PVGIS.") from error

	return responses_dir / f"pvgis_spain_profile_{season}_{year}.json"


def _load_monthly_profile(path: Path) -> pd.DataFrame:
	profile = pd.read_csv(path, keep_default_na=False)
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
	month_values = pd.to_numeric(profile["month"], errors="coerce")
	hour_values = profile[HOUR_COLUMNS].apply(pd.to_numeric, errors="coerce")
	invalid_hour_values = (
		profile[HOUR_COLUMNS].apply(
			lambda column: column.astype(str).str.strip().ne("")
		)
		& hour_values.isna()
	)
	if month_values.isna().any() or invalid_hour_values.any().any():
		raise ValueError(f"El perfil {path.name} contiene valores no numéricos.")
	profile["month"] = month_values
	profile[HOUR_COLUMNS] = hour_values
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
		weights["weekday"][period.month] += int((days.weekday < 5).sum())
		weights["weekend"][period.month] += int((days.weekday >= 5).sum())
	return weights


def _community_season_day_weights(
	represented_months: list[str], season_months: set[int]
) -> dict[str, dict[int, int]]:
	weights = {
		"weekday": {month: 0 for month in season_months},
		"weekend": {month: 0 for month in season_months},
	}
	for value in represented_months:
		try:
			period = pd.Period(str(value), freq="M")
		except (TypeError, ValueError) as error:
			raise ValueError(f"El mes representado no es válido: {value}.") from error
		if period.month not in season_months:
			continue
		holidays = _spanish_national_holidays(period.year)
		for day in pd.date_range(period.start_time, period.end_time, freq="D"):
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


def _load_extended_monthly_profiles(
	path: Path, required_months: set[int]
) -> dict[str, dict[int, dict[str, list[float | None]]]]:
	try:
		data = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as error:
		raise ValueError(
			f"No se pudo leer el perfil ampliado {path.name}: {error}"
		) from error
	if not isinstance(data, dict):
		raise ValueError(f"El perfil ampliado {path.name} no contiene un objeto JSON.")

	profiles = {}
	for day_type in ("weekday", "weekend"):
		rows = data.get(f"{day_type}_consumption")
		if not isinstance(rows, list):
			raise ValueError(
				f"El perfil ampliado {path.name} no contiene datos de {day_type}."
			)
		monthly_profiles = {}
		for row in rows:
			if not isinstance(row, dict):
				raise ValueError(
					f"El perfil ampliado {path.name} tiene una fila inválida."
				)
			try:
				raw_month = row["month"]
			except (KeyError, TypeError, ValueError) as error:
				raise ValueError(
					f"El perfil ampliado {path.name} tiene un mes inválido."
				) from error
			if (
				isinstance(raw_month, bool)
				or not isinstance(raw_month, (int, float))
				or not math.isfinite(raw_month)
				or not float(raw_month).is_integer()
			):
				raise ValueError(
					f"El perfil ampliado {path.name} tiene un mes inválido."
				)
			month = int(raw_month)
			if month not in range(1, 13) or month in monthly_profiles:
				raise ValueError(
					f"El perfil ampliado {path.name} tiene meses inválidos o duplicados."
				)

			metrics = {}
			for metric in ("self_consumption_kWh", "total_generation"):
				hour_values = []
				for hour in range(24):
					try:
						value = row[str(hour)][metric]
					except (KeyError, TypeError) as error:
						raise ValueError(
							f"El perfil ampliado {path.name} no contiene la hora "
							f"{hour} para {metric}."
						) from error
					if value is None:
						hour_values.append(None)
						continue
					if isinstance(value, bool) or not isinstance(value, (int, float)):
						raise ValueError(
							f"El perfil ampliado {path.name} contiene un valor inválido "
							f"de {metric} en la hora {hour}."
						)
					numeric_value = float(value)
					if not math.isfinite(numeric_value) or numeric_value < 0:
						raise ValueError(
							f"El perfil ampliado {path.name} contiene un valor no válido "
							f"de {metric} en la hora {hour}."
						)
					hour_values.append(numeric_value)
				metrics[metric] = hour_values
			monthly_profiles[month] = metrics

		missing_months = required_months.difference(monthly_profiles)
		if missing_months:
			raise ValueError(
				f"El perfil ampliado {path.name} no contiene los meses necesarios: "
				+ ", ".join(str(month) for month in sorted(missing_months))
				+ "."
			)
		profiles[day_type] = monthly_profiles
	return profiles


def _mean_extended_metric_per_hour(
	extended_profiles: list[dict[str, dict[int, dict[str, list[float | None]]]]],
	day_weights: dict[str, dict[int, int]],
	metric: str,
) -> list[float | None]:
	means = []
	for hour in range(24):
		cups_means = []
		for profile in extended_profiles:
			weighted_total = 0.0
			available_days = 0
			for day_type in ("weekday", "weekend"):
				for month, days in day_weights[day_type].items():
					value = profile[day_type][month][metric][hour]
					if days and value is not None:
						weighted_total += value * days
						available_days += days
			if available_days:
				cups_means.append(weighted_total / available_days)
		means.append(sum(cups_means) / len(cups_means) if cups_means else None)
	return means


def _load_community_pvgis_profile(path: Path) -> pd.DataFrame:
	data = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(data, dict):
		raise ValueError(f"El perfil PVGIS no contiene un objeto JSON: {path.name}.")
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
			hour_text = str(row["hora"])
			if len(hour_text) != 5 or hour_text[2:] != ":00":
				raise ValueError
			hour = int(hour_text[:2])
			value = row["generacion_media"]
			sample_count = row["muestras"]
		except (KeyError, TypeError, ValueError) as error:
			raise ValueError(f"El perfil PVGIS tiene un valor horario inválido: {path.name}.") from error
		if (
			isinstance(value, bool)
			or not isinstance(value, (int, float))
			or isinstance(sample_count, bool)
			or not isinstance(sample_count, int)
		):
			raise ValueError(f"El perfil PVGIS tiene un valor horario inválido: {path.name}.")
		value = float(value)
		if (
			hour not in range(24)
			or not math.isfinite(value)
			or value < 0
			or sample_count <= 0
		):
			raise ValueError(f"El perfil PVGIS tiene una hora o un valor inválido: {path.name}.")
		profile.append({"hora": hour, "consumo_kWh": value})

	result = pd.DataFrame(profile).sort_values("hora").reset_index(drop=True)
	if result["hora"].tolist() != list(range(24)):
		raise ValueError(f"El perfil PVGIS debe contener una muestra por hora: {path.name}.")
	return result


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
					hour_values[hour] = float(value)
				except (TypeError, ValueError) as error:
					raise ValueError(
						f"El perfil {path.name} tiene un valor de {metric} inválido."
					) from error
		profile_rows.append({"month": month, **hour_values})

	profile = pd.DataFrame(profile_rows).set_index("month")
	if profile.index.has_duplicates:
		raise ValueError(f"El perfil {path.name} contiene meses duplicados.")
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
	figure.update_traces(
		visible="legendonly",
		selector={"name": "Toda la comunidad"},
	)
	if pvgis_profile_path is not None:
		figure.update_traces(
			line={"color": "#2e7d32"},
			marker={"color": "#2e7d32", "size": 8},
			fill="tozeroy",
			fillcolor="rgba(46, 125, 50, 0.12)",
			visible="legendonly",
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
	season_months: set[int] | None = None,
):
	if season_months is None:
		season_months = set(range(1, 13))
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
		weights = _season_day_weights(represented_months, season_months)[
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
		if trace.name.startswith("Toda la comunidad"):
			trace.visible = "legendonly"
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
	responses_dir: Path,
	pvgis_profile_path: Path | None = None,
):
	if not responses_dir.is_dir():
		raise ValueError(f"No existe el directorio de perfiles: {responses_dir}.")
	extended_paths = sorted(responses_dir.glob("*_day_profile_extended.json"))
	if not extended_paths:
		raise ValueError(
			f"No hay archivos *_day_profile_extended.json en {responses_dir}."
		)

	weights = _community_season_day_weights(represented_months, season_months)
	required_months = {
		month
		for day_type in ("weekday", "weekend")
		for month, days in weights[day_type].items()
		if days > 0
	}
	if not required_months:
		raise ValueError("No hay meses representados para la estación seleccionada.")
	if not any(weights["weekday"].values()) or not any(weights["weekend"].values()):
		raise ValueError(
			"No hay días laborables y fines de semana en los meses seleccionados."
		)

	community_profiles = []
	for path in (community_weekday_path, community_weekend_path):
		profile = _load_monthly_profile(path)
		month_values = profile["month"].to_numpy(dtype="float64")
		if not all(
			math.isfinite(month)
			and month.is_integer()
			and int(month) in range(1, 13)
			for month in month_values
		):
			raise ValueError(f"El perfil {path.name} contiene meses no válidos.")
		if profile["month"].duplicated().any():
			raise ValueError(f"El perfil {path.name} contiene meses duplicados.")
		months_present = set(profile["month"].astype(int))
		missing_months = required_months.difference(months_present)
		if missing_months:
			raise ValueError(
				f"El perfil {path.name} no contiene los meses necesarios: "
				+ ", ".join(str(month) for month in sorted(missing_months))
				+ "."
			)
		values = profile[HOUR_COLUMNS].to_numpy(dtype="float64")
		if any(
			not math.isnan(value) and (not math.isfinite(value) or value < 0)
			for value in values.flat
		):
			raise ValueError(f"El perfil {path.name} contiene valores no válidos.")
		required_values = profile.loc[
			profile["month"].isin(required_months), HOUR_COLUMNS
		].to_numpy(dtype="float64")
		if not all(
			math.isfinite(value) and value >= 0
			for value in required_values.flat
		):
			raise ValueError(
				f"El perfil {path.name} no contiene valores horarios válidos "
				"para los meses necesarios."
			)
		community_profiles.append(profile)

	weekday_profile = _weighted_season_mean(
		community_profiles[0], weights["weekday"], community_weekday_path
	)
	weekend_profile = _weighted_season_mean(
		community_profiles[1], weights["weekend"], community_weekend_path
	)
	weekday_days = sum(weights["weekday"].values())
	weekend_days = sum(weights["weekend"].values())
	community_mean = (
		weekday_profile * weekday_days + weekend_profile * weekend_days
	) / (weekday_days + weekend_days)

	extended_profiles = [
		_load_extended_monthly_profiles(path, required_months)
		for path in extended_paths
	]
	series = [
		(
			"Consumo medio de los usuarios",
			community_mean.to_numpy(),
			"#ef9a9a",
			"solid",
			"square",
			None,
		),
	]
	if pvgis_profile_path is not None:
		pvgis_profile = _load_community_pvgis_profile(pvgis_profile_path)
		series.append(
			(
				"Generación PVGIS proporcional",
				pvgis_profile["consumo_kWh"].to_numpy(),
				"#2e7d32",
				"solid",
				"circle",
				"rgba(46, 125, 50, 0.12)",
			)
		)
	series.extend(
		[
			(
				"Autoconsumida media de los usuarios",
				_mean_extended_metric_per_hour(
					extended_profiles, weights, "self_consumption_kWh"
				),
				"#1b5e20",
				"dash",
				"diamond",
				"rgba(27, 94, 32, 0.16)",
			),
			(
				"Energía generada media de los usuarios",
				_mean_extended_metric_per_hour(
					extended_profiles, weights, "total_generation"
				),
				"#ba68c8",
				"dot",
				"triangle-up",
				"rgba(186, 104, 200, 0.16)",
			),
		]
	)

	figure = go.Figure()
	for name, values, color, dash, symbol, fillcolor in series:
		figure.add_trace(
			go.Scatter(
				name=name,
				x=list(range(24)),
				y=values,
				mode="lines+markers",
				line={"color": color, "dash": dash},
				marker={"color": color, "size": 8, "symbol": symbol},
				fill="tozeroy" if fillcolor else None,
				fillcolor=fillcolor,
			)
		)
	if pvgis_profile_path is not None:
		figure.update_traces(
			visible="legendonly",
			selector={"name": "Generación PVGIS proporcional"},
		)
	figure.update_layout(
		title=title,
		xaxis_title="Hora del día",
		yaxis_title="Energía media (kWh/usuario/hora)",
		height=520,
		margin={"b": 110},
		legend={
			"orientation": "h",
			"x": 0.5,
			"xanchor": "center",
			"y": -0.3,
			"yanchor": "top",
		},
	)
	figure.update_xaxes(dtick=1, range=[-0.5, 23.5])
	figure.update_yaxes(rangemode="tozero")
	return figure


def apply_shared_seasonal_y_scale(figures: list[go.Figure]) -> float:
	maximum = max(
		(
			float(value)
			for figure in figures
			for trace in figure.data
			if trace.y is not None
			for value in trace.y
			if value is not None and pd.notna(value)
		),
		default=0.0,
	)
	if not math.isfinite(maximum):
		raise ValueError("Las gráficas estacionales contienen valores no finitos.")
	y_max = maximum * 1.05 if maximum > 0 else 1.0
	for figure in figures:
		figure.update_yaxes(range=[0, y_max])
	return y_max


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


def build_community_seasonal_day_type_profile_figure(
	community_weekend_profile_path: Path,
	community_weekday_profile_path: Path,
	represented_months: list[str],
	season_months: set[int],
	title: str,
):
	weights = _community_season_day_weights(represented_months, season_months)
	profiles = []
	for label, path, day_type in (
		("Día festivo", community_weekend_profile_path, "weekend"),
		("Día laborable", community_weekday_profile_path, "weekday"),
	):
		if not any(weights[day_type].values()):
			raise ValueError(
				f"No hay días representados para el tipo de día {day_type} "
				"en la estación seleccionada."
			)
		monthly_profile = _load_monthly_profile(path)
		if monthly_profile["month"].duplicated().any():
			raise ValueError(f"El perfil {path.name} contiene meses duplicados.")
		values = monthly_profile[HOUR_COLUMNS].to_numpy(dtype="float64")
		if any(
			not math.isnan(value) and (not math.isfinite(value) or value < 0)
			for value in values.flat
		):
			raise ValueError(f"El perfil {path.name} contiene valores no válidos.")
		required_months = [
			month for month, days in weights[day_type].items() if days > 0
		]
		required_values = monthly_profile.loc[
			monthly_profile["month"].isin(required_months), HOUR_COLUMNS
		].to_numpy(dtype="float64")
		if not all(
			math.isfinite(value) and value >= 0
			for value in required_values.flat
		):
			raise ValueError(
				f"El perfil {path.name} no contiene valores horarios válidos "
				"para los meses necesarios."
			)
		community_mean = _weighted_season_mean(
			monthly_profile,
			weights[day_type],
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
	figure.update_xaxes(dtick=1, range=[-0.5, 23.5])
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