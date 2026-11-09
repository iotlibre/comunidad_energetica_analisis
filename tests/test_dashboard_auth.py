import tempfile
import unittest
from pathlib import Path

from dashboard.auth import (
    DashboardAuthConfigError,
    credentials_match,
    load_dashboard_credentials,
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


if __name__ == "__main__":
    unittest.main()
