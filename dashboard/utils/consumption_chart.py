import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px


CONSUMPTION_JSON_PATTERN = re.compile(
    r"^ES.+_\d{4}_\d{2}_\d{4}_\d{2}\.json$"
)


def find_consumption_json_files(responses_dir: Path) -> list[Path]:
    """Return consumption JSON files without modifying the responses directory."""
    return sorted(
        path
        for path in responses_dir.iterdir()
        if path.is_file() and CONSUMPTION_JSON_PATTERN.match(path.name)
    )


def load_consumption_data(json_path: Path) -> pd.DataFrame:
    """Load dates and consumption values from one consumption JSON file."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    records = pd.DataFrame(data)
    required_columns = {"date", "time", "consumptionKWh"}
    missing_columns = required_columns.difference(records.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Faltan columnas necesarias: {missing}")

    date_text = records["date"].astype(str).str.replace("/", "-", regex=False)
    time_text = records["time"].astype(str)
    midnight_records = time_text.eq("24:00")
    time_text = time_text.where(~midnight_records, "00:00")
    timestamps = pd.to_datetime(
        date_text + " " + time_text,
        errors="coerce",
    )
    timestamps = timestamps + pd.to_timedelta(midnight_records.astype(int), unit="D")

    chart_data = pd.DataFrame(
        {
            "fecha": timestamps,
            "consumo_kWh": pd.to_numeric(
                records["consumptionKWh"], errors="coerce"
            ),
        }
    ).dropna().sort_values("fecha")

    if chart_data.empty:
        raise ValueError("El fichero no contiene datos válidos para representar.")
    return chart_data


def build_consumption_figure(chart_data: pd.DataFrame, title: str):
    """Build the hourly consumption chart from normalized chart data."""
    figure = px.line(
        chart_data,
        x="fecha",
        y="consumo_kWh",
        labels={
            "fecha": "Fecha y hora",
            "consumo_kWh": "Consumo (kWh)",
        },
        title=title,
    )
    figure.update_layout(hovermode="x unified")
    return figure