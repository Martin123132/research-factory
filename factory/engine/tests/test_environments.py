from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from engine import environments as env
from engine.cli import main
from engine.fixture_packets import FixturePacketController


ROOT = Path(__file__).resolve().parents[2]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "environments", self.root / "environments")
        shutil.copyfile(ROOT / "requirements.lock", self.root / "requirements.lock")
        destination = self.root / "rounds/WB001-PILOT-001"
        destination.mkdir(parents=True)
        shutil.copyfile(ROOT / "rounds/WB001-PILOT-001/round.json", destination / "round.json")

    def write_index(self, value):
        (self.root / "environments/index.json").write_text(json.dumps(value), encoding="utf-8")

    def rewrite_manifest_for_negative_test(self, identity, change):
        index = json.loads((self.root / "environments/index.json").read_text())
        entry = next(row for row in index["profiles"] if row["environment_id"] == identity)
        path = self.root / entry["path"]
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_index(index)

    def test_rehashed_profile_cannot_relabel_a_changed_lock_as_the_old_round(self):
        path = self.root / "requirements.lock"
        path.write_bytes(path.read_bytes().replace(b"50.0.0", b"50.0.2"))
        self.rewrite_manifest_for_negative_test(
            env.LEGACY_PROFILE,
            lambda value: value["lock"].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
        )
        with self.assertRaisesRegex(env.EnvironmentProfileError, "round's frozen"):
            env.profiles(self.root)

    def test_rehashed_profile_cannot_introduce_path_traversal(self):
        self.rewrite_manifest_for_negative_test(
            "engine-v1", lambda value: value["lock"].update(path="../requirements.lock")
        )
        with self.assertRaisesRegex(env.EnvironmentProfileError, "unsafe environment path"):
            env.profiles(self.root)

    def test_current_profiles_keep_different_locks_and_no_scientific_standing(self):
        value = env.inspect_profiles(self.root)
        self.assertEqual("engine-v1", value["current_engine"])
        self.assertEqual({"50.0.0", "50.0.2"}, {p["pins"]["cryptography"] for p in value["profiles"]})
        self.assertFalse(any(value["boundary"].values()))

    def test_changed_lock_is_rejected(self):
        with (self.root / "requirements.lock").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(env.EnvironmentProfileError, "hash mismatch"):
            env.profiles(self.root)

    def test_changed_frozen_round_is_rejected(self):
        with (self.root / "rounds/WB001-PILOT-001/round.json").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(env.EnvironmentProfileError, "hash mismatch"):
            env.profiles(self.root)

    def test_changed_manifest_is_rejected(self):
        path = self.root / "environments/versions/engine-v1/manifest.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(env.EnvironmentProfileError, "hash mismatch"):
            env.profiles(self.root)

    def test_duplicate_json_and_unknown_fields_are_rejected(self):
        path = self.root / "environments/index.json"
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(env.EnvironmentProfileError, "duplicate JSON"):
            env.profiles(self.root)
        self.write_index({"schema_version": 1, "current_engine": "engine-v1", "profiles": [], "promoted": True})
        with self.assertRaisesRegex(env.EnvironmentProfileError, "closed format"):
            env.profiles(self.root)

    def test_duplicate_profile_and_wrong_current_role_are_rejected(self):
        original = json.loads((self.root / "environments/index.json").read_text())
        for mutation in ("duplicate", "role"):
            value = copy.deepcopy(original)
            if mutation == "duplicate":
                value["profiles"].append(value["profiles"][0])
            else:
                value["current_engine"] = env.LEGACY_PROFILE
            self.write_index(value)
            with self.subTest(mutation=mutation), self.assertRaises(env.EnvironmentProfileError):
                env.profiles(self.root)

    def test_traversal_absolute_and_windows_paths_are_rejected(self):
        for path in ("../requirements.lock", "/requirements.lock", "C:/requirements.lock", "a\\b", "a//b"):
            with self.subTest(path=path), self.assertRaises(env.EnvironmentProfileError):
                env._safe_file(self.root, path)

    def test_links_are_rejected(self):
        link = self.root / "linked.lock"
        try:
            link.symlink_to(self.root / "requirements.lock")
        except OSError:
            self.skipTest("host does not permit creating test symlinks")
        with self.assertRaisesRegex(env.EnvironmentProfileError, "links"):
            env._safe_file(self.root, "linked.lock")

    def test_unpinned_and_duplicate_dependencies_are_rejected(self):
        for value in ("cryptography>=50", "cryptography==50.*", "a_b==1\na-b==1"):
            path = self.root / "invalid.lock"
            path.write_text(value, encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(env.EnvironmentProfileError):
                env._pins(path)

    def test_wrong_or_missing_installed_version_is_rejected_before_rehearsal(self):
        _, loaded = env.profiles(self.root)
        pins = loaded[env.LEGACY_PROFILE]["pins"]
        for mode in ("wrong", "missing"):
            def version(name):
                if name == "cryptography":
                    if mode == "missing":
                        raise importlib.metadata.PackageNotFoundError(name)
                    return "50.0.2"
                return pins[name]
            with patch.object(env.importlib.metadata, "version", side_effect=version):
                self.assertFalse(env.check_runtime(self.root, env.LEGACY_PROFILE)["matches"])
                with self.assertRaisesRegex(env.EnvironmentProfileError, "does not match"):
                    env.rehearse(self.root, env.LEGACY_PROFILE)

    def test_governed_front_door_never_delegates_after_environment_rejection(self):
        with patch("engine.cli.require_runtime", side_effect=env.EnvironmentProfileError("wrong environment")), patch("engine.cli.governed_cli.main") as delegated, redirect_stderr(StringIO()):
            self.assertEqual(2, main(["status", "--round", "WB001-PILOT-001"]))
            delegated.assert_not_called()

    def test_fixture_front_door_never_spawns_after_environment_rejection(self):
        controller = FixturePacketController(ROOT)
        with patch("engine.fixture_packets.require_runtime", side_effect=env.EnvironmentProfileError("wrong environment")), patch("engine.fixture_packets.subprocess.run") as spawn:
            with self.assertRaises(env.EnvironmentProfileError):
                controller.execute("build", workbench="WB-001", output=self.root / "package")
            spawn.assert_not_called()

    def test_cli_requires_explicit_profile_for_runtime_check(self):
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            self.assertEqual(2, main(["environment", "check", "--json"]))

    def test_real_installed_environment_rehearses_without_changing_any_profile(self):
        index, loaded = env.profiles(ROOT)
        matching = [p for p in loaded if env.check_runtime(ROOT, p)["matches"]]
        self.assertEqual(1, len(matching), "Run these tests in one of the two pinned environments")
        self.assertIn(matching[0], (env.LEGACY_PROFILE, index["current_engine"]), "CI must test the current maintenance profile")
        before = {entry["path"]: (ROOT / entry["path"]).read_bytes() for entry in index["profiles"]}
        report = env.rehearse(ROOT, matching[0])
        self.assertTrue(report["fixture"]["round_trip_exact"])
        self.assertTrue(report["fixture"]["signature_verified"])
        self.assertFalse(any(report["boundary"].values()))
        digest = report.pop("report_sha256")
        self.assertEqual(digest, hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        for path, contents in before.items():
            self.assertEqual(contents, (ROOT / path).read_bytes())
