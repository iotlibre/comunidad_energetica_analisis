import streamlit as st
from pathlib import Path
import sys

dashboard_dir = Path(__file__).resolve().parents[1]
if str(dashboard_dir) not in sys.path:
    sys.path.insert(0, str(dashboard_dir))

from auth import require_dashboard_login

st.set_page_config(page_title="Autoconsumo", layout="wide")
require_dashboard_login()
st.title("Autoconsumo")
st.info("Esta página mostrará generación, consumo, importación y exportación.")