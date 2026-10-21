"""Focused safety checks for operational commands; no external services required."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import database_backup
import release
from sqlalchemy.engine import make_url


class BackupSafetyTests(unittest.TestCase):
    def test_required_channel_binding_reaches_libpq(self):
        url = make_url(
            "postgresql+psycopg://test:private@localhost/test_db?channel_binding=require"
        )
        with patch.dict(os.environ, {"PGCHANNELBINDING": "disable"}):
            env = database_backup.pg_environment(url)
        self.assertEqual(env.get("PGCHANNELBINDING"), "require")
        self.assertNotIn("PGCHANNEL_BINDING", env)

    def test_password_is_an_environment_value(self):
        url = make_url("postgresql+psycopg://test:private-value@localhost/test_db?sslmode=require")
        with patch.dict(os.environ, {"PGSERVICE": "wrong-host", "PGHOST": "wrong-host"}):
            env = database_backup.pg_environment(url)
        self.assertEqual(env["PGHOST"], "localhost")
        self.assertEqual(env["PGPASSWORD"], "private-value")
        self.assertEqual(env["PGSSLMODE"], "require")
        self.assertNotIn("PGSERVICE", env)

    def test_same_database_restore_is_rejected_before_connection(self):
        url = "postgresql+psycopg://test:private@localhost/same_db"
        args = argparse.Namespace(operation="restore", file=Path("missing.dump"), pg_bin=None)
        with patch.dict(os.environ, {"PETSHOP_DATABASE_URL": url,
                                     "PETSHOP_RESTORE_DATABASE_URL": url}):
            with patch.object(database_backup, "assert_empty") as check:
                with self.assertRaisesRegex(ValueError, "differ"):
                    database_backup.run(args)
        check.assert_not_called()

    def test_existing_backup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.dump"
            path.write_bytes(b"keep-existing-backup")
            args = argparse.Namespace(operation="backup", file=path, pg_bin=None)
            with patch.dict(os.environ, {"PETSHOP_DATABASE_URL":
                                        "postgresql+psycopg://test:private@localhost/test_db"}):
                with patch.object(database_backup, "executable", return_value="pg_dump"):
                    with self.assertRaises(FileExistsError):
                        database_backup.run(args)
            self.assertEqual(path.read_bytes(), b"keep-existing-backup")


class DependencyLockTests(unittest.TestCase):
    def test_runtime_versions_match_tested_development_versions(self):
        root = Path(__file__).resolve().parents[1]

        def versions(filename):
            lines = (root / filename).read_text(encoding="utf-8").splitlines()
            pins = (re.match(r"^([\w.-]+)==([^;\s\\]+)", line) for line in lines)
            return {pin[1].lower().replace("_", "-"): pin[2] for pin in pins if pin}

        runtime = versions("requirements-lock.txt")
        development = versions("requirements-dev-lock.txt")
        self.assertTrue(runtime)
        for package, version in runtime.items():
            with self.subTest(package=package):
                self.assertEqual(development.get(package), version)


class ReleaseSafetyTests(unittest.TestCase):
    def test_failed_readiness_restores_the_previous_image(self):
        calls = []

        def fake(args, env):
            calls.append((args, env.copy()))
            if args[1:3] == ["compose", "ps"]:
                return subprocess.CompletedProcess(args, 0, "old-container\n", "")
            if args[1] == "inspect":
                return subprocess.CompletedProcess(args, 0, "sha256:previous\n", "")
            return subprocess.CompletedProcess(args, 1 if len(calls) == 3 else 0, "", "")

        with (patch.object(release, "command", side_effect=fake),
              patch("sys.stderr", new_callable=io.StringIO) as error):
            self.assertEqual(release.deploy("candidate:release", 10), 1)
        self.assertEqual(calls[2][1]["PETSHOP_IMAGE"], "candidate:release")
        self.assertEqual(calls[3][1]["PETSHOP_IMAGE"], "sha256:previous")
        self.assertIn("--wait", calls[2][0])
        self.assertIn("--no-deps", calls[3][0])
        event = json.loads(error.getvalue())
        self.assertTrue(event["rollback_succeeded"])
        self.assertEqual(event["previous_image"], "sha256:previous")
        self.assertIn("Set PETSHOP_IMAGE in .env to previous_image", event["manual_action"])
        self.assertIn("before any subsequent docker compose up", event["manual_action"])

    def test_initial_deployment_is_not_modified(self):
        with patch.object(release, "command", return_value=
                          subprocess.CompletedProcess([], 0, "", "")) as call:
            with self.assertRaisesRegex(ValueError, "existing"):
                release.deploy("candidate:release")
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
