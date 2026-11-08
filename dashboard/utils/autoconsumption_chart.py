from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


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
_BALANCE_CHART_MIN_HEIGHT = 400
_BALANCE_CHART_ROW_HEIGHT = 21
_BALANCE_CHART_VERTICAL_MARGIN = 120
_RENEWABLE_PERCENTAGE_CHART_MIN_HEIGHT = 160
_RENEWABLE_PERCENTAGE_CHART_ROW_HEIGHT = 11
_RENEWABLE_PERCENTAGE_CHART_VERTICAL_MARGIN = 48
_RENEWABLE_PERCENTAGE_BELOW_COMMUNITY_COLOR = "#2e7d32"
_RENEWABLE_PERCENTAGE_WITHIN_RANGE_COLOR = "#7b1fa2"
_RENEWABLE_PERCENTAGE_ABOVE_100_COLOR = "#1976d2"


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


def build_user_energy_balance_figure(data: pd.DataFrame, colors: dict) -> go.Figure:
    """Build two stacked horizontal energy-balance bars for each user."""
    required_columns = {
        "cups",
        "energia_importada_kWh",
        "energia_autoconsumida_kWh",
        "energia_generada_kWh",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(
            "Faltan columnas para el balance energético: "
            + ", ".join(sorted(missing_columns))
            + "."
        )

    users = data.groupby("cups", as_index=False)[
        [
            "energia_importada_kWh",
            "energia_autoconsumida_kWh",
            "energia_generada_kWh",
        ]
    ].sum()
    users["energia_consumida_kWh"] = (
        users["energia_importada_kWh"] + users["energia_autoconsumida_kWh"]
    )
    users["energia_exportada_balance_kWh"] = (
        users["energia_generada_kWh"] - users["energia_autoconsumida_kWh"]
    )
    users = users.sort_values(
        "energia_consumida_kWh", ascending=False, kind="stable"
    )

    cups = users["cups"].tolist()
    figure = go.Figure()
    figure.add_bar(
        name="Autoconsumida",
        x=users["energia_autoconsumida_kWh"],
        y=cups,
        orientation="h",
        offsetgroup="consumo",
        legendgroup="autoconsumida",
        marker_color=colors["Autoconsumida"],
        showlegend=True,
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.2f} kWh<extra></extra>",
    )
    figure.add_bar(
        name="Importada",
        x=users["energia_importada_kWh"],
        y=cups,
        orientation="h",
        offsetgroup="consumo",
        legendgroup="importada",
        marker_color=colors["Importada"],
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.2f} kWh<extra></extra>",
    )
    figure.add_bar(
        name="Autoconsumida",
        x=users["energia_autoconsumida_kWh"],
        y=cups,
        orientation="h",
        offsetgroup="autoconsumida_exportada",
        legendgroup="autoconsumida",
        marker_color=colors["Autoconsumida"],
        showlegend=False,
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.2f} kWh<extra></extra>",
    )
    figure.add_bar(
        name="Exportada",
        x=users["energia_exportada_balance_kWh"],
        y=cups,
        orientation="h",
        offsetgroup="autoconsumida_exportada",
        legendgroup="exportada",
        marker_color=colors["Exportada"],
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.2f} kWh<extra></extra>",
    )
    figure.update_layout(
        barmode="stack",
        height=max(
            _BALANCE_CHART_MIN_HEIGHT,
            _BALANCE_CHART_ROW_HEIGHT * len(users)
            + _BALANCE_CHART_VERTICAL_MARGIN,
        ),
        title="Balance energético por usuario",
        xaxis_title="Energía (kWh)",
        yaxis_title="Usuario",
        yaxis={
            "categoryorder": "array",
            "categoryarray": cups,
            "autorange": "reversed",
            "automargin": True,
        },
        legend_title_text="Magnitud",
        legend={"groupclick": "togglegroup"},
    )
    return figure


def build_user_energy_distribution_figures(
    data: pd.DataFrame,
) -> tuple[go.Figure | None, go.Figure | None]:
    """Build community pie charts for total consumption and renewable energy."""
    required_columns = {
        "cups",
        "energia_importada_kWh",
        "energia_autoconsumida_kWh",
        "energia_exportada_kWh",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(
            "Faltan columnas para la distribución energética por usuario: "
            + ", ".join(sorted(missing_columns))
            + "."
        )

    users = data.groupby("cups", as_index=False)[
        [
            "energia_importada_kWh",
            "energia_autoconsumida_kWh",
            "energia_exportada_kWh",
        ]
    ].sum()
    users = users.sort_values("cups", kind="stable").reset_index(drop=True)
    consumption_users = users.assign(
        _consumption=(
            users["energia_autoconsumida_kWh"]
            + users["energia_importada_kWh"]
        )
    ).sort_values("_consumption", ascending=False, kind="stable")
    consumption_users = consumption_users.reset_index(drop=True)
    renewable_users = consumption_users.assign(
        _renewable=(
            consumption_users["energia_autoconsumida_kWh"]
            + consumption_users["energia_exportada_kWh"]
        )
    )
    consumption_colors = [
        "#263238" if index % 2 == 0 else "#cfd8dc"
        for index in range(len(consumption_users))
    ]
    renewable_colors = [
        "#263238" if index % 2 == 0 else "#cfd8dc"
        for index in range(len(renewable_users))
    ]
    distributions = (
        (
            "Consumo por usuario",
            consumption_users,
            consumption_users["_consumption"],
            consumption_colors,
            "none",
            "clockwise",
        ),
        (
            "Energía renovable por usuario",
            renewable_users,
            renewable_users["_renewable"],
            renewable_colors,
            "none",
            "clockwise",
        ),
    )
    figures = []
    for title, plot_users, values, pie_colors, textinfo, direction in distributions:
        if (values < 0).any():
            raise ValueError(f"Hay valores negativos en «{title}».")
        total = values.sum()
        if total == 0:
            figures.append(None)
            continue

        figure = go.Figure(
            go.Pie(
                labels=plot_users["cups"],
                values=values,
                customdata=plot_users["cups"],
                marker={"colors": pie_colors},
                textinfo=textinfo,
                hovertemplate=(
                    "%{customdata}<br>%{percent}<br>%{value:.2f} kWh<extra></extra>"
                ),
                showlegend=False,
                sort=False,
                direction=direction,
            )
        )
        figure.update_layout(title=title)
        figures.append(figure)
    return figures[0], figures[1]


def calculate_community_renewable_percentage(data: pd.DataFrame) -> float | None:
    """Return community generation as a percentage of total consumption."""
    required_columns = {"energia_generada_kWh", "energia_consumida_kWh"}
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(
            "Faltan columnas para el porcentaje renovable comunitario: "
            + ", ".join(sorted(missing_columns))
            + "."
        )

    consumption = data["energia_consumida_kWh"].sum()
    if consumption == 0:
        return None
    return data["energia_generada_kWh"].sum() / consumption * 100


def build_user_renewable_percentage_figure(
    data: pd.DataFrame,
    community_reference_percentage: float | None = None,
) -> go.Figure:
    """Build a horizontal bar chart of renewable energy share per user."""
    renewable_data = build_user_renewable_percentage_data(
        data, community_reference_percentage
    )
    cups = renewable_data["CUPS"].tolist()
    percentages = renewable_data["Porcentaje de energía renovable"].tolist()
    bar_values = [0 if pd.isna(value) else value for value in percentages]
    labels = [
        "Sin consumo" if pd.isna(value) else f"{value:.1f}%".replace(".", ",")
        for value in percentages
    ]
    bar_colors = [
        _RENEWABLE_PERCENTAGE_ABOVE_100_COLOR
        if value > 100
        else (
            _RENEWABLE_PERCENTAGE_WITHIN_RANGE_COLOR
            if community_reference_percentage is None
            or community_reference_percentage <= value <= 100
            else _RENEWABLE_PERCENTAGE_BELOW_COMMUNITY_COLOR
        )
        for value in bar_values
    ]
    xaxis_max = max(
        100,
        max(bar_values, default=0),
        community_reference_percentage or 0,
    ) * 1.15
    figure = go.Figure(
        go.Bar(
            x=bar_values,
            y=cups,
            orientation="h",
            marker_color=bar_colors,
            text=labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>",
        )
    )
    if community_reference_percentage is not None:
        figure.add_vline(
            x=community_reference_percentage,
            line_color="#2e7d32",
            line_width=2,
            annotation_text=f"Comunidad ({community_reference_percentage:.1f}%)",
            annotation_position="top",
            annotation_font_color="#2e7d32",
        )
    figure.add_vline(
        x=100,
        line_color="#7b1fa2",
        line_width=2,
        annotation_text="100 %",
        annotation_position="top",
        annotation_font_color="#7b1fa2",
    )
    figure.update_layout(
        height=max(
            _RENEWABLE_PERCENTAGE_CHART_MIN_HEIGHT,
            _RENEWABLE_PERCENTAGE_CHART_ROW_HEIGHT * len(renewable_data)
            + _RENEWABLE_PERCENTAGE_CHART_VERTICAL_MARGIN,
        ),
        title="Porcentaje de energía renovable por usuario",
        xaxis_title="Porcentaje de energía renovable (%)",
        yaxis_title="Usuario",
        xaxis={"ticksuffix": "%", "range": [0, xaxis_max]},
        yaxis={
            "categoryorder": "array",
            "categoryarray": cups,
            "autorange": "reversed",
            "automargin": True,
            "showticklabels": False,
        },
        showlegend=False,
    )
    return figure


def build_user_renewable_percentage_data(
    data: pd.DataFrame,
    community_reference_percentage: float | None = None,
) -> pd.DataFrame:
    """Build per-CUPS renewable percentage data for the chart and CSV export."""
    required_columns = {
        "cups",
        "energia_importada_kWh",
        "energia_autoconsumida_kWh",
        "energia_exportada_kWh",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(
            "Faltan columnas para el porcentaje de energía renovable: "
            + ", ".join(sorted(missing_columns))
            + "."
        )

    users = data.groupby("cups", as_index=False)[
        [
            "energia_importada_kWh",
            "energia_autoconsumida_kWh",
            "energia_exportada_kWh",
        ]
    ].sum()
    users["consumo_total_kWh"] = (
        users["energia_autoconsumida_kWh"] + users["energia_importada_kWh"]
    )
    users["energia_renovable_kWh"] = (
        users["energia_autoconsumida_kWh"] + users["energia_exportada_kWh"]
    )
    users["porcentaje_renovable"] = pd.Series(
        pd.NA, index=users.index, dtype="Float64"
    )
    has_consumption = users["consumo_total_kWh"] != 0
    users.loc[has_consumption, "porcentaje_renovable"] = (
        users.loc[has_consumption, "energia_renovable_kWh"]
        / users.loc[has_consumption, "consumo_total_kWh"]
        * 100
    )
    users = users.sort_values(
        "consumo_total_kWh",
        ascending=False,
        kind="stable",
        na_position="last",
    )
    return pd.DataFrame(
        {
            "CUPS": users["cups"],
            "Generada [kWh]": users["energia_renovable_kWh"],
            "Consumida [kWh]": users["consumo_total_kWh"],
            "Porcentaje de energía renovable": users["porcentaje_renovable"],
            "Porcentaje comunitario de referencia": (
                community_reference_percentage
            ),
        }
    ).reset_index(drop=True)


def build_user_renewable_percentage_csv(
    data: pd.DataFrame,
    community_reference_percentage: float | None = None,
) -> str:
    """Serialize per-CUPS renewable data rounded to two decimal places."""
    return build_user_renewable_percentage_data(
        data, community_reference_percentage
    ).round(2).to_csv(index=False)
