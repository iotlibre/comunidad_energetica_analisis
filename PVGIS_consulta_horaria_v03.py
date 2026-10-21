import requests
import json
import os
from typing import Dict, List, Optional

DEFAULT_OUTPUT_FILENAME = "pvgis_indextime_spain.txt"
DEFAULT_OUTPUT_DIR = "responses"

# Valores por defecto embebidos
DEFAULT_PARAMS = {
    "lat": 43.38,
    "lon": -2.58,
    "startyear": 2023,
    "endyear": 2023,
    "peakpower": 100,
    "angle": 21,
    "azimuth": 0,
    "loss": 14,
}


def cargar_parametros_pvgis() -> Dict[str, object]:
    """Devuelve los parámetros por defecto de PVGIS."""
    return DEFAULT_PARAMS.copy()


def construir_url_pvgis(params: Dict[str, object]) -> str:
    """Genera la URL para la consulta a la API de PVGIS."""
    return (
        "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
        f"?lat={params['lat']}&lon={params['lon']}"
        f"&startyear={params['startyear']}&endyear={params['endyear']}"
        "&radiation=2.5"
        "&pvcalculation=1"
        f"&peakpower={params['peakpower']}"
        f"&angle={params['angle']}"
        f"&aspect={params['azimuth']}"
        f"&loss={params['loss']}"
        "&outputformat=json"
        "&browser=0"
    )


def ajustar_horario_spain(P_utc: List[float]) -> List[float]:
    """Ajusta el horario UTC a horario de España para el año 2023."""
    n = len(P_utc)
    P_spain = [0.0] * n

    for i in range(min(2018, n)):
        if i - 1 >= 0:
            P_spain[i] = P_utc[i - 1]
        else:
            P_spain[i] = 0.0

    for i in range(2018, min(7225, n)):
        if i - 2 >= 0:
            P_spain[i] = P_utc[i - 2]
        else:
            P_spain[i] = 0.0

    for i in range(7225, n):
        if i - 1 >= 0:
            P_spain[i] = P_utc[i - 1]
        else:
            P_spain[i] = 0.0

    return P_spain


def guardar_txt_pvgis_spain(P_spain: List[float], output_path: Optional[str] = None) -> str:
    """Guarda el resultado ajustado en el fichero de salida definitivo en kWh/hora."""
    if output_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, DEFAULT_OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, DEFAULT_OUTPUT_FILENAME)
    else:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

    # PVGIS devuelve valores en Wh para la hora. Para que sean comparables con
    # consumptionKWh del JSON, los convertimos a kWh/hora dividiendo por 1000.
    pvgis_kwh = [value / 1000.0 for value in P_spain]

    with open(output_path, "w", encoding="utf-8") as f:
        for i, P in enumerate(pvgis_kwh, start=1):
            index = f"{i:04d}"
            f.write(f"{index};{P}\n")

    return output_path


def generar_pvgis_horario(parametros: Optional[Dict[str, object]] = None, output_path: Optional[str] = None) -> Dict[str, object]:
    """Realiza la consulta a PVGIS y devuelve el resultado en JSON."""
    parametros_default = cargar_parametros_pvgis()
    if parametros is None:
        parametros = parametros_default
    else:
        parametros = {**parametros_default, **parametros}

    url = construir_url_pvgis(parametros)
    response = requests.get(url)

    if response.status_code != 200:
        raise RuntimeError(f"Error PVGIS {response.status_code}: {response.text}")

    data = response.json()
    hourly = data["outputs"]["hourly"]
    P_utc = [row["P"] for row in hourly]
    P_spain = ajustar_horario_spain(P_utc)
    resultado_path = guardar_txt_pvgis_spain(P_spain, output_path)

    return {
        "status": "ok",
        "output_file": resultado_path,
        "hours": len(P_spain),
        "parameters": parametros,
        "url": url,
    }


if __name__ == "__main__":
    resultado = generar_pvgis_horario()
    print(f"TXT generado en: {resultado['output_file']}")
