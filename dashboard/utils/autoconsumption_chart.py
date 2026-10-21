from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


AUTOCONSUMPTION_FILE_PATTERN = re.compile(
    r"^energia_autoconsumida_\d{4}_\d{2}_\d{4}_\d{2}\.csv$"
)
_MONTH_COLUMN_PATTERN = re.compile(r"^(\d{4}-\d{2})_(con|sur|gen|self)$")
_METRIC_NAMES = {
    "con": "energia_importada_kWh",
    "sur": "energia_exportada_kWh",
    "gen": "energia_generada_kWh",
    "self": "energia_autoconsumida_kWh",
}


def find_autoconsumption_files(responses_dir: Path) -> list[Path]:
    """Return supported autoconsumption CSV files without modifying the directory."""
    if not responses_dir.is_dir():
        return []
    return sorted(
        path
        for path in responses_dir.iterdir()
        if path.is_file() and AUTOCONSUMPTION_FILE_PATTERN.match(path.name)
    )


def load_autoconsumption_data(csv_path: Path) -> pd.DataFrame:
    """Load one autoconsumption CSV as one row per CUPS and month."""
    source = pd.read_csv(csv_path)
    if "cups" not in source.columns:
        raise ValueError("El fichero debe contener la columna 'cups'.")

    monthly_columns = {}
    for column in source.columns:
        match = _MONTH_COLUMN_PATTERN.match(str(column))
        if match:
            monthly_columns.setdefault(match.group(1), {})[match.group(2)] = column

    if not monthly_columns:
        raise ValueError("No se encontraron columnas mensuales con formato YYYY-MM_*." )

    missing_metrics = {
        month: sorted(set(_METRIC_NAMES) - set(columns))
        for month, columns in monthly_columns.items()
        if set(columns) != set(_METRIC_NAMES)
    }
    missing_metrics = {
        month: metrics for month, metrics in missing_metrics.items() if metrics
    }
    if missing_metrics:
        details = "; ".join(
            f"{month}: {', '.join(metrics)}"
            for month, metrics in sorted(missing_metrics.items())
        )
        raise ValueError(f"Faltan columnas mensuales: {details}.")

    records = []
    for month in sorted(monthly_columns):
        columns = monthly_columns[month]
        numeric_values = source[list(columns.values())].apply(
            pd.to_numeric, errors="coerce"
        )
        invalid_values = numeric_values.isna() & source[list(columns.values())].notna()
        if invalid_values.any().any():
            invalid_columns = sorted(
                column
                for column in invalid_values.columns
                if invalid_values[column].any()
            )
            raise ValueError(
                "Hay valores no numéricos en: " + ", ".join(invalid_columns) + "."
            )

        month_data = pd.DataFrame({"cups": source["cups"].astype(str), "mes": month})
        for suffix, output_name in _METRIC_NAMES.items():
            month_data[output_name] = numeric_values[columns[suffix]].values
        records.append(month_data)

    result = pd.concat(records, ignore_index=True)
    if result["cups"].eq("nan").any() or result["cups"].eq("").any():
        raise ValueError("El fichero contiene un CUPS vacío.")
    return result
