from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_plane.common import ControlPlaneError, canonical_json_bytes, sha256_bytes
from engine import fixture_packets
from engine.fixture_packets import FixturePacketController


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class FixturePacketControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.controller = FixturePacketController(FACTORY_ROOT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_list_exposes_only_allowlisted_non_live_adapters(self) -> None:
        packets = self.controller.list()

        self.assertEqual(["WB-001", "WB-013"], [row["workbench_code"] for row in packets])
        self.assertEqual(
            ["WB001_REFERENCE_FIXTURE_PACKET_V1", "WB013_ENTRY_FIXTURE_PACKET_V1"],
            [row["adapter_id"] for row in packets],
        )
        self.assertTrue(all(row["scientific_standing"] == "NONE" for row in packets))
        self.assertTrue(all(row["live_research_authorized"] is False for row in packets))

    def test_registry_rejects_a_changed_adapter_file_before_execution(self) -> None:
        with patch.object(fixture_packets, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(ControlPlaneError, "adapter_file SHA-256 differs"):
                FixturePacketController(FACTORY_ROOT)

    def test_registry_locks_runner_and_build_input_bytes(self) -> None:
        locked_targets = (
            (
                FACTORY_ROOT
                / "workbenches"
                / "wb001_lossless_compression"
                / "runner"
                / "candidate_package.py",
                "runner.script SHA-256 differs",
            ),
            (
                FACTORY_ROOT
                / "workbenches"
                / "wb001_lossless_compression"
                / "examples"
                / "zlib_level9"
                / "submission.json",
                "runner.build_input SHA-256 differs",
            ),
        )
        actual_sha256_file = fixture_packets.sha256_file
        for target, expected_error in locked_targets:
            with self.subTest(target=target.name):
                def tampered_sha256(path: Path) -> str:
                    if path.resolve() == target.resolve():
                        return "0" * 64
                    return actual_sha256_file(path)

                with patch.object(fixture_packets, "sha256_file", side_effect=tampered_sha256):
                    with self.assertRaisesRegex(ControlPlaneError, expected_error):
                        FixturePacketController(FACTORY_ROOT)

    def test_draft_check_validates_an_unregistered_adapter_without_execution(self) -> None:
        source = (
            FACTORY_ROOT
            / "fixture_packets"
            / "adapters"
            / "wb001-reference-fixture.json"
        )
        draft = json.loads(source.read_text(encoding="utf-8"))
        draft["adapter_id"] = "WB001_LOCAL_DRAFT_PACKET_V1"
        unsigned = {key: value for key, value in draft.items() if key != "adapter_sha256"}
        draft["adapter_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        draft_path = self.root / "wb001-local-draft.json"
        draft_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")

        result = self.controller.validate_draft(draft_path)

        self.assertTrue(result["valid"])
        self.assertTrue(result["registry_status"]["workbench_has_registered_adapter"])
        self.assertFalse(result["registry_status"]["exact_adapter_registered"])
        self.assertFalse(result["registry_status"]["registration_changed"])
        self.assertFalse(result["runner_execution"]["executed"])
        self.assertFalse(result["construction_boundary"]["scientific_evidence"])

    def test_unknown_workbench_is_not_a_general_runner(self) -> None:
        with self.assertRaisesRegex(ControlPlaneError, "no allowlisted fixture packet adapter"):
            self.controller.execute(
                "build",
                workbench="WB-002",
                output=self.root / "unexpected-packet",
            )

    def test_rehearsal_requires_a_demo_identity(self) -> None:
        with self.assertRaisesRegex(ControlPlaneError, "demo: operator identity"):
            self.controller.execute(
                "rehearse",
                workbench="WB-001",
                package=self.root / "not-used",
                output=self.root / "not-used-receipt.json",
                operator_id="human:alice",
            )

    def test_build_verify_and_rehearse_each_known_safe_fixture(self) -> None:
        for workbench in ("WB-001", "WB-013"):
            with self.subTest(workbench=workbench):
                package = self.root / f"{workbench.lower()}-packet"
                receipt = self.root / f"{workbench.lower()}-rehearsal.json"

                built = self.controller.execute("build", workbench=workbench, output=package)
                self.assertEqual("BUILD", built["action"])
                self.assertFalse(built["construction_boundary"]["scientific_evidence"])

                verified = self.controller.execute("verify", workbench=workbench, package=package)
                self.assertTrue(verified["result"]["valid"])
                self.assertFalse(verified["construction_boundary"]["eligible_for_promotion"])

                rehearsed = self.controller.execute(
                    "rehearse",
                    workbench=workbench,
                    package=package,
                    output=receipt,
                    operator_id=f"demo:{workbench.lower()}-test",
                )
                self.assertTrue(receipt.is_file())
                self.assertFalse(rehearsed["construction_boundary"]["counts_as_independent_reproduction"])


if __name__ == "__main__":
    unittest.main()
