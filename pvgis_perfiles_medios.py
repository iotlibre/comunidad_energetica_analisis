import calendar
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict
from zoneinfo import ZoneInfo


PROFILE_YEAR = 2023
SPAIN_TIMEZONE = ZoneInfo("Europe/Madrid")


def _local_timestamp_for_hour_offset(hour_offset: int, year: int = PROFILE_YEAR) -> datetime:
    year_start_utc = datetime(
        year, 1, 1, tzinfo=SPAIN_TIMEZONE
    ).astimezone(timezone.utc)
    timestamp_utc = year_start_utc + timedelta(hours=hour_offset)
    return timestamp_utc.astimezone(SPAIN_TIMEZONE)


def calcular_perfiles_medios_por_usuario(
    pvgis_path: str,
    num_usuarios: int,
    year: int = PROFILE_YEAR,
) -> Dict[str, object]:
    """Calculate 24-hour seasonal mean generation profiles per user."""
    source_path = Path(pvgis_path)
    rows = source_path.read_text(encoding="utf-8").splitlines()
    expected_hours = 8784 if calendar.isleap(year) else 8760
    if len(rows) != expected_hours:
        raise ValueError(
            f"El fichero PVGIS debe contener exactamente {expected_hours} horas para {year}."
        )

    hourly_values = []
    for expected_index, row in enumerate(rows, start=1):
        fields = row.split(";")
        if len(fields) != 2 or fields[0] != f"{expected_index:04d}":
            raise ValueError(f"Formato o índice incorrecto en la hora {expected_index}.")
        try:
            value = float(fields[1])
        except ValueError as error:
            raise ValueError(f"Valor no numérico en la hora {expected_index}.") from error
        if not math.isfinite(value):
            raise ValueError(f"Valor no finito en la hora {expected_index}.")
        hourly_values.append(value)

    seasons = {
        "verano": {
            "months": list(range(4, 10)),
            "totals": [0.0] * 24,
            "counts": [0] * 24,
        },
        "invierno": {
            "months": [10, 11, 12, 1, 2, 3],
            "totals": [0.0] * 24,
            "counts": [0] * 24,
        },
    }
    for offset, value in enumerate(hourly_values):
        timestamp = _local_timestamp_for_hour_offset(offset, year)
        season = "verano" if 4 <= timestamp.month <= 9 else "invierno"
        seasons[season]["totals"][timestamp.hour] += value
        seasons[season]["counts"][timestamp.hour] += 1

    profiles = {}
    for season_name, season_data in seasons.items():
        profiles[season_name] = {
            "meses": season_data["months"],
            "unidad": "kWh/usuario/hora",
            "valores": [
                {
                    "hora": f"{hour:02d}:00",
                    "muestras": season_data["counts"][hour],
                    "generacion_media": (
                        season_data["totals"][hour]
                        / season_data["counts"][hour]
                        / num_usuarios
                    ),
                }
                for hour in range(24)
            ],
        }

    output_files = {}
    file_names = {
        "verano": "summer",
        "invierno": "winter",
    }
    for season_name, file_season in file_names.items():
        output_path = source_path.parent / (
            f"pvgis_spain_profile_{file_season}_{year}.json"
        )
        profile_data = {
            "year": year,
            "num_usuarios": num_usuarios,
            "estacion": season_name,
            **profiles[season_name],
        }
        output_path.write_text(
            json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_files[season_name] = str(output_path)

    return {
        "status": "ok",
        "year": year,
        "num_usuarios": num_usuarios,
        "fichero_origen": str(source_path),
        "ficheros_generados": output_files,
    }