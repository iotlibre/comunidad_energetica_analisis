import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dashboard.auth import (
    DashboardAuthConfigError,
    credentials_match,
    create_dashboard_session_token,
    is_dashboard_session_valid,
    load_dashboard_credentials,
    load_dashboard_session_settings,
    require_dashboard_login,
)


class DashboardAuthTests(unittest.TestCase):
    def test_loads_credentials_from_api_auth_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config_datadis.ini"
            config_path.write_text(
                "[api_auth]\nusername = dashboard-user\npassword = test-password\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_dashboard_credentials(config_path),
                ("dashboard-user", "test-password"),
            )

    def test_rejects_wrong_username_or_password(self):
        self.assertTrue(
            credentials_match(
                "dashboard-user",
                "test-password",
                "dashboard-user",
                "test-password",
            )
        )
        self.assertFalse(
            credentials_match(
                "wrong-user",
                "test-password",
                "dashboard-user",
                "test-password",
            )
        )
        self.assertFalse(
            credentials_match(
                "dashboard-user",
                "wrong-password",
                "dashboard-user",
                "test-password",
            )
        )

    def test_rejects_missing_or_incomplete_config_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config_datadis.ini"
            cases = (
                None,
                "[other]\nusername = hidden-user\npassword = hidden-password\n",
                "[api_auth]\nusername = hidden-user\n",
                "[api_auth]\nusername = \npassword = hidden-password\n",
            )
            for contents in cases:
                with self.subTest(contents=contents):
                    if contents is None:
                        config_path.unlink(missing_ok=True)
                    else:
                        config_path.write_text(contents, encoding="utf-8")
                    with self.assertRaises(DashboardAuthConfigError) as error:
                        load_dashboard_credentials(config_path)
                    self.assertNotIn("hidden-user", str(error.exception))
                    self.assertNotIn("hidden-password", str(error.exception))

    def test_rejects_malformed_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config_datadis.ini"
            config_path.write_text("[api_auth\npassword = secret\n", encoding="utf-8")

            with self.assertRaises(DashboardAuthConfigError):
                load_dashboard_credentials(config_path)

    def test_session_token_is_signed_and_does_not_contain_password(self):
        token = create_dashboard_session_token(
            "dashboard-user",
            "test-password",
            "a" * 32,
        )

        self.assertNotIn("test-password", token)
        self.assertTrue(
            is_dashboard_session_valid(
                token,
                "dashboard-user",
                "test-password",
                "a" * 32,
                3600,
            )
        )
        self.assertFalse(
            is_dashboard_session_valid(
                token + "tampered",
                "dashboard-user",
                "test-password",
                "a" * 32,
                3600,
            )
        )

    def test_session_expires_and_is_invalidated_when_credentials_change(self):
        with patch("itsdangerous.timed.time.time", return_value=1_000):
            token = create_dashboard_session_token(
                "dashboard-user",
                "test-password",
                "a" * 32,
            )

        with patch("itsdangerous.timed.time.time", return_value=1_002):
            self.assertFalse(
                is_dashboard_session_valid(
                    token,
                    "dashboard-user",
                    "test-password",
                    "a" * 32,
                    1,
                )
            )
            self.assertFalse(
                is_dashboard_session_valid(
                    token,
                    "dashboard-user",
                    "changed-password",
                    "a" * 32,
                    3600,
                )
            )

    def test_session_settings_require_secret_and_valid_expiration(self):
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_SESSION_SECRET": "s" * 32,
                "DASHBOARD_SESSION_TTL_HOURS": "6",
                "DASHBOARD_COOKIE_SECURE": "true",
            },
            clear=True,
        ):
            self.assertEqual(
                load_dashboard_session_settings(),
                ("s" * 32, 21600, True),
            )

        for secret, ttl, secure in (
            ("short", "12", "false"),
            ("s" * 32, "0", "false"),
            ("s" * 32, "invalid", "false"),
            ("s" * 32, "12", "maybe"),
        ):
            with self.subTest(secret=secret, ttl=ttl, secure=secure):
                with patch.dict(
                    "os.environ",
                    {
                        "DASHBOARD_SESSION_SECRET": secret,
                        "DASHBOARD_SESSION_TTL_HOURS": ttl,
                        "DASHBOARD_COOKIE_SECURE": secure,
                    },
                    clear=True,
                ):
                    with self.assertRaises(DashboardAuthConfigError):
                        load_dashboard_session_settings()

    def test_creates_a_persistent_private_secret_when_environment_is_unset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir) / "config"
            environment = {
                "XDG_CONFIG_HOME": str(config_home),
                "DASHBOARD_SESSION_TTL_HOURS": "12",
                "DASHBOARD_COOKIE_SECURE": "false",
            }
            with patch.dict("os.environ", environment, clear=True):
                first_settings = load_dashboard_session_settings()
                secret_path = (
                    config_home
                    / "comunidad_energetica_analisis"
                    / "dashboard_session.key"
                )
                second_settings = load_dashboard_session_settings()

            self.assertEqual(first_settings, second_settings)
            self.assertGreaterEqual(len(first_settings[0]), 32)
            self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(secret_path.parent.stat().st_mode & 0o777, 0o700)

    def test_login_persists_session_and_logout_deletes_cookie(self):
        cookie_store = {}
        reader_cache = {}
        set_calls = []
        delete_calls = []

        class FakeCookieManager:
            def __init__(self, key):
                self.key = key
                self.cookies = dict(
                    reader_cache.setdefault(key, dict(cookie_store))
                )

            def get(self, cookie):
                return self.cookies.get(cookie)

            def set(self, cookie, val, **options):
                cookie_store[cookie] = val
                self.cookies[cookie] = val
                set_calls.append(options)

            def delete(self, cookie, key):
                cookie_store.pop(cookie, None)
                self.cookies.pop(cookie, None)
                delete_calls.append((cookie, key))

        class StopScript(Exception):
            pass

        def fake_streamlit(session_state, submitted=False, logout_clicked=False):
            streamlit = types.ModuleType("streamlit")
            streamlit.session_state = session_state
            streamlit.sidebar = SimpleNamespace(
                button=Mock(return_value=logout_clicked)
            )
            streamlit.form = Mock(return_value=nullcontext())
            streamlit.text_input = Mock(
                side_effect=("dashboard-user", "test-password")
            )
            streamlit.form_submit_button = Mock(return_value=submitted)
            streamlit.title = Mock()
            streamlit.success = Mock()
            streamlit.error = Mock()
            streamlit.stop = Mock(side_effect=StopScript)
            streamlit.rerun = Mock(side_effect=StopScript)
            return streamlit

        extra_components = types.ModuleType("extra_streamlit_components")
        extra_components.CookieManager = FakeCookieManager
        credentials = ("dashboard-user", "test-password")
        session_settings = ("s" * 32, 3600, True)
        session_state = {}

        with (
            patch("dashboard.auth.load_dashboard_credentials", return_value=credentials),
            patch(
                "dashboard.auth.load_dashboard_session_settings",
                return_value=session_settings,
            ),
            patch.dict(
                sys.modules,
                {"extra_streamlit_components": extra_components},
            ),
        ):
            login_streamlit = fake_streamlit(session_state, submitted=True)
            with patch.dict(sys.modules, {"streamlit": login_streamlit}):
                with self.assertRaises(StopScript):
                    require_dashboard_login()
            login_streamlit.rerun.assert_not_called()
            login_streamlit.success.assert_called_once_with(
                "Credenciales correctas. Accediendo al dashboard..."
            )

            token = cookie_store["dashboard_session"]
            self.assertTrue(
                is_dashboard_session_valid(
                    token,
                    credentials[0],
                    credentials[1],
                    session_settings[0],
                    session_settings[1],
                )
            )
            self.assertEqual(set_calls[0]["max_age"], 3600)
            self.assertTrue(set_calls[0]["secure"])
            self.assertEqual(set_calls[0]["same_site"], "strict")

            refresh_streamlit = fake_streamlit(session_state)
            with patch.dict(sys.modules, {"streamlit": refresh_streamlit}):
                with self.assertRaises(StopScript):
                    require_dashboard_login()
            self.assertEqual(session_state["dashboard_cookie_reader_version"], 1)

            authenticated_streamlit = fake_streamlit(session_state)
            with patch.dict(sys.modules, {"streamlit": authenticated_streamlit}):
                require_dashboard_login()
            authenticated_streamlit.form.assert_not_called()

            logout_streamlit = fake_streamlit(session_state, logout_clicked=True)
            with patch.dict(sys.modules, {"streamlit": logout_streamlit}):
                with self.assertRaises(StopScript):
                    require_dashboard_login()
            self.assertNotIn("dashboard_session", cookie_store)
            self.assertEqual(delete_calls[0][0], "dashboard_session")
            self.assertTrue(delete_calls[0][1].startswith("delete_session_"))

            logout_refresh_streamlit = fake_streamlit(session_state)
            with patch.dict(sys.modules, {"streamlit": logout_refresh_streamlit}):
                with self.assertRaises(StopScript):
                    require_dashboard_login()
            self.assertEqual(session_state["dashboard_cookie_reader_version"], 2)

            logged_out_streamlit = fake_streamlit(session_state)
            with patch.dict(sys.modules, {"streamlit": logged_out_streamlit}):
                with self.assertRaises(StopScript):
                    require_dashboard_login()
            logged_out_streamlit.form.assert_called_once()


if __name__ == "__main__":
    unittest.main()
