"""Deployment profile regression checks; no database or real secrets required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
INSPECT_SETTINGS = """
import json
import django
django.setup()
from django.conf import settings
db = settings.DATABASES['default']
print(json.dumps({
    'engine': db['ENGINE'], 'name': db['NAME'], 'host': db['HOST'], 'port': db['PORT'],
    'aliases': list(settings.DATABASES), 'debug': settings.DEBUG,
    'extra_params': db.get('OPTIONS', {}).get('extra_params'),
    'timeout': db.get('OPTIONS', {}).get('connection_timeout'),
    'hosts': settings.ALLOWED_HOSTS, 'origins': settings.CSRF_TRUSTED_ORIGINS,
    'public_url': settings.PUBLIC_BASE_URL,
    'static_backend': settings.STORAGES['staticfiles']['BACKEND'],
}))
"""


class DeploymentConfigTests(unittest.TestCase):
    def inspect(self, overrides=None):
        # Exclude inherited application credentials and disable both local .env files.
        keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA"}
        env = {key: value for key, value in os.environ.items() if key.upper() in keep}
        env.update({
            "PYTHONUTF8": "1", "PYTHON_DOTENV_DISABLED": "1", "RENDER": "true",
            "SECRET_KEY": "deployment-test-key-only-never-use-in-production",
            "DEBUG": "False", "DJANGO_SETTINGS_MODULE": "QLNH.sqlserver_settings",
            "SQLSERVER_HOST": "sql5106.site4now.net", "SQLSERVER_DB": "db_ad182b_comque",
            "SQLSERVER_USER": "test-user", "SQLSERVER_PASSWORD": "dummy-password",
            "RENDER_EXTERNAL_HOSTNAME": "qlnh-web.onrender.com",
            "RENDER_EXTERNAL_URL": "https://qlnh-web.onrender.com",
        })
        for key, value in (overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [sys.executable, "-c", INSPECT_SETTINGS], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def settings(self, overrides=None):
        result = self.inspect(overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_render_uses_sqlserver_without_any_postgres_variables(self):
        data = self.settings()
        self.assertEqual(data["engine"], "core.db.backends.sqlserver")
        self.assertEqual(data["name"], "db_ad182b_comque")
        self.assertEqual(data["host"], "sql5106.site4now.net")
        self.assertEqual(data["port"], "1433")
        self.assertEqual(data["aliases"], ["default"])
        self.assertEqual(data["extra_params"], "Encrypt=yes;TrustServerCertificate=no")
        self.assertEqual(data["timeout"], 15)

    def test_stale_database_url_does_not_select_postgres_on_render(self):
        data = self.settings({"DATABASE_URL": "postgresql://unused:unused@localhost/old_database"})
        self.assertEqual(data["engine"], "core.db.backends.sqlserver")
        self.assertEqual(data["aliases"], ["default"])

    def test_missing_render_credentials_fail_before_connecting(self):
        for key in ("SQLSERVER_HOST", "SQLSERVER_DB", "SQLSERVER_USER", "SQLSERVER_PASSWORD"):
            with self.subTest(key=key):
                result = self.inspect({key: None})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)
                self.assertNotIn("dummy-password", result.stderr)

    def test_render_https_and_static_configuration(self):
        data = self.settings()
        self.assertFalse(data["debug"])
        self.assertIn("qlnh-web.onrender.com", data["hosts"])
        self.assertIn("https://qlnh-web.onrender.com", data["origins"])
        self.assertEqual(data["public_url"], "https://qlnh-web.onrender.com")
        self.assertEqual(data["static_backend"], "whitenoise.storage.CompressedManifestStaticFilesStorage")

    def test_postgres_profile_remains_available(self):
        data = self.settings({
            "DJANGO_SETTINGS_MODULE": "QLNH.settings",
            "DATABASE_URL": "postgresql://unused:unused@localhost/original_database",
        })
        self.assertEqual(data["engine"], "django.db.backends.postgresql")
        self.assertEqual(data["name"], "original_database")

    def test_local_postgres_copy_source_is_optional(self):
        data = self.settings({"RENDER": None})
        self.assertEqual(data["aliases"], ["default"])
        data = self.settings({
            "RENDER": None, "DATABASE_URL": "postgresql://unused:unused@localhost/copy_source",
        })
        self.assertEqual(data["aliases"], ["default", "postgres_source"])

    def test_sqlserver_test_profile_excludes_postgres_copy_source(self):
        data = self.settings({
            "RENDER": None,
            "DJANGO_SETTINGS_MODULE": "QLNH.sqlserver_test_settings",
            "DATABASE_URL": "postgresql://unused:unused@localhost/must_not_create",
        })
        self.assertEqual(data["aliases"], ["default"])
        self.assertEqual(data["engine"], "core.db.backends.sqlserver")

    def test_sqlserver_test_profile_needs_no_postgres_credentials(self):
        data = self.settings({"DJANGO_SETTINGS_MODULE": "QLNH.sqlserver_test_settings"})
        self.assertEqual(data["aliases"], ["default"])
        self.assertEqual(data["engine"], "core.db.backends.sqlserver")



if __name__ == "__main__":
    unittest.main()
