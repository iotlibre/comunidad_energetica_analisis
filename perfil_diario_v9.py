import argparse
import csv
import json
import math
import numpy as np
import pandas as pd
from pathlib import Path
import os
import tempfile
from datetime import datetime, timedelta


def load_json_to_df(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    return df


def prepare_dataframe(df):
    # Ensure necessary columns exist
    for col in ("date", "time", "consumptionKWh"):
        if col not in df.columns:
            raise KeyError(f"Missing required column: {col}")

    # Numeric consumption
    df["consumptionKWh"] = pd.to_numeric(df["consumptionKWh"], errors="coerce")

    # Ensure selfConsumptionEnergyKWh is numeric and handle missing values
    if "selfConsumptionEnergyKWh" in df.columns:
        df["selfConsumptionEnergyKWh"] = pd.to_numeric(df["selfConsumptionEnergyKWh"], errors="coerce").fillna(0)
        df["total_consumption"] = df["consumptionKWh"] + df["selfConsumptionEnergyKWh"]
    else:
        df["total_consumption"] = df["consumptionKWh"]

    # Normalize time strings
    df["time"] = df["time"].astype(str).str.strip()

    # Detect times that represent 24:00 (could be '24:00' or start with '24')
    mask_24 = df["time"].str.startswith("24")

    # Parse date with a sensible fallback
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y/%m/%d", errors="coerce")
    if df["date"].isna().any():
        df["date"] = pd.to_datetime(df["date"].astype(str), errors="coerce")

    # Add one day where time was 24:00 and set time to 00:00
    if mask_24.any():
        df.loc[mask_24, "date"] = df.loc[mask_24, "date"] + pd.Timedelta(days=1)
        df.loc[mask_24, "time"] = df.loc[mask_24, "time"].astype(str).replace(to_replace=r"^24:.*$", value="00:00", regex=True)

    # Combine date and time into datetime
    df["datetime"] = pd.to_datetime(
        df["date"].dt.strftime("%Y-%m-%d") + " " + df["time"].str.slice(0,5),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )

    # Extract hour and month
    df["hour"] = df["datetime"].dt.hour
    df["month"] = df["datetime"].dt.month

    # Day type: weekday / weekend
    df["is_weekend"] = df["datetime"].dt.weekday >= 5
    df["day_type"] = np.where(df["is_weekend"], "weekend", "weekday")

    return df


def compute_monthly_hourly_mean(df):
    # Pivot table: rows=month (1-12), cols=hour (0-23)
    pivot = df.pivot_table(
        values="total_consumption",  # Use total_consumption instead of consumptionKWh
        index="month",
        columns="hour",
        aggfunc="mean",
    )

    # Ensure full month and hour ranges are present
    pivot = pivot.reindex(range(1, 13), fill_value=pd.NA)
    pivot = pivot.reindex(columns=range(0, 24), fill_value=pd.NA)

    return pivot


def compute_monthly_hourly_means(df):
    # Ensure day_type exists
    if "day_type" not in df.columns:
        df["is_weekend"] = df["datetime"].dt.weekday >= 5
        df["day_type"] = np.where(df["is_weekend"], "weekend", "weekday")

    weekday_df = df[df["day_type"] == "weekday"]
    weekend_df = df[df["day_type"] == "weekend"]

    weekday_pivot = compute_monthly_hourly_mean(weekday_df)
    weekend_pivot = compute_monthly_hourly_mean(weekend_df)

    return weekday_pivot, weekend_pivot


def generate_daily_profile(input_file):
    """
    Generate daily profile from the input JSON file and save results to predefined filenames.

    Args:
        input_file (str): Path to the input JSON file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        Exception: For any other errors during processing.
    """

    responses_dir = 'responses'
    ruta_fichero = Path(responses_dir) / input_file

    if not ruta_fichero.exists():
        raise FileNotFoundError(f"Input file not found: {ruta_fichero}")

    # Extract CUPS and last 5 characters from filename
    # Example: ES0021000006765028DN_20260220_075426.json -> CUPS is ES0021000006765028DN -> last 5 chars: 028DN
    filename_without_ext = ruta_fichero.stem  # Remove .json extension
    cups = filename_without_ext.split('_')[0]  # Get CUPS (first part before underscore)
    cups_last_5 = cups[-5:]  # Get last 5 characters of CUPS

    df = load_json_to_df(ruta_fichero)
    df = prepare_dataframe(df)

    weekday_pivot, weekend_pivot = compute_monthly_hourly_means(df)

    # Save results with CUPS identifier in filenames
    weekday_path = ruta_fichero.parent / f"{cups_last_5}_weekday_profile.csv"
    weekend_path = ruta_fichero.parent / f"{cups_last_5}_weekend_profile.csv"
    weekday_pivot.to_csv(weekday_path, index=True)
    weekend_pivot.to_csv(weekend_path, index=True)

    print(f"Weekday profile saved to: {weekday_path}")
    print(f"Weekend profile saved to: {weekend_path}")
    
    # Return the filenames
    return {
        "weekday_file": weekday_path.name,
        "weekend_file": weekend_path.name
    }


def generate_daily_profile_extended(file_path):
    """Generate monthly hourly mean profiles for weekdays and holidays."""
    responses_dir = Path("responses").resolve()
    requested_path = Path(file_path)
    if requested_path.is_absolute():
        raise ValueError("file_path debe ser una ruta relativa dentro de responses/.")
    if requested_path.parts and requested_path.parts[0] == "responses":
        requested_path = Path(*requested_path.parts[1:])

    input_path = (responses_dir / requested_path).resolve()
    if os.path.commonpath((str(responses_dir), str(input_path))) != str(responses_dir):
        raise ValueError("file_path debe apuntar a un fichero dentro de responses/.")
    if input_path.suffix.lower() != ".json":
        raise ValueError("file_path debe identificar un fichero JSON.")
    if not input_path.is_file():
        raise FileNotFoundError(f"No se encontró el fichero de entrada: {input_path}")

    filename_parts = input_path.stem.split("_", 1)
    if len(filename_parts) != 2 or len(filename_parts[0]) < 5:
        raise ValueError(
            "El nombre del fichero debe comenzar con el CUPS seguido de '_'."
        )
    cups_suffix = filename_parts[0][-5:]

    with input_path.open("r", encoding="utf-8") as source:
        source_records = json.load(source)
    if not isinstance(source_records, list):
        raise ValueError("El JSON de entrada debe contener una lista de registros.")

    categorized_records = {"weekday": [], "weekend": []}
    holidays_by_year = {}
    for index, record in enumerate(source_records):
        if not isinstance(record, dict):
            raise ValueError(f"El registro {index} debe ser un objeto JSON.")
        if not all(key in record for key in ("date", "time", "consumptionKWh")):
            raise ValueError(
                f"El registro {index} debe incluir date, time y consumptionKWh."
            )

        date_value = str(record["date"]).strip()
        parsed_date = None
        for date_format in ("%Y/%m/%d", "%Y-%m-%d"):
            try:
                parsed_date = datetime.strptime(date_value, date_format).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            raise ValueError(f"Fecha inválida en el registro {index}: {date_value}.")

        time_value = str(record["time"]).strip()
        if time_value in {"24:00", "24:00:00"}:
            parsed_datetime = datetime.combine(
                parsed_date + timedelta(days=1), datetime.min.time()
            )
        else:
            parsed_time = None
            for time_format in ("%H:%M", "%H:%M:%S"):
                try:
                    parsed_time = datetime.strptime(time_value, time_format).time()
                    break
                except ValueError:
                    continue
            if parsed_time is None:
                raise ValueError(f"Hora inválida en el registro {index}: {time_value}.")
            parsed_datetime = datetime.combine(parsed_date, parsed_time)

        try:
            consumption = float(record["consumptionKWh"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"consumptionKWh inválido en el registro {index}."
            ) from error
        if not math.isfinite(consumption):
            raise ValueError(f"consumptionKWh inválido en el registro {index}.")

        self_consumption_value = record.get("selfConsumptionEnergyKWh", 0)
        if self_consumption_value is None:
            self_consumption_value = 0
        try:
            self_consumption = float(self_consumption_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"selfConsumptionEnergyKWh inválido en el registro {index}."
            ) from error
        if not math.isfinite(self_consumption):
            raise ValueError(
                f"selfConsumptionEnergyKWh inválido en el registro {index}."
            )

        surplus_value = record.get("surplusEnergyKWh", 0)
        if surplus_value is None:
            surplus_value = 0
        try:
            surplus = float(surplus_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"surplusEnergyKWh inválido en el registro {index}."
            ) from error
        if not math.isfinite(surplus):
            raise ValueError(f"surplusEnergyKWh inválido en el registro {index}.")

        year = parsed_datetime.year
        if year not in holidays_by_year:
            holidays_by_year[year] = _spanish_national_holidays(year)
        holidays = holidays_by_year[year]
        category = (
            "weekend"
            if parsed_datetime.weekday() >= 5
            or parsed_datetime.date() in holidays
            else "weekday"
        )
        categorized_records[category].append(
            {
                "month": parsed_datetime.month,
                "hour": parsed_datetime.hour,
                "total_consumption_kWh": consumption + self_consumption,
                "self_consumption_kWh": self_consumption,
                "total_generation": self_consumption + surplus,
            }
        )

    result = {}
    for category, records in categorized_records.items():
        monthly_means = pd.DataFrame(
            records,
            columns=(
                "month",
                "hour",
                "total_consumption_kWh",
                "self_consumption_kWh",
                "total_generation",
            ),
        ).groupby(
            ["month", "hour"]
        ).agg(
            {
                "total_consumption_kWh": "mean",
                "self_consumption_kWh": "mean",
                "total_generation": "mean",
            }
        )
        monthly_means = monthly_means.reindex(
            pd.MultiIndex.from_product(
                [range(1, 13), range(24)], names=["month", "hour"]
            )
        )
        profile_rows = []
        for month in range(1, 13):
            row = {"month": month}
            for hour in range(24):
                means = monthly_means.loc[(month, hour)]
                row[str(hour)] = {
                    "total_consumption_kWh": (
                        None
                        if pd.isna(means["total_consumption_kWh"])
                        else float(means["total_consumption_kWh"])
                    ),
                    "self_consumption_kWh": (
                        None
                        if pd.isna(means["self_consumption_kWh"])
                        else float(means["self_consumption_kWh"])
                    ),
                    "total_generation": (
                        None
                        if pd.isna(means["total_generation"])
                        else float(means["total_generation"])
                    ),
                }
            profile_rows.append(row)
        result[f"{category}_consumption"] = profile_rows

    output_path = responses_dir / f"{cups_suffix}_day_profile_extended.json"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=responses_dir,
            prefix=f".{cups_suffix}_day_profile_extended_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(result, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return {"output_file": output_path.name}


def _load_monthly_profile(path):
    df = pd.read_csv(path)

    # Algunos CSV tienen la columna de mes con encabezado explícito "month".
    # Otros formatos (generados con index=True en pandas) tienen la primera etiqueta vacía o "Unnamed: 0".
    cols = list(df.columns)

    if len(cols) == 25 and cols[0] != "month":
        df = df.rename(columns={cols[0]: "month"})
        cols = list(df.columns)

    # Caso con index extra: Unnamed: 0, month, 0..23
    if len(cols) == 26 and cols[0] in ["Unnamed: 0", ""] and cols[1] == "month":
        df = df.iloc[:, 1:]
        cols = list(df.columns)

    if len(cols) != 25 or cols[0] != "month":
        raise ValueError(f"Archivo de perfil inválido: {path}. Se espera 25 columnas (month + 0-23)")

    # Asegurar orden y nombres de columnas
    df = df.copy()
    df.columns = ["month"] + [str(h) for h in range(24)]

    df = df.sort_values("month").reset_index(drop=True)
    if not df["month"].equals(pd.Series(range(1, 13), name="month")):
        raise ValueError(f"Archivo de perfil debe contener meses 1..12: {path}")

    return df


def _save_monthly_profile(df, path):
    df = df.copy()
    df.to_csv(path, index=False)


def generate_poruno_profiles_batch(directory, num_users_ce):
    """Genera perfiles poruno (weekday/weekend) para todos los usuarios en un directorio.

    Requiere:
    - perfil_comunitario_weekday.csv
    - perfil_comunitario_weekend.csv
    - archivos {user}_weekday_profile.csv y {user}_weekend_profile.csv

    Args:
        directory (str): Ruta al directorio de entrada/salida.
        num_users_ce (int): Número de usuarios de la Comunidad Energética.

    Returns:
        dict: Resultado con estado, usuarios procesados y archivos generados.
    """
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")
    if num_users_ce <= 0:
        raise ValueError("num_users_ce debe ser mayor que 0")

    community_weekday_path = directory / "perfil_comunitario_weekday.csv"
    community_weekend_path = directory / "perfil_comunitario_weekend.csv"

    if not community_weekday_path.exists() or not community_weekend_path.exists():
        raise FileNotFoundError("Faltan perfiles comunitarios weekday/weekend en el directorio")

    community_weekday = _load_monthly_profile(community_weekday_path)
    community_weekend = _load_monthly_profile(community_weekend_path)

    # Calcular consumo total de la CE (elemento a elemento)
    ce_total_weekday = community_weekday.copy()
    ce_total_weekend = community_weekend.copy()
    ce_total_weekday.iloc[:, 1:] = ce_total_weekday.iloc[:, 1:] * num_users_ce
    ce_total_weekend.iloc[:, 1:] = ce_total_weekend.iloc[:, 1:] * num_users_ce

    users_processed = []
    skipped_users = []
    errors = []
    generated_files = []

    weekday_files = sorted(directory.glob("*_weekday_profile.csv"))
    for weekday_file in weekday_files:
        user_id = weekday_file.name.replace("_weekday_profile.csv", "")
        weekend_file = directory / f"{user_id}_weekend_profile.csv"

        if not weekend_file.exists():
            skipped_users.append(user_id)
            continue

        try:
            user_weekday = _load_monthly_profile(weekday_file)
            user_weekend = _load_monthly_profile(weekend_file)

            # Calcular poruno con protección contra división por cero.
            poruno_weekday = user_weekday.copy()
            poruno_weekend = user_weekend.copy()

            # convertir a float para operaciones
            y_wd = user_weekday.iloc[:, 1:].astype(float)
            y_we = user_weekend.iloc[:, 1:].astype(float)
            tot_wd = ce_total_weekday.iloc[:, 1:].astype(float)
            tot_we = ce_total_weekend.iloc[:, 1:].astype(float)

            poruno_wd_vals = y_wd.div(tot_wd).fillna(0).replace([np.inf, -np.inf], 0)
            poruno_we_vals = y_we.div(tot_we).fillna(0).replace([np.inf, -np.inf], 0)

            poruno_weekday.iloc[:, 1:] = poruno_wd_vals
            poruno_weekend.iloc[:, 1:] = poruno_we_vals

            weekday_out = directory / f"{user_id}_weekday_poruno.csv"
            weekend_out = directory / f"{user_id}_weekend_poruno.csv"
            _save_monthly_profile(poruno_weekday, weekday_out)
            _save_monthly_profile(poruno_weekend, weekend_out)

            users_processed.append(user_id)
            generated_files.extend([str(weekday_out), str(weekend_out)])

        except Exception as exc:
            errors.append({"user": user_id, "error": str(exc)})

    if not users_processed and not errors:
        raise FileNotFoundError("No se encontraron usuarios con ambos archivos weekday/weekend para procesar.")

    return {
        "status": "ok" if not errors else "partial",
        "num_users_ce": num_users_ce,
        "users_processed": users_processed,
        "skipped_users": skipped_users,
        "generated_files": generated_files,
        "errors": errors,
        "message": f"Procesados {len(users_processed)} usuarios, omitidos {len(skipped_users)}, errores {len(errors)}"
    }


def _create_yearly_index(year):
    """Genera Index horario de 8760 horas para un año ignorando 29 de febrero."""
    rng = pd.date_range(start=f"{year}-01-01 00:00", end=f"{year}-12-31 23:00", freq="H")
    # Eliminar 29 de febrero si existe para tratar bisiestos como normal
    rng = rng[~((rng.month == 2) & (rng.day == 29))]
    if len(rng) != 8760:
        raise ValueError(f"El año {year} no produce 8760 horas tras excluir 29 feb, resulta {len(rng)}")
    return rng


def _spanish_national_holidays(year):
    """Devuelve set de fechas de festivos nacionales de España para el año dado."""
    # Festivos fijos
    holidays = {
        pd.Timestamp(f"{year}-01-01").date(),  # Año Nuevo
        pd.Timestamp(f"{year}-01-06").date(),  # Reyes
        pd.Timestamp(f"{year}-05-01").date(),  # Día del Trabajador
        pd.Timestamp(f"{year}-08-15").date(),  # Asunción
        pd.Timestamp(f"{year}-10-12").date(),  # Día de la Hispanidad
        pd.Timestamp(f"{year}-11-01").date(),  # Todos los Santos
        pd.Timestamp(f"{year}-12-06").date(),  # Constitución
        pd.Timestamp(f"{year}-12-08").date(),  # Inmaculada Concepción
        pd.Timestamp(f"{year}-12-25").date(),  # Navidad
    }

    # Cálculo de Easter para Good Friday
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = pd.Timestamp(year=year, month=month, day=day)
    good_friday = (easter - pd.Timedelta(days=2)).date()
    holidays.add(good_friday)

    return holidays


def _build_poruno_yearly_series(weekday_profile, weekend_profile, year=2027):
    """Convierte perfiles 12x24 weekday/weekend a vector anual de 8760 valores."""
    # Se esperan DF con columna 'month' y columnas '0'..'23'
    var_wd = weekday_profile.set_index('month').astype(float)
    var_we = weekend_profile.set_index('month').astype(float)

    # Asegurar meses 1..12 presentes
    if not var_wd.index.equals(pd.Index(range(1, 13), dtype=int)):
        raise ValueError("Perfil weekday debe contener meses 1..12")
    if not var_we.index.equals(pd.Index(range(1, 13), dtype=int)):
        raise ValueError("Perfil weekend debe contener meses 1..12")

    # Prellenar con 0 si falta hora
    for col in [str(h) for h in range(24)]:
        if col not in var_wd.columns:
            var_wd[col] = 0.0
        if col not in var_we.columns:
            var_we[col] = 0.0

    var_wd = var_wd[[str(h) for h in range(24)]].fillna(0.0)
    var_we = var_we[[str(h) for h in range(24)]].fillna(0.0)

    index = _create_yearly_index(year)
    holidays = _spanish_national_holidays(year)
    values = []
    for ts in index:
        month = ts.month
        hour = str(ts.hour)
        is_weekend_or_holiday = ts.weekday() >= 5 or ts.date() in holidays
        if is_weekend_or_holiday:
            values.append(var_we.at[month, hour])
        else:
            values.append(var_wd.at[month, hour])

    df_out = pd.DataFrame({'datetime': index, 'poruno': values})
    df_out = df_out.reset_index(drop=True)
    return df_out


def generate_poruno_8760_batch(directory, year=2027):
    """Genera archivos de 8760 horas para cada usuario poruno en el directorio."""
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")

    # Cargar cups_list.csv para mapear ids a CUPS completos
    cups_list_path = directory / "cups_list.csv"
    if not cups_list_path.exists():
        raise FileNotFoundError(f"Archivo cups_list.csv no encontrado en {directory}")
    
    cups_list = []
    with open(cups_list_path, 'r') as f:
        for line in f:
            cups, cif = line.strip().split(',')
            cups_list.append(cups)

    weekday_files = sorted(directory.glob("*_weekday_poruno.csv"))
    if not weekday_files:
        raise FileNotFoundError("No se encontraron archivos *_weekday_poruno.csv en el directorio")

    users_processed = []
    skipped_users = []
    errors = []
    generated_files = []

    # Acumular suma horaria global para info futura
    global_sum = None

    for weekday_file in weekday_files:
        user_id_full = weekday_file.name.replace("_weekday_poruno.csv", "")
        user_id_prefix = user_id_full  # usar el id completo
        
        # Buscar el CUPS que contenga el id
        cups_completo = None
        for cups in cups_list:
            if user_id_prefix in cups:
                cups_completo = cups
                break
        
        if cups_completo is None:
            errors.append({"user": user_id_prefix, "error": f"CUPS no encontrado en cups_list.csv que contenga {user_id_prefix}"})
            continue
        
        weekend_file = directory / f"{user_id_full}_weekend_poruno.csv"
        if not weekend_file.exists():
            skipped_users.append(user_id_prefix)
            continue

        try:
            user_weekday = _load_monthly_profile(weekday_file)
            user_weekend = _load_monthly_profile(weekend_file)

            user_8760 = _build_poruno_yearly_series(user_weekday, user_weekend, year)
            output_file = directory / f"{cups_completo}_8760_poruno_{year}.txt"
            # Generar archivo txt con formato: cups_completo;hora(4);coeficiente(6 decimales)
            with open(output_file, 'w') as f:
                for idx, row in user_8760.iterrows():
                    hour_num = idx + 1  # 1-based, 0001 to 8760
                    coef = f"{row['poruno']:.6f}"
                    line = f"{cups_completo};{hour_num:04d};{coef}\n"
                    f.write(line)

            # Contar tipos_dias (incluye festivos nacionales como weekend)
            holidays = _spanish_national_holidays(year)
            weekday_count = sum(
                1
                for ts in user_8760['datetime']
                if ts.weekday() < 5 and ts.date() not in holidays
            )
            weekend_count = 8760 - weekday_count

            # Para response: data[user][hour] = value
            user_data = {f"{idx+1:04d}": row['poruno'] for idx, row in user_8760.iterrows()}

            if global_sum is None:
                global_sum = user_8760["poruno"].copy()
            else:
                global_sum = global_sum.add(user_8760["poruno"], fill_value=0)

            users_processed.append({
                "user": cups_completo,
                "file": str(output_file),
                "tipos_dias": {"weekday": weekday_count, "weekend": weekend_count},
                "data": user_data
            })
            generated_files.append(str(output_file))

        except Exception as exc:
            errors.append({"user": user_id_prefix, "error": str(exc)})

    # total_sum vector si hay datos
    global_sum_info = None

    if global_sum is not None:
        if len(global_sum) != 8760:
            raise ValueError(f"Suma global no tiene 8760 valores, tiene {len(global_sum)}")
        # dato de control: rango (min/max) y primer/último valor
        global_sum_info = {
            "min": float(global_sum.min()),
            "max": float(global_sum.max()),
            "mean": float(global_sum.mean())
        }

    return {
        "status": "ok" if not errors else "partial",
        "year": year,
        "users_processed": [u["user"] for u in users_processed],
        "skipped_users": skipped_users,
        "generated_files": generated_files,
        "errors": errors,
        "global_sum_info": global_sum_info,
        "message": f"Procesados {len(users_processed)} usuarios, omitidos {len(skipped_users)}, errores {len(errors)}"
    }


def calcular_reparto_kwh_poruno(directory, year=2026):
    """Genera cups_list_reparto.csv con kWh asignados y porcentaje del total disponible."""
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")

    cups_list_path = directory / "cups_list.csv"
    if not cups_list_path.exists():
        raise FileNotFoundError(f"Archivo cups_list.csv no encontrado en {directory}")

    pvgis_path = directory / "pvgis_indextime_spain.txt"
    if not pvgis_path.exists():
        raise FileNotFoundError(f"Archivo pvgis_indextime_spain.txt no encontrado en {directory}")

    pvgis_energy = {}
    with open(pvgis_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.strip().split(";")
            if len(parts) != 2:
                raise ValueError(f"Formato inválido en {pvgis_path} en línea {line_num}: {line.strip()}")
            try:
                index = int(parts[0])
                energy = float(parts[1])
            except ValueError as exc:
                raise ValueError(f"Formato inválido en {pvgis_path} en línea {line_num}: {line.strip()}") from exc
            pvgis_energy[index] = energy

    total_available_kwh = sum(pvgis_energy.values())

    cups_rows = []
    with open(cups_list_path, "r", encoding="utf-8") as f:
        header = f.readline()
        if not header:
            raise ValueError(f"cups_list.csv está vacío: {cups_list_path}")
        for line_num, line in enumerate(f, 2):
            if not line.strip():
                continue
            parts = [part.strip() for part in line.strip().split(",")]
            if len(parts) < 2:
                raise ValueError(f"Formato inválido en cups_list.csv línea {line_num}: {line.strip()}")
            cups_rows.append({
                "cups": parts[0],
                "cif": parts[1]
            })

    results = []
    missing_files = []
    known_cups = {row["cups"] for row in cups_rows}

    for row in cups_rows:
        cups = row["cups"]
        archivo_poruno = directory / f"{cups}_8760_poruno_{year}.txt"
        if not archivo_poruno.exists():
            results.append({
                "cups": cups,
                "cif": row["cif"],
                "kwh_asignado": None,
                "pct_kwh_total": None
            })
            missing_files.append(cups)
            continue

        assigned_kwh = 0.0
        with open(archivo_poruno, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                parts = line.strip().split(";")
                if len(parts) != 3:
                    raise ValueError(f"Formato inválido en {archivo_poruno} línea {line_num}: {line.strip()}")
                try:
                    hour_index = int(parts[1])
                    coef = float(parts[2])
                except ValueError as exc:
                    raise ValueError(f"Formato inválido en {archivo_poruno} línea {line_num}: {line.strip()}") from exc
                energy = pvgis_energy.get(hour_index)
                if energy is None:
                    raise ValueError(f"Índice horario {hour_index} no encontrado en {pvgis_path}")
                assigned_kwh += coef * energy

        pct = None
        if total_available_kwh > 0:
            pct = assigned_kwh / total_available_kwh * 100

        results.append({
            "cups": cups,
            "cif": row["cif"],
            "kwh_asignado": assigned_kwh,
            "pct_kwh_total": pct
        })

    unknown_profiles = []
    for path in directory.glob(f"*_8760_poruno_{year}.txt"):
        cups = path.name.replace(f"_8760_poruno_{year}.txt", "")
        if cups not in known_cups:
            unknown_profiles.append(str(path.name))

    output_path = directory / "cups_list_reparto.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["cups", "cif", "kwh_asignado", "pct_kwh_total"])
        for row in results:
            kwh_value = "null" if row["kwh_asignado"] is None else f"{row['kwh_asignado']:.6f}"
            pct_value = "null" if row["pct_kwh_total"] is None else f"{row['pct_kwh_total']:.6f}"
            writer.writerow([row["cups"], row["cif"], kwh_value, pct_value])

    return {
        "status": "ok",
        "cups_list_reparto": str(output_path),
        "total_available_kwh": total_available_kwh,
        "rows": len(results),
        "missing_8760_files": missing_files,
        "unknown_8760_files": unknown_profiles,
        "message": f"cups_list_reparto.csv generado con {len(results)} filas."
    }


def corregir_y_combinar_poruno_8760(directory, year=2027):
    """Corrige el último usuario para que suma de coeficientes = 1 por hora y combina todos en un fichero.

    Args:
        directory (str): Ruta al directorio con los archivos 8760.
        year (int): Año de referencia.

    Returns:
        dict: Resultado con estado, usuarios procesados, fichero combinado y validaciones.
    """
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")

    # Buscar archivos *_8760_poruno_{year}.txt
    pattern = f"*_8760_poruno_{year}.txt"
    poruno_files = sorted(directory.glob(pattern))

    if not poruno_files:
        raise FileNotFoundError(f"No se encontraron archivos {pattern} en {directory}")
    
    if len(poruno_files) < 2:
        raise ValueError(f"Se requieren al menos 2 usuarios. Solo se encontró {len(poruno_files)}")

    # Identificar último usuario (último de la lista ordenada)
    last_file = poruno_files[-1]
    last_cups = last_file.name.replace(f"_8760_poruno_{year}.txt", "")
    other_files = poruno_files[:-1]

    # Diccionarios para almacenar datos
    hourly_sums_others = {f"{h:04d}": 0.0 for h in range(1, 8761)}
    all_user_data = {}  # {cups: {hora: coef, ...}, ...}
    errors = []

    # Procesar archivos de otros usuarios
    for file_path in other_files:
        try:
            filename = file_path.name
            cups = filename.replace(f"_8760_poruno_{year}.txt", "")
            user_data = {}

            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        parts = line.strip().split(';')
                        if len(parts) != 3:
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: formato incorrecto"
                            })
                            continue

                        file_cups, hour_str, coef_str = parts
                        
                        try:
                            hour = int(hour_str)
                            coef = float(coef_str)
                        except ValueError:
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: conversión numérica fallida"
                            })
                            continue

                        if hour not in range(1, 8761):
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: hora fuera de rango"
                            })
                            continue

                        hour_str_fmt = f"{hour:04d}"
                        hourly_sums_others[hour_str_fmt] += coef
                        user_data[hour_str_fmt] = coef

            all_user_data[cups] = user_data

        except Exception as exc:
            errors.append({"file": filename, "error": str(exc)})

    # Procesar último usuario
    last_user_data = {}
    try:
        with open(last_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    parts = line.strip().split(';')
                    if len(parts) != 3:
                        errors.append({
                            "file": last_file.name,
                            "error": f"Línea {line_num}: formato incorrecto"
                        })
                        continue

                    file_cups, hour_str, coef_str = parts
                    
                    try:
                        hour = int(hour_str)
                        coef = float(coef_str)
                    except ValueError:
                        errors.append({
                            "file": last_file.name,
                            "error": f"Línea {line_num}: conversión numérica fallida"
                        })
                        continue

                    hour_str_fmt = f"{hour:04d}"
                    last_user_data[hour_str_fmt] = coef

    except Exception as exc:
        errors.append({"file": last_file.name, "error": str(exc)})

    if not last_user_data:
        raise ValueError(f"No se pudo leer correctamente el archivo del último usuario {last_file.name}")

    # Validar y corregir último usuario
    last_user_corrected = {}
    validation_errors = []

    for hour in range(1, 8761):
        hour_str = f"{hour:04d}"
        sum_others = hourly_sums_others[hour_str]
        last_coef = last_user_data.get(hour_str, 0.0)
        sum_total = sum_others + last_coef
        
        # Ajuste necesario para que suma total = 1
        adjustment = 1.0 - sum_total
        
        # Validación: ajuste debe estar dentro de [-0.0001, 0.0001]
        if adjustment < -0.0001 or adjustment > 0.0001:
            validation_errors.append({
                "hour": hour,
                "sum_others": sum_others,
                "last_coef": last_coef,
                "sum_total": sum_total,
                "adjustment_needed": adjustment,
                "error": f"Ajuste fuera de rango: {adjustment:.6f}"
            })
        
        last_user_corrected[hour_str] = last_coef + adjustment

    # Si hay errores de validación, detener proceso
    if validation_errors:
        return {
            "status": "error",
            "year": year,
            "message": f"Corrección rechazada: {len(validation_errors)} horas con ajuste fuera de rango",
            "validation_errors": validation_errors[:10]  # Mostrar primeros 10
        }

    # Guardar último usuario corregido
    output_file_last = last_file
    try:
        with open(output_file_last, 'w', encoding='utf-8') as f:
            for hour in range(1, 8761):
                hour_str = f"{hour:04d}"
                coef = last_user_corrected[hour_str]
                line = f"{last_cups};{hour_str};{coef:.6f}\n"
                f.write(line)
    except Exception as exc:
        return {
            "status": "error",
            "year": year,
            "message": f"Error al guardar fichero del último usuario: {str(exc)}"
        }

    all_user_data[last_cups] = last_user_corrected

    # Crear fichero combinado
    combined_file = directory / f"todos_usuarios_8760_poruno_{year}.txt"
    try:
        with open(combined_file, 'w', encoding='utf-8') as f:
            # Ordenar por CUPS para consistencia
            for cups in sorted(all_user_data.keys()):
                user_data = all_user_data[cups]
                for hour in range(1, 8761):
                    hour_str = f"{hour:04d}"
                    coef = user_data.get(hour_str, 0.0)
                    line = f"{cups};{hour_str};{coef:.6f}\n"
                    f.write(line)
    except Exception as exc:
        return {
            "status": "error",
            "year": year,
            "message": f"Error al guardar fichero combinado: {str(exc)}"
        }

    # Verificación final: sumar todos para confirmar
    final_verification = {f"{h:04d}": 0.0 for h in range(1, 8761)}
    for user_data in all_user_data.values():
        for hour_str, coef in user_data.items():
            final_verification[hour_str] += coef

    verification_errors = []
    for hour in range(1, 8761):
        hour_str = f"{hour:04d}"
        total = final_verification[hour_str]
        if abs(total - 1.0) > 1e-5:
            verification_errors.append({
                "hour": hour,
                "total_sum": total,
                "error": f"Suma final no es 1: {total:.6f}"
            })

    return {
        "status": "ok" if not verification_errors else "partial",
        "year": year,
        "num_users": len(all_user_data),
        "last_user_corrected": last_cups,
        "other_users": len(other_files),
        "combined_file": str(combined_file),
        "last_user_file": str(output_file_last),
        "verification_errors": verification_errors if verification_errors else None,
        "message": f"Corrección completada. {len(all_user_data)} usuarios. Ajustes aplicados al último usuario."
    }


def validar_suma_poruno_8760(directory, year=2027):
    """Valida que la suma de coeficientes poruno sea 1 para cada hora del año.

    Args:
        directory (str): Ruta al directorio con los archivos 8760.
        year (int): Año de referencia.

    Returns:
        dict: Resultado con estado, archivos procesados y estadísticas.
    """
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")

    # Buscar archivos *_8760_poruno_{year}.txt
    pattern = f"*_8760_poruno_{year}.txt"
    poruno_files = list(directory.glob(pattern))

    if not poruno_files:
        raise FileNotFoundError(f"No se encontraron archivos {pattern} en {directory}")

    # Inicializar diccionario para acumular sumas por hora
    hourly_sums = {f"{h:04d}": 0.0 for h in range(1, 8761)}

    users_processed = []
    errors = []

    # Procesar cada archivo de usuario
    for file_path in poruno_files:
        try:
            # Extraer CUPS del nombre del archivo
            filename = file_path.name
            cups = filename.replace(f"_8760_poruno_{year}.txt", "")

            # Leer archivo y procesar líneas
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        parts = line.strip().split(';')
                        if len(parts) != 3:
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: formato incorrecto, esperado 3 partes separadas por ';'"
                            })
                            continue

                        file_cups, hour_str, coef_str = parts

                        # Validar que el CUPS del archivo coincida con el del contenido
                        if file_cups != cups:
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: CUPS del archivo ({cups}) no coincide con CUPS del contenido ({file_cups})"
                            })
                            continue

                        try:
                            hour = int(hour_str)
                            coef = float(coef_str)
                        except ValueError:
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: hora o coeficiente no numérico"
                            })
                            continue

                        if hour not in range(1, 8761):
                            errors.append({
                                "file": filename,
                                "error": f"Línea {line_num}: hora {hour} fuera de rango 1-8760"
                            })
                            continue

                        hourly_sums[f"{hour:04d}"] += coef

            users_processed.append(cups)

        except Exception as exc:
            errors.append({"file": filename, "error": str(exc)})

    if not users_processed:
        raise ValueError("No se pudieron procesar archivos válidos")

    # Calcular diferencias (1 - suma_real)
    differences = {}
    stats = {
        "total_hours": 8760,
        "hours_with_exact_sum": 0,
        "hours_with_deviation": 0,
        "max_deviation": 0.0,
        "min_deviation": 0.0,
        "mean_deviation": 0.0
    }

    deviations = []
    for hour_str, total_sum in hourly_sums.items():
        diff = 1.0 - total_sum
        differences[hour_str] = diff
        deviations.append(abs(diff))

        if abs(diff) < 1e-6:  # Considerar prácticamente 1
            stats["hours_with_exact_sum"] += 1
        else:
            stats["hours_with_deviation"] += 1

    if deviations:
        stats["max_deviation"] = max(deviations)
        stats["min_deviation"] = min(deviations)
        stats["mean_deviation"] = sum(deviations) / len(deviations)

    # Guardar archivo con diferencias
    output_file = directory / f"validacion_suma_poruno_{year}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Validación suma coeficientes poruno {year}\n")
        f.write(f"# Total usuarios procesados: {len(users_processed)}\n")
        f.write(f"# Formato: hora;diferencia_con_1\n")
        for hour in range(1, 8761):
            hour_str = f"{hour:04d}"
            diff = differences[hour_str]
            f.write(f"{hour_str};{diff:.6f}\n")

    return {
        "status": "ok" if not errors else "partial",
        "year": year,
        "users_processed": users_processed,
        "num_users": len(users_processed),
        "output_file": str(output_file),
        "stats": stats,
        "errors": errors,
        "message": f"Validación completada. {stats['hours_with_exact_sum']}/8760 horas con suma exacta, "
                  f"desviación máxima: {stats['max_deviation']:.6f}"
    }
