import streamlit as st
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent.parent
responses_dir = BASE / "responses"

st.set_page_config(page_title="Dashboard Energético", layout="wide")
st.title("Dashboard de perfiles energéticos")

if responses_dir.exists():
    files = sorted(p.name for p in responses_dir.iterdir() if p.is_file())
    st.success(f"Directorio detectado: {responses_dir}")
    st.write(f"Ficheros encontrados: {len(files)}")
    selected = st.selectbox("Selecciona un fichero", files if files else ["No hay ficheros"])
    st.write("Archivo seleccionado:", selected)

    selected_path = responses_dir / selected
    if selected_path.suffix.lower() == ".json" and selected_path.is_file():
        st.write(f"Tamaño: {selected_path.stat().st_size} bytes")
        try:
            data = json.loads(selected_path.read_text(encoding="utf-8"))
            st.write(
                "Número de registros:",
                len(data) if isinstance(data, (list, dict)) else "No aplicable",
            )
            st.json(data)
        except (OSError, json.JSONDecodeError) as error:
            st.error(f"No se pudo leer el JSON: {error}")
else:
    st.warning(f"No se encontró el directorio: {responses_dir}")
