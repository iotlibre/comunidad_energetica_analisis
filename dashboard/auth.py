import configparser
import hashlib
import hmac
import os
import secrets
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from itsdangerous import BadSignature, URLSafeTimedSerializer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config_datadis.ini"
SESSION_COOKIE_NAME = "dashboard_session"
DEFAULT_SESSION_TTL_HOURS = 12
MIN_SESSION_SECRET_LENGTH = 32
SESSION_SECRET_DIRECTORY = "comunidad_energetica_analisis"
SESSION_SECRET_FILENAME = "dashboard_session.key"
COOKIE_READER_VERSION_KEY = "dashboard_cookie_reader_version"
COOKIE_REFRESH_PENDING_KEY = "dashboard_cookie_refresh_pending"


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


def _load_or_create_session_secret() -> str:
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    )
    config_directory = config_home / SESSION_SECRET_DIRECTORY
    secret_path = config_directory / SESSION_SECRET_FILENAME

    try:
        config_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        config_directory.chmod(0o700)

        try:
            descriptor = os.open(
                secret_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            descriptor = os.open(
                secret_path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            with os.fdopen(descriptor, encoding="utf-8") as secret_file:
                if not stat.S_ISREG(os.fstat(secret_file.fileno()).st_mode):
                    raise DashboardAuthConfigError(
                        "El archivo de clave de sesión no es un archivo regular."
                    )
                os.fchmod(secret_file.fileno(), 0o600)
                secret = secret_file.read().strip()
        else:
            secret = secrets.token_urlsafe(32)
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
                secret_file.write(secret)
                secret_file.flush()
                os.fsync(secret_file.fileno())
    except DashboardAuthConfigError:
        raise
    except OSError as error:
        raise DashboardAuthConfigError(
            "No se pudo leer o crear la clave persistente de sesión."
        ) from error

    if len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise DashboardAuthConfigError(
            "La clave persistente de sesión está vacía o es demasiado corta."
        )
    return secret


def load_dashboard_session_settings() -> tuple[str, int, bool]:
    secret = os.environ.get("DASHBOARD_SESSION_SECRET")
    if secret is None:
        secret = _load_or_create_session_secret()
    else:
        secret = secret.strip()
    if len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise DashboardAuthConfigError(
            "DASHBOARD_SESSION_SECRET debe contener al menos 32 caracteres."
        )

    raw_ttl = os.environ.get(
        "DASHBOARD_SESSION_TTL_HOURS",
        str(DEFAULT_SESSION_TTL_HOURS),
    )
    try:
        ttl_hours = int(raw_ttl)
    except ValueError as error:
        raise DashboardAuthConfigError(
            "DASHBOARD_SESSION_TTL_HOURS debe ser un entero positivo."
        ) from error
    if ttl_hours <= 0:
        raise DashboardAuthConfigError(
            "DASHBOARD_SESSION_TTL_HOURS debe ser un entero positivo."
        )

    raw_secure = os.environ.get("DASHBOARD_COOKIE_SECURE", "false").casefold()
    if raw_secure not in {"true", "false"}:
        raise DashboardAuthConfigError(
            "DASHBOARD_COOKIE_SECURE debe ser true o false."
        )
    return secret, ttl_hours * 60 * 60, raw_secure == "true"


def _session_serializer(
    session_secret: str,
    username: str,
    password: str,
) -> URLSafeTimedSerializer:
    credentials = f"{username}\0{password}".encode("utf-8")
    signing_key = hmac.new(
        session_secret.encode("utf-8"),
        credentials,
        hashlib.sha256,
    ).digest()
    return URLSafeTimedSerializer(signing_key, salt="dashboard-auth")


def create_dashboard_session_token(
    username: str,
    password: str,
    session_secret: str,
) -> str:
    serializer = _session_serializer(session_secret, username, password)
    return serializer.dumps({"username": username})


def is_dashboard_session_valid(
    token: object,
    expected_username: str,
    expected_password: str,
    session_secret: str,
    max_age_seconds: int,
) -> bool:
    if not isinstance(token, str) or not token:
        return False

    serializer = _session_serializer(
        session_secret,
        expected_username,
        expected_password,
    )
    try:
        payload = serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return False

    token_username = payload.get("username") if isinstance(payload, dict) else None
    return isinstance(token_username, str) and hmac.compare_digest(
        token_username,
        expected_username,
    )


def require_dashboard_login() -> None:
    import streamlit as st

    try:
        expected_username, expected_password = load_dashboard_credentials()
    except DashboardAuthConfigError as error:
        st.error(f"No se puede acceder al dashboard: {error}")
        st.stop()
        return

    try:
        session_secret, max_age_seconds, cookie_secure = (
            load_dashboard_session_settings()
        )
    except DashboardAuthConfigError as error:
        st.error(f"No se puede inicializar la sesión del dashboard: {error}")
        st.stop()
        return

    try:
        import extra_streamlit_components as stx
    except ImportError:
        st.error(
            "Falta extra-streamlit-components. Instala las dependencias del "
            "dashboard desde requirements/requirements-dash-lock.txt."
        )
        st.stop()
        return

    reader_version = st.session_state.get(COOKIE_READER_VERSION_KEY, 0)
    cookie_manager = stx.CookieManager(
        key=f"dashboard_auth_cookie_manager_{reader_version}"
    )
    if st.session_state.pop(COOKIE_REFRESH_PENDING_KEY, False):
        st.session_state[COOKIE_READER_VERSION_KEY] = reader_version + 1
        st.rerun()

    token = cookie_manager.get(SESSION_COOKIE_NAME)
    if is_dashboard_session_valid(
        token,
        expected_username,
        expected_password,
        session_secret,
        max_age_seconds,
    ):
        if st.sidebar.button("Cerrar sesión"):
            cookie_manager.delete(
                SESSION_COOKIE_NAME,
                key=f"delete_session_{uuid4().hex}",
            )
            st.session_state[COOKIE_REFRESH_PENDING_KEY] = True
            st.stop()
        return

    if token:
        cookie_manager.delete(
            SESSION_COOKIE_NAME,
            key=f"delete_session_{uuid4().hex}",
        )
        st.session_state[COOKIE_REFRESH_PENDING_KEY] = True
        st.stop()

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
            st.success("Credenciales correctas. Accediendo al dashboard...")
            now = datetime.now(timezone.utc)
            cookie_manager.set(
                cookie=SESSION_COOKIE_NAME,
                val=create_dashboard_session_token(
                    expected_username,
                    expected_password,
                    session_secret,
                ),
                key=f"set_session_{uuid4().hex}",
                path="/",
                expires_at=now + timedelta(seconds=max_age_seconds),
                max_age=max_age_seconds,
                secure=cookie_secure,
                same_site="strict",
            )
            st.session_state[COOKIE_REFRESH_PENDING_KEY] = True
            st.stop()
        else:
            st.error("Usuario o contraseña incorrectos.")

    st.stop()
