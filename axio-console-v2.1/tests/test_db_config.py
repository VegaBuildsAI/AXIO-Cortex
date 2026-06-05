import importlib
import os
import unittest
from unittest.mock import patch


class DatabaseConfigTests(unittest.TestCase):
    def reload_config(self, env):
        with patch.dict(os.environ, env, clear=False):
            import core.config as config
            return importlib.reload(config)

    def test_defaults_to_json_memory_backend(self):
        config = self.reload_config({"AXIO_MEMORY_BACKEND": ""})
        self.assertEqual(config.AXIO_MEMORY_BACKEND, "json")

    def test_reads_postgres_database_settings(self):
        config = self.reload_config({
            "AXIO_MEMORY_BACKEND": "postgres",
            "AXIO_DB_HOST": "127.0.0.1",
            "AXIO_DB_PORT": "5544",
            "AXIO_DB_NAME": "axio_test",
            "AXIO_DB_USER": "axio_user",
            "AXIO_DB_PASSWORD": "secret",
        })

        self.assertEqual(config.AXIO_MEMORY_BACKEND, "postgres")
        self.assertEqual(config.AXIO_DB_HOST, "127.0.0.1")
        self.assertEqual(config.AXIO_DB_PORT, 5544)
        self.assertEqual(config.AXIO_DB_NAME, "axio_test")
        self.assertEqual(config.AXIO_DB_USER, "axio_user")
        self.assertEqual(config.AXIO_DB_PASSWORD, "secret")

    def test_builds_psycopg_connection_string(self):
        with patch.dict(os.environ, {
            "AXIO_DB_HOST": "127.0.0.1",
            "AXIO_DB_PORT": "5432",
            "AXIO_DB_NAME": "axio_cortex",
            "AXIO_DB_USER": "axio",
            "AXIO_DB_PASSWORD": "pw",
        }, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.db as db
            importlib.reload(db)

            dsn = db.get_database_dsn()

        self.assertIn("host=127.0.0.1", dsn)
        self.assertIn("port=5432", dsn)
        self.assertIn("dbname=axio_cortex", dsn)
        self.assertIn("user=axio", dsn)
        self.assertIn("password=pw", dsn)


if __name__ == "__main__":
    unittest.main()
