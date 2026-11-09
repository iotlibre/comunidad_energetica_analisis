import configparser
import hmac
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config_datadis.ini"
AUTHENTICATED_SESSION_KEY = "dashboard_authenticated"


class DashboardAuthConfigError(Exception):
    """Raised when the dashboard authentication configuration is unavailable."""


def load_dashboard_credentials(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> tuple[str, str]:
    config = configparser.ConfigParser(interpolation=None)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config.read_file(config_file)
        username = config["api_auth"]["username"].strip()
        password = config["api_auth"]["password"].strip()
    except (OSError, UnicodeError, configparser.Error, KeyError) as error:
        raise DashboardAuthConfigError(
            "La configuración de acceso no está disponible o está incompleta."
        ) from error

    if not username or not password:
        raise DashboardAuthConfigError(
            "La configuración de acceso no está disponible o está incompleta."
        )
    return username, password


def credentials_match(
    username: str,
    password: str,
    expected_username: str,
    expected_password: str,
) -> bool:
    username_matches = hmac.compare_digest(username, expected_username)
    password_matches = hmac.compare_digest(password, expected_password)
    return username_matches & password_matches


def require_dashboard_login() -> None:
    import streamlit as st

    try:
        expected_username, expected_password = load_dashboard_credentials()
    except DashboardAuthConfigError:
        st.error(
            "No se puede acceder al dashboard. Comprueba que config_datadis.ini "
            "exista y contenga [api_auth], username y password."
        )
        st.stop()
        return

    if st.session_state.get(AUTHENTICATED_SESSION_KEY, False):
        if st.sidebar.button("Cerrar sesión"):
            st.session_state.pop(AUTHENTICATED_SESSION_KEY, None)
            st.rerun()
        return

    st.title("Acceso al dashboard")
    with st.form("dashboard_login"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión")

    if submitted:
        if credentials_match(
            username,
            password,
            expected_username,
            expected_password,
        ):
            st.session_state[AUTHENTICATED_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

    st.stop()
