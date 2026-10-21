import streamlit as st
from pathlib import Path
import sys

import pandas as pd

dashboard_dir = Path(__file__).resolve().parents[1]
if str(dashboard_dir) not in sys.path:
	sys.path.insert(0, str(dashboard_dir))

from utils.consumption_chart import (
	build_consumption_figure,
	find_consumption_json_files,
	load_consumption_data,
)
from utils.autoconsumption_chart import find_autoconsumption_files

st.set_page_config(page_title="Datos disponibles", layout="wide")
st.title("Datos disponibles")
st.header("Consumo horario")

responses_dir = dashboard_dir.parent / "responses"
if not responses_dir.is_dir():
	st.warning(f"No se encontró el directorio: {responses_dir}")
else:
	json_files = find_consumption_json_files(responses_dir)
	st.write(f"Ficheros JSON de consumo encontrados: {len(json_files)}")
	if not json_files:
		st.warning("No se encontraron JSON de consumo en responses/.")
	else:
		selected_json_path = st.selectbox(
			"Selecciona un fichero JSON",
			json_files,
			format_func=lambda path: path.name,
		)
		try:
			consumption_data = load_consumption_data(selected_json_path)
			consumption_figure = build_consumption_figure(
				consumption_data,
				f"Consumo horario: {selected_json_path.name}",
			)
		except (OSError, ValueError, TypeError) as error:
			st.error(f"No se pudo preparar la gráfica: {error}")
		else:
			st.write(f"Registros representados: {len(consumption_data)}")
			st.plotly_chart(consumption_figure, use_container_width=True)

st.divider()
st.header("Energía autoconsumida")
st.caption(
	"Formato de archivo: "
	"energia_autoconsumida_<fecha_inicio>_<fecha_final>.csv "
	"(fechas con formato YYYY_MM)."
)

autoconsumption_files = find_autoconsumption_files(responses_dir)
st.write(f"Ficheros de autoconsumo encontrados: {len(autoconsumption_files)}")
if not autoconsumption_files:
	st.warning("No se encontraron archivos de energía autoconsumida en responses/.")
else:
	selected_autoconsumption_path = st.selectbox(
		"Selecciona un fichero de energía autoconsumida",
		autoconsumption_files,
		format_func=lambda path: path.name,
	)
	try:
		autoconsumption_table = pd.read_csv(selected_autoconsumption_path)
	except (OSError, ValueError) as error:
		st.error(f"No se pudo leer el fichero seleccionado: {error}")
	else:
		st.dataframe(autoconsumption_table, hide_index=True, width="stretch")