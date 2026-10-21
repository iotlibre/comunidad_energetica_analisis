import os
import json
import re
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent
TOP_LEVEL_DIRS = {"responses", "registers", "logs", "community_profiles"}


def _resolve_path(path_value: Optional[str], base_dir: Path) -> Path:
    """Resuelve rutas de forma robusta tanto para rutas absolutas como relativas.

    El comportamiento previo unía siempre la ruta relativa al directorio del JSON,
    lo que provocaba duplicaciones como:
    responses/ce_Valdes3/consumos_2026/responses/ce_Valdes3/...
    """
    if not path_value:
        return base_dir

    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate

    # Si la ruta ya apunta a un directorio de proyecto (por ejemplo
    # "responses/..." o "./responses/..."), intentamos resolverla desde la
    # raíz del proyecto antes de caer al directorio del JSON. Esto evita las
    # duplicaciones de rutas cuando el servidor ejecuta el proceso desde otro
    # directorio de trabajo.
    if candidate.parts and candidate.parts[0] in TOP_LEVEL_DIRS:
        project_candidate = (PROJECT_ROOT / candidate).resolve()
        cwd_candidate = (Path.cwd() / candidate).resolve()

        if project_candidate.exists() or not cwd_candidate.exists():
            return project_candidate
        if cwd_candidate.exists():
            return cwd_candidate

    return (base_dir / candidate).resolve()


def calcular_energia_autoconsumida(directorio: str, mes_inicio: int, anio_inicio: int, mes_fin: int, anio_fin: int) -> Dict[str, Any]:
    """
    Calcula la energía de autoconsumo por usuario y mes dentro del rango especificado.

    Args:
        directorio (str): Directorio donde están los archivos JSON de datos energéticos.
        mes_inicio (int): Mes de inicio (1-12).
        anio_inicio (int): Año de inicio.
        mes_fin (int): Mes de fin (1-12).
        anio_fin (int): Año de fin.

    Returns:
        Dict con el resultado del cálculo, incluyendo DataFrame en formato JSON serializable.
    """
    # Validar rango de fechas
    fecha_inicio = datetime(anio_inicio, mes_inicio, 1)
    if mes_fin == 12:
        fecha_fin = datetime(anio_fin + 1, 1, 1)
    else:
        fecha_fin = datetime(anio_fin, mes_fin + 1, 1)

    # Lista para almacenar todos los datos
    all_data = []

    # Leer todos los archivos JSON en el directorio
    for filename in os.listdir(directorio):
        if filename.endswith('.json') and not filename.startswith('__'):
            filepath = os.path.join(directorio, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_data.extend(data)
            except Exception as e:
                print(f"Error leyendo {filename}: {e}")
                continue

    if not all_data:
        return {
            "status": "error",
            "message": "No se encontraron datos válidos en el directorio"
        }

    # Convertir a DataFrame
    df = pd.DataFrame(all_data)

    # Convertir date a datetime
    df['date'] = pd.to_datetime(df['date'], format='%Y/%m/%d')

    # Filtrar por rango de fechas
    df_filtered = df[(df['date'] >= fecha_inicio) & (df['date'] < fecha_fin)].copy()

    if df_filtered.empty:
        return {
            "status": "error",
            "message": "No hay datos en el rango de fechas especificado"
        }

    # Rellenar NaN con 0 para sumas
    df_filtered[['consumptionKWh', 'surplusEnergyKWh', 'generationEnergyKWh', 'selfConsumptionEnergyKWh']] = \
        df_filtered[['consumptionKWh', 'surplusEnergyKWh', 'generationEnergyKWh', 'selfConsumptionEnergyKWh']].fillna(0)

    # Crear columna de mes-año para agrupar
    df_filtered['mes_anio'] = df_filtered['date'].dt.to_period('M')

    # Agrupar por cups y mes_anio, sumar los valores
    grouped = df_filtered.groupby(['cups', 'mes_anio']).agg({
        'consumptionKWh': 'sum',
        'surplusEnergyKWh': 'sum',
        'generationEnergyKWh': 'sum',
        'selfConsumptionEnergyKWh': 'sum'
    }).reset_index()

    # Pivotear para tener meses como columnas
    pivot = grouped.pivot(index='cups', columns='mes_anio', values=['consumptionKWh', 'surplusEnergyKWh', 'generationEnergyKWh', 'selfConsumptionEnergyKWh'])

    # Renombrar columnas para el formato deseado: mes_con, mes_sur, etc.
    new_columns = []
    for col in pivot.columns:
        mes = str(col[1])  # e.g., '2025-01'
        tipo = col[0]
        if tipo == 'consumptionKWh':
            abreviado = 'con'
        elif tipo == 'surplusEnergyKWh':
            abreviado = 'sur'
        elif tipo == 'generationEnergyKWh':
            abreviado = 'gen'
        elif tipo == 'selfConsumptionEnergyKWh':
            abreviado = 'self'
        new_columns.append(f"{mes}_{abreviado}")
    pivot.columns = new_columns

    # Calcular totales
    total_con = pivot.filter(regex='_con$').sum(axis=1)
    total_sur = pivot.filter(regex='_sur$').sum(axis=1)
    total_gen = pivot.filter(regex='_gen$').sum(axis=1)
    total_self = pivot.filter(regex='_self$').sum(axis=1)

    # Crear DataFrame de totales
    totales_df = pd.DataFrame({
        'total_con': total_con,
        'total_sur': total_sur,
        'total_gen': total_gen,
        'total_self': total_self
    })

    # Combinar
    result_df = pd.concat([pivot, totales_df], axis=1)

    # Reordenar columnas: para cada mes, con, sur, gen, self, luego totales
    meses = sorted(set([col.split('_')[0] for col in pivot.columns if '_' in col]))
    ordered_columns = []
    for mes in meses:
        for cat in ['con', 'sur', 'gen', 'self']:
            col_name = f"{mes}_{cat}"
            if col_name in result_df.columns:
                ordered_columns.append(col_name)
    # Agregar totales al final
    ordered_columns.extend(['total_con', 'total_sur', 'total_gen', 'total_self'])
    result_df = result_df[ordered_columns]

    # Generar archivo CSV
    output_filename = f"energia_autoconsumida_{anio_inicio}_{mes_inicio:02d}_{anio_fin}_{mes_fin:02d}.csv"
    output_path = os.path.join(directorio, output_filename)
    result_df.to_csv(output_path, index=True)  # index=True para incluir cups como índice, pero mejor resetear

    # Resetear índice para incluir cups como columna
    result_df_reset = result_df.reset_index()
    result_df_reset.to_csv(output_path, index=False)

    return {
        "status": "ok",
        "directorio": directorio,
        "rango_fechas": {
            "inicio": f"{anio_inicio}-{mes_inicio:02d}",
            "fin": f"{anio_fin}-{mes_fin:02d}"
        },
        "usuarios_procesados": len(result_df),
        "output_file": output_path
    }
def _parse_date_time(date_str: str, time_str: str, json_path: Path) -> datetime:
    """Parsea una fecha y hora del JSON de consumo, incluyendo 24:00 como medianoche del día siguiente."""
    normalized_time = time_str.strip()
    if re.fullmatch(r"24:00", normalized_time):
        base_date = datetime.strptime(date_str, "%Y/%m/%d")
        return base_date + timedelta(days=1)

    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{date_str} {normalized_time}", fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato inválido de fecha/hora en {json_path}: {date_str} {time_str}")


def _is_ambiguous_local_time(dt: datetime, tz: ZoneInfo) -> bool:
    dt_fold0 = dt.replace(tzinfo=tz, fold=0)
    dt_fold1 = dt.replace(tzinfo=tz, fold=1)
    return dt_fold0.utcoffset() != dt_fold1.utcoffset()


def _load_proyeccion_json(archivo_json: Path):
    if not archivo_json.exists():
        raise FileNotFoundError(f"Archivo JSON no encontrado: {archivo_json}")

    try:
        with open(archivo_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Formato JSON inválido en {archivo_json}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Se esperaba un array JSON en {archivo_json}")

    stem = archivo_json.stem
    parts = stem.rsplit("_", 4)
    if len(parts) != 5:
        raise ValueError(
            f"Nombre de archivo inválido: {archivo_json.name}. Debe tener formato CUPS_YYYY_MM_YYYY_MM.json"
        )

    cups = parts[0]
    try:
        year_start = int(parts[1])
        month_start = int(parts[2])
        year_end = int(parts[3])
        month_end = int(parts[4])
    except ValueError as exc:
        raise ValueError(
            f"Nombre de archivo inválido: {archivo_json.name}. Debe tener formato CUPS_YYYY_MM_YYYY_MM.json"
        ) from exc

    if year_start != year_end:
        raise ValueError(
            f"El fichero JSON debe pertenecer a un único año. Encontrado {year_start} y {year_end}."
        )

    consumption_by_index = {}
    datetime_by_index = {}
    year = year_end
    tz = ZoneInfo("Europe/Madrid")
    year_start_utc = datetime(year, 1, 1, tzinfo=tz).astimezone(timezone.utc)
    seen_local_times = {}
    uses_datadis_end_times = any(
        isinstance(item, dict) and str(item.get('time', '')).strip() == '24:00'
        for item in data
    )

    for item in data:
        if not isinstance(item, dict):
            continue

        date_str = item.get('date')
        time_str = item.get('time')
        if date_str is None or time_str is None:
            continue

        consumption_raw = item.get('consumptionKWh')
        if consumption_raw is None:
            continue

        try:
            consumption = float(consumption_raw)
            self_consumption = float(item.get('selfConsumptionEnergyKWh') or 0)
        except (TypeError, ValueError):
            continue

        consumption += self_consumption

        dt = _parse_date_time(date_str, time_str, archivo_json)
        source_year = int(date_str[:4])
        if (dt.year != year and not uses_datadis_end_times) or (
            uses_datadis_end_times and source_year != year
        ):
            raise ValueError(
                f"Las fechas del archivo {archivo_json.name} deben corresponder al año {year}. Encontrado {dt.year}."
            )

        count = seen_local_times.get(dt, 0)
        seen_local_times[dt] = count + 1
        fold = 0

        if count > 0:
            if not _is_ambiguous_local_time(dt, tz):
                raise ValueError(
                    f"Hora duplicada no ambigua en {archivo_json.name}: {date_str} {time_str}"
                )
            if count > 1:
                raise ValueError(
                    f"Más de dos ocurrencias de hora ambigua en {archivo_json.name}: {date_str} {time_str}"
                )
            fold = 1

        localized_dt = dt.replace(tzinfo=tz, fold=fold)
        utc_dt = localized_dt.astimezone(timezone.utc)
        elapsed_hours = int((utc_dt - year_start_utc).total_seconds() // 3600)
        index = elapsed_hours if uses_datadis_end_times else elapsed_hours + 1

        if index < 1 or index > 8760:
            raise ValueError(
                f"Hora fuera de rango en {archivo_json.name}: {date_str} {time_str} -> índice {index}"
            )

        if index in consumption_by_index:
            raise ValueError(
                f"Índice horario duplicado en {archivo_json.name}: {index}"
            )

        consumption_by_index[index] = consumption
        datetime_by_index[index] = dt

    if not consumption_by_index:
        raise ValueError(f"No se encontraron horas de consumo válidas en {archivo_json}")

    return cups, year, consumption_by_index, datetime_by_index


def _load_pvgis_energy(pvgis_path: Path) -> Dict[int, float]:
    if not pvgis_path.exists():
        raise FileNotFoundError(f"Archivo PVGIS no encontrado: {pvgis_path}")

    pvgis_energy = {}
    with open(pvgis_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.strip().split(";")
            if len(parts) != 2:
                raise ValueError(f"Formato inválido en {pvgis_path} línea {line_num}: {line.strip()}")
            try:
                index = int(parts[0])
                energy = float(parts[1])
            except ValueError as exc:
                raise ValueError(f"Formato inválido en {pvgis_path} línea {line_num}: {line.strip()}") from exc
            pvgis_energy[index] = energy
    return pvgis_energy


def _load_poruno_coefficients(coef_path: Path, cups: str) -> Dict[int, float]:
    if not coef_path.exists():
        raise FileNotFoundError(f"Archivo de coeficientes no encontrado: {coef_path}")

    coefficients = {}
    with open(coef_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.strip().split(";")
            if len(parts) < 3:
                raise ValueError(f"Formato inválido en {coef_path} línea {line_num}: {line.strip()}")
            cups_line = parts[0].strip()
            try:
                index = int(parts[1])
                coef = float(parts[2])
            except ValueError as exc:
                raise ValueError(f"Formato inválido en {coef_path} línea {line_num}: {line.strip()}") from exc
            if cups_line != cups:
                raise ValueError(
                    f"El archivo {coef_path.name} contiene CUPS distinto en la línea {line_num}: {cups_line} vs {cups}"
                )
            coefficients[index] = coef
    return coefficients


def _parse_constant_coefficient(coef_input: Optional[Union[str, float, int]]) -> Optional[float]:
    if coef_input is None:
        return None

    if isinstance(coef_input, (int, float)):
        return float(coef_input)

    if isinstance(coef_input, str):
        value = coef_input.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    return None


def _append_historial(historia_path: Path, registro: Dict[str, Any]) -> None:
    historia = []
    historia_path.parent.mkdir(parents=True, exist_ok=True)

    if historia_path.exists():
        try:
            with open(historia_path, 'r', encoding='utf-8') as f:
                historia = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"El archivo de historial {historia_path} contiene JSON inválido: {exc}") from exc

        if not isinstance(historia, list):
            raise ValueError(f"El archivo de historial {historia_path} no contiene un array JSON")

    historia.append(registro)
    with open(historia_path, 'w', encoding='utf-8') as f:
        json.dump(historia, f, ensure_ascii=False, indent=2)


def calcular_proyeccion_autoconsumida(
    archivo_json: str,
    pvgis_file: Optional[str] = None,
    coef_file: Optional[str] = None,
    historial_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Calcula la proyección de autoconsumo hora a hora para un CUPS."""
    json_path = Path(archivo_json)
    cups, year, consumption_by_index, datetime_by_index = _load_proyeccion_json(json_path)
    directory = json_path.parent

    if pvgis_file is None:
        pvgis_path = directory / 'pvgis_indextime_spain.txt'
    else:
        pvgis_path = _resolve_path(pvgis_file, directory)

    coef_path_display = None
    if coef_file is None:
        coef_path = directory / f"{cups}_8760_poruno_{year}.txt"
        coef_path_display = str(coef_path)
        coefficients = _load_poruno_coefficients(coef_path, cups)
    else:
        constant_coefficient = _parse_constant_coefficient(coef_file)
        if constant_coefficient is not None:
            coef_path_display = str(coef_file)
            coefficients = {index: constant_coefficient for index in consumption_by_index.keys()}
        else:
            coef_path = _resolve_path(coef_file, directory)
            coef_path_display = str(coef_path)
            coefficients = _load_poruno_coefficients(coef_path, cups)

    if historial_file is None:
        historia_path = directory / 'resultados_calculo_autoconsumida.json'
    else:
        historia_path = _resolve_path(historial_file, directory)

    pvgis_energy = _load_pvgis_energy(pvgis_path)

    energia_exportada = 0.0
    energia_autoconsumida = 0.0
    energia_importada = 0.0
    horas_incluidas = 0
    included_datetimes = []
    missing_pvgis = 0
    missing_coef = 0

    for index, consumption in consumption_by_index.items():
        pvgis_value = pvgis_energy.get(index)
        coef = coefficients.get(index)

        if pvgis_value is None:
            missing_pvgis += 1
            continue
        if coef is None:
            missing_coef += 1
            continue

        generated = pvgis_value * coef
        net = generated - consumption

        if net >= 0:
            energia_exportada += net
            energia_autoconsumida += consumption
        else:
            energia_importada += abs(net)
            energia_autoconsumida += generated

        horas_incluidas += 1
        included_datetimes.append(datetime_by_index[index])

    if horas_incluidas == 0:
        return {
            "status": "error",
            "message": "No se encontraron horas comunes en el JSON, PVGIS y el fichero de coeficientes poruno.",
            "archivo_json": str(json_path),
            "pvgis_file": str(pvgis_path),
            "coef_file": str(coef_path),
            "horas_disponibles_json": len(consumption_by_index),
            "missing_pvgis": missing_pvgis,
            "missing_coef": missing_coef
        }

    included_datetimes.sort()
    primera_fecha = included_datetimes[0].isoformat()
    ultima_fecha = included_datetimes[-1].isoformat()

    registro = {
        "fecha": datetime.utcnow().isoformat() + 'Z',
        "archivo": str(json_path),
        "cups": cups,
        "year": year,
        "horas_incluidas": horas_incluidas,
        "horas_disponibles_json": len(consumption_by_index),
        "missing_pvgis": missing_pvgis,
        "missing_coef": missing_coef,
        "primera_fecha": primera_fecha,
        "ultima_fecha": ultima_fecha,
        "energia_exportada": energia_exportada,
        "energia_autoconsumida": energia_autoconsumida,
        "energia_importada": energia_importada,
        "pvgis_file": str(pvgis_path),
        "coef_file": coef_path_display
    }

    _append_historial(historia_path, registro)

    return {
        "status": "ok",
        "archivo_json": str(json_path),
        "cups": cups,
        "year": year,
        "horas_incluidas": horas_incluidas,
        "horas_disponibles_json": len(consumption_by_index),
        "missing_pvgis": missing_pvgis,
        "missing_coef": missing_coef,
        "primera_fecha": primera_fecha,
        "ultima_fecha": ultima_fecha,
        "energia_exportada": energia_exportada,
        "energia_autoconsumida": energia_autoconsumida,
        "energia_importada": energia_importada,
        "pvgis_file": str(pvgis_path),
        "coef_file": coef_path_display,
        "historial_file": str(historia_path)
    }
